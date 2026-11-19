import asyncio
import json
from datetime import timedelta
from unittest import mock

from channels.db import database_sync_to_async
from channels.layers import InMemoryChannelLayer, get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from sosuke.models import Users, characters
from . import ai_manager, safety, services, worker
from .models import DrinkGift, Message, Presence, Room
from .routing import websocket_urlpatterns

IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def make_character(name="りん"):
    return characters.objects.create(
        name=name, age=20, gender=1, birthday="2000-01-01", height=160, occupation="学生",
        personality="", skill="", speciality="", individuality="", background="", life="", hobby="",
    )


def make_user(anon_id="alice0001"):
    return services.get_or_create_guest(anon_id)


def make_fire(owner=None, **kwargs):
    kwargs.setdefault("name", "テストの焚火")
    return Room.objects.create(kind=Room.KIND_USER, owner=owner, **kwargs)


def sit(room, user, channel="ch-1", seen=None):
    return Presence.objects.create(
        room=room, user=user, channel_name=channel, last_seen=seen or timezone.now()
    )


# ====================================
# 見張り
# ====================================

class SafetyTests(SimpleTestCase):
    def kind(self, text):
        return safety.classify(text).kind

    def test_ordinary_talk_is_ok(self):
        self.assertEqual(self.kind("今日は寒いね"), safety.OK)
        self.assertEqual(self.kind("ゴミ出しの日を忘れてた"), safety.OK)
        self.assertEqual(self.kind("カスタードのパンを食べた"), safety.OK)

    def test_wish_to_die_is_not_blocked(self):
        self.assertEqual(self.kind("もう死にたいって思ってる"), safety.IDEATION)
        self.assertEqual(self.kind("消えたいな"), safety.IDEATION)

    def test_not_wanting_to_die_is_ok(self):
        self.assertEqual(self.kind("死にたくないよ"), safety.OK)

    def test_plan_or_time_is_imminent(self):
        self.assertEqual(self.kind("今夜、死にたい"), safety.IMMINENT)
        self.assertEqual(self.kind("遺書を書いた。死にたい"), safety.IMMINENT)

    def test_method_is_blocked(self):
        self.assertEqual(self.kind("首を吊る方法を教えて"), safety.METHOD)
        self.assertEqual(self.kind("楽に死ぬ方法ってある?"), safety.METHOD)
        self.assertEqual(self.kind("練炭"), safety.METHOD)

    def test_attack_on_others_is_held(self):
        self.assertEqual(self.kind("お前なんか死ね"), safety.ATTACK)
        self.assertEqual(self.kind("うざい"), safety.ATTACK)

    def test_harsh_words_about_oneself_are_not_attacks(self):
        self.assertEqual(self.kind("自分はクズだ"), safety.OK)
        self.assertEqual(self.kind("私なんてクズだよね"), safety.OK)

    def test_cannot_die_is_not_an_attack(self):
        self.assertEqual(self.kind("死ねない"), safety.OK)

    def test_mask_hides_only_strong_words(self):
        self.assertEqual(safety.mask_attack_words("お前なんか死ね"), "お前なんか…")

    def test_care_messages_carry_crisis_lines(self):
        for kind in (safety.IDEATION, safety.IMMINENT, safety.METHOD):
            numbers = [line["number"] for line in safety.care_payload(kind)["lines"]]
            self.assertIn("0120-279-338", numbers)

    def test_ideation_care_never_says_the_wish_is_right(self):
        for kind in (safety.IDEATION, safety.IMMINENT, safety.METHOD):
            body = safety.care_payload(kind)["body"] + safety.listener_guide(kind)
            self.assertNotIn("仕方ない", body)
            self.assertNotIn("正しい", body)

    def test_keeper_guidance_forbids_agreeing(self):
        self.assertIn("「正しい」「仕方ない」とは言わない", ai_manager.KEEPER_GUIDANCE)


# ====================================
# 火・輪・AIキャラ(ロジック)
# ====================================

@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class ServicesTests(TestCase):
    def setUp(self):
        Room.objects.all().delete()
        self.alice = make_user("alice0001")
        self.bob = make_user("bobbob0001")

    # --- 火 ---

    def test_fire_gets_smaller_over_time(self):
        now = timezone.now()
        room = make_fire(fire_level=0.6, fire_updated_at=now - timedelta(minutes=20))
        self.assertAlmostEqual(services.fire_level_now(room, now), 0.2, places=2)

    def test_feeding_makes_it_bigger_and_resets_the_closing_notice(self):
        room = make_fire(fire_level=0.1, closing_announced=True)
        fire = services.feed_fire(room.pk, 0.5)
        self.assertGreater(fire["level"], 0.5)
        room.refresh_from_db()
        self.assertFalse(room.closing_announced)

    def test_ambient_fire_never_goes_out(self):
        room = Room.objects.create(
            name="AI", kind=Room.KIND_AMBIENT, fire_level=0.0,
            fire_updated_at=timezone.now() - timedelta(hours=5),
        )
        self.assertFalse(services.is_burnt_out(room))
        self.assertGreaterEqual(services.fire_level_now(room), 0.5)

    def test_burnt_out_user_fire(self):
        room = make_fire(fire_level=0.05, fire_updated_at=timezone.now() - timedelta(minutes=30))
        self.assertTrue(services.is_burnt_out(room))

    def test_extinguish_deletes_the_fire_and_everything_said_there(self):
        room = make_fire(owner=self.alice)
        Message.objects.create(room=room, user=self.alice, content="つらい")
        DrinkGift.objects.create(room=room, from_user=self.alice, item_name="薪")
        sit(room, self.alice)
        self.assertTrue(services.extinguish(room.pk))
        self.assertFalse(Room.objects.filter(pk=room.pk).exists())
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(DrinkGift.objects.count(), 0)
        self.assertEqual(Presence.objects.count(), 0)

    def test_legacy_rooms_are_never_touched(self):
        room = Room.objects.create(name="むかし", kind=Room.KIND_LEGACY)
        Message.objects.create(room=room, user=self.alice, content="むかしの発言")
        self.assertFalse(services.extinguish(room.pk))
        self.assertEqual(Message.objects.count(), 1)

    # --- 輪 ---

    def test_capacity_counts_people_not_connections(self):
        room = make_fire(capacity=2)
        services.enter(room.pk, self.alice, "ch-a1")
        services.enter(room.pk, self.alice, "ch-a2")  # 同じ人の別タブ
        self.assertEqual(services.human_count(room.pk), 1)
        services.enter(room.pk, self.bob, "ch-b1")
        carol = make_user("carol00001")
        with self.assertRaises(services.FireFullError):
            services.enter(room.pk, carol, "ch-c1")

    def test_second_connection_of_same_user_is_not_a_new_member(self):
        room = make_fire()
        first = services.enter(room.pk, self.alice, "ch-a1")
        second = services.enter(room.pk, self.alice, "ch-a2")
        self.assertTrue(first.new_member)
        self.assertFalse(second.new_member)

    def test_legacy_room_cannot_be_entered(self):
        room = Room.objects.create(name="むかし", kind=Room.KIND_LEGACY)
        with self.assertRaises(Room.DoesNotExist):
            services.enter(room.pk, self.alice, "ch-a1")

    def test_leave_reports_whether_the_person_is_fully_gone(self):
        room = make_fire()
        services.enter(room.pk, self.alice, "ch-a1")
        services.enter(room.pk, self.alice, "ch-a2")
        self.assertFalse(services.leave("ch-a1").fully_left)
        last = services.leave("ch-a2")
        self.assertTrue(last.fully_left)
        self.assertEqual(last.count, 0)
        self.assertIsNone(services.leave("ch-a2"))  # 二重に呼んでも安全

    def test_dead_connection_stops_counting_after_ttl_without_any_disconnect(self):
        room = make_fire()
        sit(room, self.alice, seen=timezone.now() - timedelta(seconds=120))
        self.assertEqual(services.human_count(room.pk), 0)

    def test_purge_removes_ghosts_and_reports_them_once(self):
        room = make_fire()
        old = timezone.now() - timedelta(seconds=300)
        sit(room, self.alice, "ch-a1", seen=old)
        sit(room, self.alice, "ch-a2", seen=old)
        sit(room, self.bob, "ch-b1")
        left = services.purge_stale()
        self.assertEqual([r.user.pk for r in left], [self.alice.pk])
        self.assertEqual(Presence.objects.count(), 1)

    def test_purge_does_not_report_someone_who_still_has_a_live_connection(self):
        room = make_fire()
        sit(room, self.alice, "ch-a1", seen=timezone.now() - timedelta(seconds=300))
        sit(room, self.alice, "ch-a2")
        self.assertEqual(services.purge_stale(), [])

    def test_touch_restores_a_purged_presence(self):
        room = make_fire()
        self.assertTrue(services.touch("ch-new", room.pk, self.alice))
        self.assertEqual(services.human_count(room.pk), 1)

    def test_touch_fails_when_the_fire_is_gone(self):
        room = make_fire()
        pk = room.pk
        room.delete()
        self.assertFalse(services.touch("ch-new", pk, self.alice))

    # --- 作る・変える ---

    def test_create_validates_and_limits(self):
        with self.assertRaises(services.FireError):
            services.create_fire(self.alice, "", capacity=4)
        with self.assertRaises(services.FireError):
            services.create_fire(self.alice, "a" * 31, capacity=4)
        with self.assertRaises(services.FireError):
            services.create_fire(self.alice, "ok", capacity=1)
        with self.assertRaises(services.FireError):
            services.create_fire(self.alice, "ok", capacity=999)
        with override_settings(DESK_MAX_FIRES_PER_USER=1):
            services.create_fire(self.alice, "ひとつめ", capacity=4)
            with self.assertRaises(services.FireError):
                services.create_fire(self.alice, "ふたつめ", capacity=4)

    def test_lowering_capacity_keeps_people_but_blocks_newcomers(self):
        room = make_fire(owner=self.alice, capacity=4)
        services.enter(room.pk, self.alice, "ch-a1")
        services.enter(room.pk, self.bob, "ch-b1")
        services.update_fire(room, capacity=2)
        self.assertEqual(services.human_count(room.pk), 2)
        with self.assertRaises(services.FireFullError):
            services.enter(room.pk, make_user("carol00001"), "ch-c1")

    def test_approving_a_note_clears_the_draft(self):
        room = make_fire(owner=self.alice, note_draft="仕事の疲れについて話しています")
        services.update_fire(room, public_note="仕事の疲れについて話しています")
        room.refresh_from_db()
        self.assertEqual(room.public_note, "仕事の疲れについて話しています")
        self.assertEqual(room.note_draft, "")

    # --- 一覧 ---

    def test_list_puts_lonely_people_first_and_hides_legacy(self):
        Room.objects.create(name="むかし", kind=Room.KIND_LEGACY)
        empty = make_fire(name="誰もいない")
        crowd = make_fire(name="にぎやか", capacity=3)
        lonely = make_fire(name="ひとり")
        for i, name in enumerate(["u1", "u2"]):
            sit(crowd, make_user(f"{name}000000"), channel=f"c{i}")
        sit(lonely, self.alice, channel="cl")
        items, total = services.list_fires()
        names = [i["name"] for i in items]
        self.assertNotIn("むかし", names)
        self.assertEqual(names[0], "ひとり")
        self.assertLess(names.index("にぎやか"), names.index("誰もいない"))
        self.assertEqual(total, 3)

    def test_welcome_text_for_a_lone_person(self):
        room = make_fire()
        self.assertIn("誰かを待っている", services.welcome_text(room, 1))

    def test_welcome_is_insiders_when_two_people_do_all_the_talking(self):
        room = make_fire(capacity=6)
        users = [make_user(f"user{i}0000") for i in range(3)]
        for i, u in enumerate(users):
            sit(room, u, channel=f"c{i}")
        for _ in range(5):
            Message.objects.create(room=room, user=users[0], content="a")
            Message.objects.create(room=room, user=users[1], content="b")
        self.assertEqual(services.compute_welcome(room, 3), "insiders")

    def test_welcome_is_waiting_when_there_is_room_and_talk_is_spread_out(self):
        room = make_fire(capacity=6)
        users = [make_user(f"user{i}0000") for i in range(3)]
        for i, u in enumerate(users):
            sit(room, u, channel=f"c{i}")
            Message.objects.create(room=room, user=u, content="x")
        self.assertEqual(services.compute_welcome(room, 3), "waiting")

    # --- AIキャラ ---

    def test_acquire_takes_a_free_character(self):
        char = make_character()
        room = make_fire()
        got, borrowed = services.acquire_character(room.pk)
        self.assertEqual(got, char)
        self.assertIsNone(borrowed)

    def test_acquire_borrows_from_an_empty_ambient_fire(self):
        char = make_character()
        ambient = Room.objects.create(name="AI", kind=Room.KIND_AMBIENT)
        ambient.active_characters.add(char)
        room = make_fire()
        got, borrowed = services.acquire_character(room.pk)
        self.assertEqual(got, char)
        self.assertEqual(borrowed, ambient.pk)
        self.assertFalse(ambient.active_characters.exists())

    def test_acquire_does_not_borrow_from_an_ambient_fire_with_people(self):
        char = make_character()
        ambient = Room.objects.create(name="AI", kind=Room.KIND_AMBIENT)
        ambient.active_characters.add(char)
        sit(ambient, self.bob, channel="cb")
        room = make_fire()
        self.assertEqual(services.acquire_character(room.pk), (None, None))

    def test_ambient_messages_are_pruned(self):
        ambient = Room.objects.create(name="AI", kind=Room.KIND_AMBIENT)
        for i in range(8):
            Message.objects.create(room=ambient, user=self.alice, content=str(i))
        services.prune_ambient_messages(keep=3)
        self.assertEqual(Message.objects.filter(room=ambient).count(), 3)


# ====================================
# HTTP API
# ====================================

@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class FireApiTests(TestCase):
    def setUp(self):
        Room.objects.all().delete()
        self.alice = make_user("alice0001")

    def post(self, path, data, method="post"):
        return getattr(self.client, method)(
            path, data=json.dumps(data), content_type="application/json"
        )

    def create(self, anon_id="alice0001", **kwargs):
        body = {"anon_id": anon_id, "name": "夜更かしの焚火", "capacity": 4, **kwargs}
        return self.post("/api/desk/fires/", body)

    def test_create_and_list(self):
        res = self.create(topic="眠れない人へ")
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual((body["capacity"], body["is_mine"], body["human_count"]), (4, True, 0))
        self.assertNotIn("anon_id", json.dumps(body))

        listed = self.client.get("/api/desk/fires/?anon_id=alice0001").json()
        self.assertEqual(listed["total"], 1)
        self.assertTrue(listed["fires"][0]["is_mine"])
        other = self.client.get("/api/desk/fires/?anon_id=bobbob0001").json()
        self.assertFalse(other["fires"][0]["is_mine"])

    def test_create_requires_valid_anon_id_and_name(self):
        self.assertEqual(self.create(anon_id="x").status_code, 400)
        self.assertEqual(self.create(name="").status_code, 400)
        self.assertEqual(self.create(capacity=1).status_code, 400)

    def test_only_the_owner_can_change_or_put_out_the_fire(self):
        fire_id = self.create().json()["id"]
        make_user("bobbob0001")
        res = self.post(f"/api/desk/fires/{fire_id}/", {"anon_id": "bobbob0001", "capacity": 9}, "patch")
        self.assertEqual(res.status_code, 403)
        res = self.post(f"/api/desk/fires/{fire_id}/", {"anon_id": "bobbob0001"}, "delete")
        self.assertEqual(res.status_code, 403)

        res = self.post(f"/api/desk/fires/{fire_id}/", {"anon_id": "alice0001", "capacity": 9}, "patch")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["capacity"], 9)

        res = self.post(f"/api/desk/fires/{fire_id}/", {"anon_id": "alice0001"}, "delete")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Room.objects.filter(pk=fire_id).exists())

    def test_only_an_approved_note_is_shown_outside(self):
        fire_id = self.create().json()["id"]
        Room.objects.filter(pk=fire_id).update(note_draft="仕事の疲れについて話しています")
        listed = self.client.get("/api/desk/fires/").json()["fires"][0]
        self.assertEqual(listed["public_note"], "")  # 下書きは外に出ない
        self.assertNotIn("仕事の疲れ", json.dumps(listed, ensure_ascii=False))

        self.post(
            f"/api/desk/fires/{fire_id}/",
            {"anon_id": "alice0001", "public_note": "仕事の疲れについて話しています"},
            "patch",
        )
        listed = self.client.get("/api/desk/fires/").json()["fires"][0]
        self.assertEqual(listed["public_note"], "仕事の疲れについて話しています")

    def test_join_returns_history_and_owner_sees_the_draft(self):
        fire_id = self.create().json()["id"]
        Message.objects.create(room_id=fire_id, user=self.alice, content="こんばんは")
        Room.objects.filter(pk=fire_id).update(note_draft="下書き")

        res = self.post(f"/api/desk/fires/{fire_id}/join/", {"anon_id": "alice0001"})
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["ws_path"], f"/ws/fires/{fire_id}/?anon_id=alice0001")
        self.assertEqual([m["message"] for m in body["history"]], ["こんばんは"])
        self.assertEqual(body["note_draft"], "下書き")

        res = self.post(f"/api/desk/fires/{fire_id}/join/", {"anon_id": "bobbob0001"})
        self.assertEqual(res.json()["note_draft"], "")

    def test_join_is_refused_when_the_circle_is_full(self):
        fire_id = self.create(capacity=2).json()["id"]
        room = Room.objects.get(pk=fire_id)
        sit(room, self.alice, "c1")
        sit(room, make_user("bobbob0001"), "c2")
        res = self.post(f"/api/desk/fires/{fire_id}/join/", {"anon_id": "carol00001"})
        self.assertEqual(res.status_code, 409)
        # すでに輪にいる人は、入り直せる
        res = self.post(f"/api/desk/fires/{fire_id}/join/", {"anon_id": "alice0001"})
        self.assertEqual(res.status_code, 201)

    def test_join_unknown_or_legacy_fire(self):
        legacy = Room.objects.create(name="むかし", kind=Room.KIND_LEGACY)
        self.assertEqual(self.post("/api/desk/fires/9999/join/", {"anon_id": "alice0001"}).status_code, 404)
        self.assertEqual(
            self.post(f"/api/desk/fires/{legacy.pk}/join/", {"anon_id": "alice0001"}).status_code, 404
        )

    def test_messages_can_only_be_read_from_inside_the_circle(self):
        fire_id = self.create().json()["id"]
        room = Room.objects.get(pk=fire_id)
        for i in range(5):
            Message.objects.create(room=room, user=self.alice, content=f"m{i}")

        outsider = self.client.get(f"/api/desk/fires/{fire_id}/messages/?anon_id=bobbob0001")
        self.assertEqual(outsider.status_code, 403)

        sit(room, self.alice, "c1")
        res = self.client.get(f"/api/desk/fires/{fire_id}/messages/?anon_id=alice0001&limit=2").json()
        self.assertEqual([m["message"] for m in res["messages"]], ["m3", "m4"])
        before = res["messages"][0]["id"]
        res = self.client.get(
            f"/api/desk/fires/{fire_id}/messages/?anon_id=alice0001&limit=2&before={before}"
        ).json()
        self.assertEqual([m["message"] for m in res["messages"]], ["m1", "m2"])
        after = res["messages"][-1]["id"]
        res = self.client.get(
            f"/api/desk/fires/{fire_id}/messages/?anon_id=alice0001&after={after}"
        ).json()
        self.assertEqual([m["message"] for m in res["messages"]], ["m3", "m4"])

    def test_gift_needs_presence_a_known_item_and_a_pause(self):
        fire_id = self.create().json()["id"]
        room = Room.objects.get(pk=fire_id)
        Room.objects.filter(pk=fire_id).update(fire_level=0.2, fire_updated_at=timezone.now())
        url = f"/api/desk/fires/{fire_id}/gifts/"

        self.assertEqual(self.post(url, {"anon_id": "alice0001", "item": "薪"}).status_code, 403)
        sit(room, self.alice, "c1")
        self.assertEqual(self.post(url, {"anon_id": "alice0001", "item": "ダイヤ"}).status_code, 400)

        res = self.post(url, {"anon_id": "alice0001", "item": "コーヒー", "message": "おつかれさま"})
        self.assertEqual(res.status_code, 201)
        self.assertGreater(res.json()["fire"]["level"], 0.3)
        self.assertEqual(DrinkGift.objects.get().from_user, self.alice)
        self.assertEqual(self.post(url, {"anon_id": "alice0001", "item": "薪"}).status_code, 429)


# ====================================
# worker
# ====================================

@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class WorkerTests(TestCase):
    def setUp(self):
        Room.objects.all().delete()
        self.alice = make_user("alice0001")
        self.bob = make_user("bobbob0001")
        patcher = mock.patch("desk.worker.broadcast")
        self.broadcast = patcher.start()
        self.addCleanup(patcher.stop)

    def events(self, type_, **match):
        out = []
        for call in self.broadcast.call_args_list:
            payload = call.args[1]
            if payload.get("type") == type_ and all(payload.get(k) == v for k, v in match.items()):
                out.append(payload)
        return out

    def test_burnt_out_fire_disappears_with_everything_said_there(self):
        room = make_fire(fire_level=0.05, fire_updated_at=timezone.now() - timedelta(minutes=30))
        Message.objects.create(room=room, user=self.alice, content="つらい")
        pk = room.pk
        worker.run_tick()
        self.assertFalse(Room.objects.filter(pk=pk).exists())
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(len(self.events("fire.out")), 1)

    def test_a_fire_being_fed_stays_lit(self):
        room = make_fire(fire_level=0.6)
        sit(room, self.alice)
        worker.run_tick()
        self.assertTrue(Room.objects.filter(pk=room.pk).exists())

    def test_ghost_connections_are_purged_and_announced(self):
        room = make_fire()
        sit(room, self.alice, "ch-a", seen=timezone.now() - timedelta(minutes=10))
        sit(room, self.bob, "ch-b")
        worker.run_tick()
        self.assertEqual(Presence.objects.count(), 1)
        leaves = self.events("chat.presence", event="leave")
        self.assertEqual([e["user_id"] for e in leaves], [self.alice.pk])

    def test_closing_words_when_the_fire_gets_small(self):
        char = make_character()
        room = make_fire(fire_level=0.1)
        room.active_characters.add(char)
        sit(room, self.alice)
        worker.run_tick()
        room.refresh_from_db()
        self.assertTrue(room.closing_announced)
        self.assertEqual(len(self.events("fire.closing")), 1)
        self.assertIn("また", Message.objects.get(room=room).content)
        worker.run_tick()  # 二度は言わない
        self.assertEqual(len(self.events("fire.closing")), 1)

    def test_characters_go_home_when_everyone_has_left(self):
        char = make_character()
        room = make_fire()
        room.active_characters.add(char)
        worker.run_tick()
        self.assertFalse(room.active_characters.exists())

    def test_lonely_person_gets_a_visit_after_a_wait(self):
        char = make_character()
        room = make_fire()
        sit(room, self.alice)

        worker.run_tick()  # 1回目: 来る時刻が決まるだけ
        room.refresh_from_db()
        self.assertIsNotNone(room.ai_join_after)
        self.assertFalse(room.active_characters.exists())

        Room.objects.filter(pk=room.pk).update(ai_join_after=timezone.now() - timedelta(seconds=1))
        with mock.patch("desk.ai_manager.generate_character_reply", return_value="こんばんは") as reply:
            worker.run_tick()
        self.assertEqual(list(room.active_characters.all()), [char])
        self.assertEqual(len(self.events("chat.presence", event="ai_join")), 1)
        gift = DrinkGift.objects.get(room=room)
        self.assertEqual((gift.from_character, gift.item_name), (char, "コーヒー"))
        self.assertEqual(Message.objects.get(room=room).content, "こんばんは")
        self.assertIsNone(reply.call_args.kwargs.get("guidance"))

    def test_visit_still_happens_when_the_ai_is_down(self):
        char = make_character()
        room = make_fire(ai_join_after=timezone.now() - timedelta(seconds=1))
        sit(room, self.alice)
        with mock.patch("desk.ai_manager.generate_character_reply", side_effect=RuntimeError("down")):
            worker.run_tick()
        self.assertEqual(list(room.active_characters.all()), [char])
        self.assertTrue(DrinkGift.objects.filter(room=room).exists())

    def test_nobody_visits_when_two_people_are_already_there(self):
        make_character()
        room = make_fire(ai_join_after=timezone.now() - timedelta(seconds=1))
        sit(room, self.alice, "c1")
        sit(room, self.bob, "c2")
        worker.run_tick()
        room.refresh_from_db()
        self.assertFalse(room.active_characters.exists())
        self.assertIsNone(room.ai_join_after)

    def test_visit_is_called_off_if_the_person_left_in_the_meantime(self):
        make_character()
        room = make_fire(ai_join_after=timezone.now() - timedelta(seconds=1))
        worker.run_tick()
        self.assertFalse(room.active_characters.exists())

    def test_longest_waiting_person_is_served_first(self):
        make_character("りん")
        first = make_fire(name="先", ai_join_after=timezone.now() - timedelta(seconds=50))
        second = make_fire(name="後", ai_join_after=timezone.now() - timedelta(seconds=5))
        sit(first, self.alice, "c1")
        sit(second, self.bob, "c2")
        with mock.patch("desk.ai_manager.generate_character_reply", return_value="やあ"):
            worker.run_tick()
        self.assertTrue(first.active_characters.exists())
        self.assertFalse(second.active_characters.exists())  # キャラが1人しかいない

    def test_a_character_is_borrowed_from_an_empty_ambient_fire(self):
        char = make_character()
        ambient = Room.objects.create(
            name="AI", kind=Room.KIND_AMBIENT, ambient_next_at=timezone.now() + timedelta(hours=1)
        )
        ambient.active_characters.add(char)
        room = make_fire(ai_join_after=timezone.now() - timedelta(seconds=1))
        sit(room, self.alice)
        with mock.patch("desk.ai_manager.generate_character_reply", return_value="やあ"):
            worker.run_tick()
        self.assertEqual(list(room.active_characters.all()), [char])
        self.assertEqual(len(self.events("chat.presence", event="ai_leave")), 1)

    def test_ambient_fire_fills_up_with_characters(self):
        make_character("a")
        make_character("b")
        make_character("c")
        ambient = Room.objects.create(name="AI", kind=Room.KIND_AMBIENT)
        worker.run_tick()
        self.assertEqual(ambient.active_characters.count(), 2)
        ambient.refresh_from_db()
        self.assertGreater(ambient.ambient_next_at, timezone.now())

    def test_ambient_characters_chat_and_it_is_saved(self):
        a, b = make_character("a"), make_character("b")
        ambient = Room.objects.create(name="AI", kind=Room.KIND_AMBIENT)
        ambient.active_characters.add(a, b)
        with mock.patch("desk.worker.random.random", return_value=0.9), mock.patch(
            "desk.ai_manager.generate_ambient_exchange", return_value=[(a, "いい天気"), (b, "そうだね")]
        ):
            worker.run_tick()
        self.assertEqual(
            list(Message.objects.filter(room=ambient).values_list("content", flat=True)),
            ["いい天気", "そうだね"],
        )

    def test_ambient_fire_with_a_visitor_is_left_alone(self):
        a, b = make_character("a"), make_character("b")
        ambient = Room.objects.create(name="AI", kind=Room.KIND_AMBIENT)
        ambient.active_characters.add(a, b)
        sit(ambient, self.alice)
        with mock.patch("desk.ai_manager.generate_ambient_exchange") as exchange:
            worker.run_tick()
        exchange.assert_not_called()
        self.assertEqual(ambient.active_characters.count(), 2)

    def test_note_draft_goes_only_to_the_owner_and_not_to_the_public_list(self):
        room = make_fire(owner=self.alice)
        sit(room, self.alice)
        for i in range(5):
            Message.objects.create(room=room, user=self.alice, content=f"つらい{i}")
        with mock.patch("desk.ai_manager.draft_public_note", return_value="しんどい日々について話しています"):
            worker.run_tick()
        room.refresh_from_db()
        self.assertEqual(room.note_draft, "しんどい日々について話しています")
        self.assertEqual(room.public_note, "")
        (event,) = self.events("note.draft")
        self.assertEqual(event["owner_id"], self.alice.pk)

        with mock.patch("desk.ai_manager.draft_public_note") as draft:
            worker.run_tick()  # 間隔が空いていないので、作り直さない
        draft.assert_not_called()

    def test_no_note_draft_when_the_owner_is_away(self):
        room = make_fire(owner=self.alice)
        sit(room, self.bob)
        for i in range(5):
            Message.objects.create(room=room, user=self.bob, content=f"m{i}")
        with mock.patch("desk.ai_manager.draft_public_note") as draft:
            worker.run_tick()
        draft.assert_not_called()


# ====================================
# WebSocket
# ====================================

@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER, DESK_MIN_SEND_INTERVAL=0)
class FireConsumerTests(TransactionTestCase):
    def setUp(self):
        Room.objects.all().delete()
        self.room = make_fire(capacity=2)
        self.app = URLRouter(websocket_urlpatterns)
        patcher = mock.patch("desk.consumers.random.uniform", return_value=0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def communicator(self, anon_id, room_id=None):
        return WebsocketCommunicator(
            self.app, f"/ws/fires/{room_id or self.room.id}/?anon_id={anon_id}"
        )

    async def open(self, anon_id):
        comm = self.communicator(anon_id)
        ok, _ = await comm.connect()
        self.assertTrue(ok)
        return comm

    async def close_code(self, comm):
        """accept のあとに来る close のコードを返す(accept してから閉じるので、ブラウザにもコードが届く)。"""
        for _ in range(5):
            out = await comm.receive_output(timeout=3)
            if out["type"] == "websocket.close":
                return out["code"]
        self.fail("close が来ませんでした")

    async def events_until(self, comm, predicate, limit=15):
        events = []
        for _ in range(limit):
            events.append(await comm.receive_json_from(timeout=5))
            if predicate(events[-1]):
                return events
        self.fail(f"期待したイベントが来ませんでした: {events}")

    async def test_join_notice_carries_user_id_and_count(self):
        a = await self.open("alice0001")
        (event,) = await self.events_until(a, lambda e: e["type"] == "chat.presence")
        user = await database_sync_to_async(make_user)("alice0001")
        self.assertEqual(
            (event["event"], event["user_id"], event["count"]), ("join", user.pk, 1)
        )
        await a.disconnect()

    async def test_second_tab_of_the_same_person_does_not_announce_again(self):
        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        a2 = await self.open("alice0001")
        self.assertTrue(await a.receive_nothing(timeout=1))
        await a2.disconnect()
        self.assertTrue(await a.receive_nothing(timeout=1))  # 片方を閉じても「席を立った」にはならない
        await a.disconnect()

    async def test_full_circle_closes_with_4403(self):
        a = await self.open("alice0001")
        b = await self.open("bobbob0001")
        c = self.communicator("carol00001")
        await c.connect()
        self.assertEqual(await self.close_code(c), 4403)
        await a.disconnect()
        await b.disconnect()

    async def test_invalid_anon_id_and_unknown_fire(self):
        c = self.communicator("x")
        await c.connect()
        self.assertEqual(await self.close_code(c), 4401)
        c = self.communicator("alice0001", room_id=99999)
        await c.connect()
        self.assertEqual(await self.close_code(c), 4404)

    async def test_leaving_removes_the_presence_and_tells_the_others(self):
        a = await self.open("alice0001")
        b = await self.open("bobbob0001")
        await self.events_until(b, lambda e: e["type"] == "chat.presence" and e["count"] == 2)
        await a.disconnect()
        events = await self.events_until(
            b, lambda e: e["type"] == "chat.presence" and e["event"] == "leave"
        )
        self.assertEqual(events[-1]["count"], 1)
        count = await database_sync_to_async(services.human_count)(self.room.pk)
        self.assertEqual(count, 1)
        await b.disconnect()

    async def test_presence_is_removed_even_if_the_consumer_crashes(self):
        """Redisのタイムアウトなどでconsumerが落ちて、disconnect() が呼ばれなくても、人数が残らない。"""
        orig = InMemoryChannelLayer.receive

        async def boom(self, channel):
            await asyncio.sleep(0.5)
            raise RuntimeError("Timeout reading from redis")

        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        with mock.patch.object(InMemoryChannelLayer, "receive", boom):
            await asyncio.sleep(0.2)
            await asyncio.sleep(1.5)
            try:
                await a.wait(1)
            except BaseException:
                pass
        InMemoryChannelLayer.receive = orig
        count = await database_sync_to_async(services.human_count)(self.room.pk)
        self.assertEqual(count, 0)

    @override_settings(DESK_HEARTBEAT_SECONDS=0.1)
    async def test_heartbeat_keeps_the_presence_fresh(self):
        a = await self.open("alice0001")
        first = await database_sync_to_async(lambda: Presence.objects.get().last_seen)()
        await asyncio.sleep(0.5)
        second = await database_sync_to_async(lambda: Presence.objects.get().last_seen)()
        self.assertGreater(second, first)
        await a.disconnect()

    async def test_message_is_saved_and_feeds_the_fire(self):
        await database_sync_to_async(
            lambda: Room.objects.filter(pk=self.room.pk).update(fire_level=0.2, fire_updated_at=timezone.now())
        )()
        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        await a.send_json_to({"type": "chat.message", "message": "こんばんは"})
        events = await self.events_until(a, lambda e: e["type"] == "fire.level")
        msg = next(e for e in events if e["type"] == "chat.message")
        self.assertEqual(msg["message"], "こんばんは")
        self.assertGreater(events[-1]["fire"]["level"], 0.25)
        saved = await database_sync_to_async(lambda: list(Message.objects.values_list("content", flat=True)))()
        self.assertEqual(saved, ["こんばんは"])
        await a.disconnect()

    async def test_gift_event_reaches_the_circle(self):
        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        await get_channel_layer().group_send(
            services.group_name(self.room.pk), {"type": "chat.gift", "gift": {"item": "コーヒー"}}
        )
        event = await a.receive_json_from(timeout=3)
        self.assertEqual(event["gift"]["item"], "コーヒー")
        await a.disconnect()

    async def test_fire_out_closes_the_connection(self):
        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        await get_channel_layer().group_send(services.group_name(self.room.pk), {"type": "fire.out"})
        self.assertEqual((await a.receive_json_from(timeout=3))["type"], "fire.out")
        self.assertEqual(await self.close_code(a), 4410)

    # --- 見張り ---

    async def test_attack_is_held_then_burned_and_nothing_is_kept_or_shown(self):
        a = await self.open("alice0001")
        b = await self.open("bobbob0001")
        await self.events_until(b, lambda e: e["type"] == "chat.presence")
        with mock.patch("desk.ai_manager.suggest_softer_text", return_value="腹が立って仕方ない"):
            await a.send_json_to({"type": "chat.message", "message": "お前なんか死ね"})
            events = await self.events_until(a, lambda e: e["type"] == "chat.hold")
        hold = events[-1]
        self.assertEqual(hold["softened"], "腹が立って仕方ない")
        self.assertNotIn("死ね", json.dumps(hold, ensure_ascii=False))

        await a.send_json_to({"type": "chat.resolve_hold", "hold_id": hold["hold_id"], "choice": "burn"})
        await self.events_until(a, lambda e: e["type"] == "chat.burned")
        self.assertTrue(await b.receive_nothing(timeout=1))
        self.assertEqual(await database_sync_to_async(Message.objects.count)(), 0)
        await a.disconnect()
        await b.disconnect()

    async def test_attack_can_be_published_in_softer_words(self):
        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        with mock.patch("desk.ai_manager.suggest_softer_text", return_value="腹が立って仕方ない"):
            await a.send_json_to({"type": "chat.message", "message": "うざい"})
            hold = (await self.events_until(a, lambda e: e["type"] == "chat.hold"))[-1]
        await a.send_json_to(
            {"type": "chat.resolve_hold", "hold_id": hold["hold_id"], "choice": "softened"}
        )
        events = await self.events_until(a, lambda e: e["type"] == "chat.message")
        self.assertEqual(events[-1]["message"], "腹が立って仕方ない")
        saved = await database_sync_to_async(lambda: list(Message.objects.values_list("content", flat=True)))()
        self.assertEqual(saved, ["腹が立って仕方ない"])
        await a.disconnect()

    async def test_unknown_hold_id_does_nothing(self):
        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        await a.send_json_to({"type": "chat.resolve_hold", "hold_id": "nope", "choice": "softened"})
        self.assertTrue(await a.receive_nothing(timeout=1))
        await a.disconnect()

    async def test_ai_failure_falls_back_to_a_masked_version(self):
        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        with mock.patch("desk.ai_manager.suggest_softer_text", side_effect=RuntimeError("down")):
            await a.send_json_to({"type": "chat.message", "message": "お前なんか死ね"})
            hold = (await self.events_until(a, lambda e: e["type"] == "chat.hold"))[-1]
        self.assertEqual(hold["softened"], "お前なんか…")
        await a.disconnect()

    async def test_method_talk_is_shown_to_no_one_and_not_kept(self):
        a = await self.open("alice0001")
        b = await self.open("bobbob0001")
        await self.events_until(b, lambda e: e["type"] == "chat.presence")
        await a.send_json_to({"type": "chat.message", "message": "首を吊る方法を教えて"})
        care = (await self.events_until(a, lambda e: e["type"] == "chat.care"))[-1]["care"]
        self.assertEqual(care["kind"], safety.METHOD)
        self.assertTrue(care["lines"])
        self.assertTrue(await b.receive_nothing(timeout=1))
        self.assertEqual(await database_sync_to_async(Message.objects.count)(), 0)
        await a.disconnect()
        await b.disconnect()

    async def test_wish_to_die_is_heard_not_blocked(self):
        char = await database_sync_to_async(make_character)("りん")
        await database_sync_to_async(self.room.active_characters.add)(char)
        calls = []

        def fake_reply(character, recent, guidance=None, timeout=60):
            calls.append(guidance)
            return "死にたいほどつらいんだね。どんなことがあったのか、聞かせてもらえる?"

        a = await self.open("alice0001")
        b = await self.open("bobbob0001")
        await self.events_until(b, lambda e: e["type"] == "chat.presence" and e["count"] == 2)

        with mock.patch("desk.ai_manager.generate_character_reply", side_effect=fake_reply):
            await a.send_json_to({"type": "chat.message", "message": "もう死にたい"})
            a_events = await self.events_until(
                a, lambda e: e["type"] == "chat.message" and e["sender_type"] == "ai"
            )
            b_events = await self.events_until(
                b, lambda e: e["type"] == "chat.message" and e["sender_type"] == "ai"
            )

        # 本人の発言は、止められずに焚火へ届く
        self.assertIn("もう死にたい", [e.get("message") for e in b_events])
        # 本人にだけ静かな案内。聴く側の案内は、本人には出ない
        care = next(e for e in a_events if e["type"] == "chat.care")["care"]
        self.assertEqual(care["kind"], safety.IDEATION)
        self.assertNotIn("chat.guide", [e["type"] for e in a_events])
        self.assertIn("chat.guide", [e["type"] for e in b_events])
        self.assertNotIn("chat.care", [e["type"] for e in b_events])
        # キャラは、聴く方針(KEEPER_GUIDANCE)で返す
        self.assertEqual(calls, [ai_manager.KEEPER_GUIDANCE])
        saved = await database_sync_to_async(lambda: list(Message.objects.values_list("content", flat=True)))()
        self.assertEqual(saved[0], "もう死にたい")
        await a.disconnect()
        await b.disconnect()

    async def test_listener_guide_is_not_repeated_for_every_message(self):
        a = await self.open("alice0001")
        b = await self.open("bobbob0001")
        await self.events_until(b, lambda e: e["type"] == "chat.presence" and e["count"] == 2)
        with mock.patch("desk.ai_manager.generate_character_reply", return_value="うん"):
            for text in ("死にたい", "消えたい"):
                await a.send_json_to({"type": "chat.message", "message": text})
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.5)
            seen = []
            while not await b.receive_nothing(timeout=0.3):
                seen.append((await b.receive_output())["text"])
        guides = [s for s in seen if '"chat.guide"' in s]
        self.assertEqual(len(guides), 1)
        await a.disconnect()
        await b.disconnect()

    async def test_a_keeper_comes_when_nobody_is_there_to_listen(self):
        char = await database_sync_to_async(make_character)("りん")
        a = await self.open("alice0001")
        await self.events_until(a, lambda e: e["type"] == "chat.presence")
        with mock.patch("desk.ai_manager.generate_character_reply", side_effect=RuntimeError("down")):
            await a.send_json_to({"type": "chat.message", "message": "死にたい"})
            events = await self.events_until(
                a, lambda e: e["type"] == "chat.message" and e["sender_type"] == "ai"
            )
        join = next(e for e in events if e["type"] == "chat.presence")
        self.assertEqual((join["event"], join["user"]), ("ai_join", "りん"))
        # AIが使えなくても、固定の一言で、ひとりにはしない
        self.assertIn("死にたいほどつらい", events[-1]["message"])
        self.assertNotIn("仕方ない", events[-1]["message"])
        self.assertNotIn("正しい", events[-1]["message"])
        self.assertEqual(
            await database_sync_to_async(lambda: self.room.active_characters.first())(), char
        )
        await a.disconnect()
