import json
from datetime import timedelta
from unittest import mock

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from sosuke.models import characters
from . import tables as table_logic
from .models import Message, Presence, Room, Table
from .routing import websocket_urlpatterns

IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def occupy(room, n=1, age=timedelta(0)):
    """部屋に n 人が在席している状態にする(ageだけ前に最終確認したことにできる)。"""
    for i in range(n):
        Presence.objects.create(
            room=room, channel_name=f"test-{room.pk}-{i}-{age.total_seconds()}", last_seen=timezone.now() - age
        )


def make_character(name="りん"):
    return characters.objects.create(
        name=name, age=20, gender=1, birthday="2000-01-01", height=160, occupation="学生",
        personality="", skill="", speciality="", individuality="", background="", life="", hobby="",
    )


class TableApiTests(TestCase):
    def setUp(self):
        Table.objects.all().delete()
        self.table = Table.objects.create(name="ゆるく雑談", is_permanent=True)

    def post(self, path, **body):
        return self.client.post(path, data=json.dumps(body), content_type="application/json")

    def sit(self, anon_id="u1", table=None):
        return self.post(f"/api/desk/tables/{(table or self.table).id}/sit/", anon_id=anon_id)

    def create(self, name="最近読んだ本", anon_id="u1"):
        return self.post("/api/desk/tables/", name=name, anon_id=anon_id)

    def list_tables(self):
        return self.client.get("/api/desk/tables/").json()["tables"]

    def table_data(self, table=None):
        table = table or self.table
        return next(t for t in self.list_tables() if t["id"] == table.id)

    def test_empty_table_is_vacant(self):
        t = self.table_data()
        self.assertEqual(t["status"], "vacant")
        self.assertEqual(t["human_count"], 0)
        self.assertEqual(t["atmosphere"], "")
        self.assertTrue(t["is_permanent"])

    def test_sit_creates_room_and_reserves_table(self):
        res = self.sit()
        self.assertEqual(res.status_code, 201)
        body = res.json()
        room = Room.objects.get(pk=body["room_id"])
        self.assertEqual(room.name, "ゆるく雑談")
        self.assertIn(f"/ws/rooms/{room.id}/", body["ws_path"])
        # WebSocket接続前でも、猶予時間内は空きに見えない
        self.assertEqual(self.table_data()["status"], "occupied")

    def test_sit_validation(self):
        self.assertEqual(self.post(f"/api/desk/tables/{self.table.id}/sit/").status_code, 400)
        self.assertEqual(self.sit(table=Table(id=9999)).status_code, 404)

    def test_unlimited_people_share_one_room(self):
        room_id = self.sit("u0").json()["room_id"]
        for i in range(1, 10):
            self.assertEqual(self.sit(f"u{i}").json()["room_id"], room_id)
            table_logic.enter(room_id, f"ch{i}")
        t = self.table_data()
        self.assertEqual(t["status"], "occupied")
        self.assertEqual(t["human_count"], 9)

    def test_create_table_with_topic(self):
        res = self.create("最近読んだ本")
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["table"]["name"], "最近読んだ本")
        self.assertFalse(body["table"]["is_permanent"])
        room = Room.objects.get(pk=body["room_id"])
        self.assertEqual(room.table.name, "最近読んだ本")
        self.assertEqual(len(self.list_tables()), 2)

    def test_create_table_validation(self):
        self.assertEqual(self.create("").status_code, 400)
        self.assertEqual(self.create("   ").status_code, 400)
        self.assertEqual(self.create("あ" * (table_logic.TABLE_NAME_MAX + 1)).status_code, 400)
        self.assertEqual(self.post("/api/desk/tables/", name="話題").status_code, 400)  # anon_idなし

    def test_table_count_is_capped(self):
        with mock.patch.object(table_logic, "MAX_TABLES", 2):
            self.assertEqual(self.create("A").status_code, 201)
            self.assertEqual(self.create("B").status_code, 409)

    def test_user_made_table_closes_when_empty(self):
        body = self.create().json()
        table = Table.objects.get(pk=body["table"]["id"])
        table_logic.enter(body["room_id"], "ch1")
        self.assertEqual(len(self.list_tables()), 2)
        table_logic.leave(body["room_id"], "ch1")
        self.assertEqual([t["id"] for t in self.list_tables()], [self.table.id])
        self.assertFalse(Table.objects.filter(pk=table.pk).exists())
        # 部屋と発言ログは残る
        self.assertTrue(Room.objects.filter(pk=body["room_id"]).exists())

    def test_user_made_table_that_nobody_joined_closes_after_grace(self):
        body = self.create().json()
        Table.objects.filter(pk=body["table"]["id"]).update(
            sat_at=timezone.now() - table_logic.SIT_GRACE - timedelta(seconds=1)
        )
        self.assertEqual(len(self.list_tables()), 1)

    def test_permanent_table_stays_and_gets_new_room(self):
        old_room_id = self.sit("u1").json()["room_id"]
        table_logic.enter(old_room_id, "ch1")
        table_logic.leave(old_room_id, "ch1")
        self.assertEqual(self.table_data()["status"], "vacant")
        new_room_id = self.sit("u2").json()["room_id"]
        self.assertNotEqual(old_room_id, new_room_id)

    def test_new_sitter_releases_characters_of_old_room(self):
        old_room_id = self.sit("u1").json()["room_id"]
        Room.objects.get(pk=old_room_id).active_characters.add(make_character())
        Table.objects.filter(pk=self.table.pk).update(
            sat_at=timezone.now() - table_logic.SIT_GRACE - timedelta(seconds=1)
        )
        self.sit("u2")
        self.assertFalse(Room.objects.get(pk=old_room_id).active_characters.exists())

    def test_floor_total_counts_everyone(self):
        other = Table.objects.create(name="別の話題", is_permanent=True)
        occupy(table_logic.sit(self.table.id), 2)
        occupy(table_logic.sit(other.id), 3)
        floor = self.client.get("/api/desk/tables/").json()["floor"]
        self.assertEqual(floor["human_count"], 5)

    def test_occupied_table_shows_characters_and_atmosphere(self):
        room = table_logic.sit(self.table.id)
        occupy(room, 1)
        room.active_characters.add(make_character("りん"))
        user = table_logic.get_or_create_guest("u1")
        Message.objects.create(room=room, user=user, content="今日は雨だね")

        with mock.patch(
            "desk.ai_manager.generate_room_atmosphere_summary", return_value="雨の話でのんびり。"
        ) as gen:
            t = self.table_data()
            self.assertEqual(t["atmosphere"], "雨の話でのんびり。")
            self.assertEqual(t["characters"], ["りん"])
            self.assertEqual(t["human_count"], 1)
            # 新しい発言がなければ作り直さない
            self.list_tables()
            self.assertEqual(gen.call_count, 1)

    def test_atmosphere_failure_does_not_break_listing(self):
        room = table_logic.sit(self.table.id)
        user = table_logic.get_or_create_guest("u1")
        Message.objects.create(room=room, user=user, content="こんにちは")
        with mock.patch(
            "desk.ai_manager.generate_room_atmosphere_summary", side_effect=RuntimeError("ollama down")
        ):
            t = self.table_data()
        self.assertEqual(t["status"], "occupied")
        self.assertEqual(t["atmosphere"], "")

    def test_quiet_atmosphere_when_no_messages(self):
        self.sit("u1")
        self.assertEqual(self.table_data()["atmosphere"], table_logic.QUIET_ATMOSPHERE)

    def test_stale_ghost_presence_does_not_keep_table_occupied(self):
        room = table_logic.sit(self.table.id)
        occupy(room, 2, age=table_logic.PRESENCE_TTL + timedelta(seconds=1))
        Table.objects.filter(pk=self.table.pk).update(sat_at=None)
        t = self.table_data()
        self.assertEqual(t["status"], "vacant")
        self.assertEqual(t["human_count"], 0)

    def test_table_is_vacant_right_after_everyone_leaves(self):
        room = table_logic.sit(self.table.id)
        table_logic.enter(room.id, "ch1")
        self.assertEqual(self.table_data()["status"], "occupied")
        table_logic.leave(room.id, "ch1")
        t = self.table_data()
        self.assertEqual(t["status"], "vacant")
        self.assertEqual(t["human_count"], 0)

    def test_touch_keeps_presence_alive(self):
        room = table_logic.sit(self.table.id)
        table_logic.enter(room.id, "ch1")
        Presence.objects.filter(channel_name="ch1").update(
            last_seen=timezone.now() - table_logic.PRESENCE_TTL - timedelta(seconds=5)
        )
        self.assertEqual(table_logic.live_count(room), 0)
        table_logic.touch(room.id, "ch1")
        self.assertEqual(table_logic.live_count(room), 1)

    def test_purge_releases_characters_of_ghost_rooms(self):
        room = table_logic.sit(self.table.id)
        room.active_characters.add(make_character())
        occupy(room, 1, age=table_logic.PRESENCE_TTL + timedelta(seconds=1))
        table_logic.purge_stale_presences()
        self.assertFalse(room.active_characters.exists())
        self.assertEqual(Presence.objects.count(), 0)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER, DESK_LONELY_JOIN_SECONDS=(0.05, 0.05))
class SeatConsumerTests(TransactionTestCase):
    def setUp(self):
        Table.objects.all().delete()
        self.table = Table.objects.create(name="テスト席", is_permanent=True)
        self.room = table_logic.sit(self.table.id)
        self.app = URLRouter(websocket_urlpatterns)

    def communicator(self, anon_id):
        return WebsocketCommunicator(self.app, f"/ws/rooms/{self.room.id}/?anon_id={anon_id}")

    async def test_many_people_can_join_the_same_table(self):
        from channels.db import database_sync_to_async

        clients = [self.communicator(f"user{i}") for i in range(4)]
        for c in clients:
            ok, _ = await c.connect()
            self.assertTrue(ok)
        count = await database_sync_to_async(table_logic.live_count)(self.room)
        self.assertEqual(count, 4)
        for c in clients:
            await c.disconnect()

    async def test_ping_refreshes_presence(self):
        from channels.db import database_sync_to_async

        a = self.communicator("alice")
        await a.connect()
        await database_sync_to_async(Presence.objects.update)(
            last_seen=timezone.now() - table_logic.PRESENCE_TTL + timedelta(seconds=1)
        )
        await a.send_json_to({"type": "ping"})
        await a.receive_nothing(timeout=0.5)
        fresh = await database_sync_to_async(
            lambda: Presence.objects.filter(last_seen__gte=timezone.now() - timedelta(seconds=5)).count()
        )()
        self.assertEqual(fresh, 1)
        await a.disconnect()

    async def test_leaving_releases_characters_and_count(self):
        from channels.db import database_sync_to_async

        char = await database_sync_to_async(make_character)()
        await database_sync_to_async(self.room.active_characters.add)(char)
        a = self.communicator("alice")
        await a.connect()
        await a.receive_json_from()  # 自分のjoin通知
        await a.disconnect()
        room = await database_sync_to_async(Room.objects.get)(pk=self.room.pk)
        self.assertEqual(await database_sync_to_async(table_logic.live_count)(room), 0)
        has_chars = await database_sync_to_async(room.active_characters.exists)()
        self.assertFalse(has_chars)

    async def test_lonely_user_gets_a_character_who_greets(self):
        from channels.db import database_sync_to_async

        await database_sync_to_async(make_character)("りん")
        a = self.communicator("alice")
        await a.connect()
        events = []
        with mock.patch("desk.ai_manager.generate_character_reply", return_value="こんにちは"):
            while not any(e["type"] == "chat.message" for e in events):
                events.append(await a.receive_json_from(timeout=5))
        await a.disconnect()
        self.assertTrue(any(e.get("event") == "ai_join" and e["user"] == "りん" for e in events))
        msg = next(e for e in events if e["type"] == "chat.message")
        self.assertEqual((msg["sender_type"], msg["sender_name"], msg["message"]), ("ai", "りん", "こんにちは"))

    async def test_ai_failure_keeps_connection_alive(self):
        from channels.db import database_sync_to_async

        char = await database_sync_to_async(make_character)()
        await database_sync_to_async(self.room.active_characters.add)(char)
        a = self.communicator("alice")
        await a.connect()
        await a.receive_json_from()
        with mock.patch("desk.ai_manager.generate_character_reply", side_effect=RuntimeError("down")):
            await a.send_json_to({"type": "chat.message", "message": "やあ"})
            echo = await a.receive_json_from(timeout=5)
            self.assertEqual(echo["message"], "やあ")
            self.assertTrue(await a.receive_nothing(timeout=4))
        await a.disconnect()
