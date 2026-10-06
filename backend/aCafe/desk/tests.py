import json
from datetime import timedelta
from unittest import mock

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from sosuke.models import characters
from . import seats as seat_logic
from .models import Message, Room, Seat
from .routing import websocket_urlpatterns

IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def make_character(name="りん"):
    return characters.objects.create(
        name=name, age=20, gender=1, birthday="2000-01-01", height=160, occupation="学生",
        personality="", skill="", speciality="", individuality="", background="", life="", hobby="",
    )


class SeatApiTests(TestCase):
    def setUp(self):
        Seat.objects.all().delete()
        self.seat = Seat.objects.create(label="テスト席", capacity=2)

    def sit(self, anon_id="u1", seat=None):
        return self.client.post(
            f"/api/desk/seats/{(seat or self.seat).id}/sit/",
            data=json.dumps({"anon_id": anon_id}),
            content_type="application/json",
        )

    def list_seats(self):
        return self.client.get("/api/desk/seats/").json()["seats"]

    def test_empty_seat_is_vacant(self):
        (s,) = self.list_seats()
        self.assertEqual(s["status"], "vacant")
        self.assertEqual(s["human_count"], 0)
        self.assertEqual(s["atmosphere"], "")

    def test_sit_creates_room_and_reserves_seat(self):
        res = self.sit()
        self.assertEqual(res.status_code, 201)
        body = res.json()
        room = Room.objects.get(pk=body["room_id"])
        self.assertEqual(room.name, "テスト席")
        self.assertIn(f"/ws/rooms/{room.id}/", body["ws_path"])
        # WebSocket接続前でも、猶予時間内は空席に見えない
        (s,) = self.list_seats()
        self.assertEqual(s["status"], "occupied")

    def test_sit_requires_anon_id(self):
        res = self.client.post(
            f"/api/desk/seats/{self.seat.id}/sit/", data="{}", content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)

    def test_sit_unknown_seat(self):
        res = self.client.post(
            "/api/desk/seats/9999/sit/",
            data=json.dumps({"anon_id": "u1"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 404)

    def test_second_person_shares_room_within_grace(self):
        first = self.sit("u1").json()["room_id"]
        second = self.sit("u2").json()["room_id"]
        self.assertEqual(first, second)

    def test_full_seat_is_rejected(self):
        self.sit("u1")
        Room.objects.filter(pk=self.seat.__class__.objects.get(pk=self.seat.pk).room_id).update(human_count=2)
        self.assertEqual(self.list_seats()[0]["status"], "full")
        self.assertEqual(self.sit("u3").status_code, 409)

    def test_seat_becomes_vacant_after_grace_and_gets_new_room(self):
        old_room_id = self.sit("u1").json()["room_id"]
        Seat.objects.filter(pk=self.seat.pk).update(
            sat_at=timezone.now() - seat_logic.SIT_GRACE - timedelta(seconds=1)
        )
        self.assertEqual(self.list_seats()[0]["status"], "vacant")
        new_room_id = self.sit("u2").json()["room_id"]
        self.assertNotEqual(old_room_id, new_room_id)

    def test_new_sitter_releases_characters_of_old_room(self):
        old_room_id = self.sit("u1").json()["room_id"]
        Room.objects.get(pk=old_room_id).active_characters.add(make_character())
        Seat.objects.filter(pk=self.seat.pk).update(
            sat_at=timezone.now() - seat_logic.SIT_GRACE - timedelta(seconds=1)
        )
        self.sit("u2")
        self.assertFalse(Room.objects.get(pk=old_room_id).active_characters.exists())

    def test_occupied_seat_shows_characters_and_atmosphere(self):
        room_id = self.sit("u1").json()["room_id"]
        room = Room.objects.get(pk=room_id)
        Room.objects.filter(pk=room_id).update(human_count=1)
        room.active_characters.add(make_character("りん"))
        user = seat_logic.get_or_create_guest("u1")
        Message.objects.create(room=room, user=user, content="今日は雨だね")

        with mock.patch(
            "desk.ai_manager.generate_room_atmosphere_summary", return_value="雨の話でのんびり。"
        ) as gen:
            (s,) = self.list_seats()
            self.assertEqual(s["atmosphere"], "雨の話でのんびり。")
            self.assertEqual(s["characters"], ["りん"])
            self.assertEqual(s["human_count"], 1)
            # 新しい発言がなければ作り直さない
            self.list_seats()
            self.assertEqual(gen.call_count, 1)

    def test_atmosphere_failure_does_not_break_listing(self):
        room_id = self.sit("u1").json()["room_id"]
        room = Room.objects.get(pk=room_id)
        user = seat_logic.get_or_create_guest("u1")
        Message.objects.create(room=room, user=user, content="こんにちは")
        with mock.patch(
            "desk.ai_manager.generate_room_atmosphere_summary", side_effect=RuntimeError("ollama down")
        ):
            (s,) = self.list_seats()
        self.assertEqual(s["status"], "occupied")
        self.assertEqual(s["atmosphere"], "")

    def test_quiet_atmosphere_when_no_messages(self):
        self.sit("u1")
        self.assertEqual(self.list_seats()[0]["atmosphere"], seat_logic.QUIET_ATMOSPHERE)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER, DESK_LONELY_JOIN_SECONDS=(0.05, 0.05))
class SeatConsumerTests(TransactionTestCase):
    def setUp(self):
        Seat.objects.all().delete()
        self.seat = Seat.objects.create(label="テスト席", capacity=1)
        self.room = seat_logic.sit(self.seat.id)
        self.app = URLRouter(websocket_urlpatterns)

    def communicator(self, anon_id):
        return WebsocketCommunicator(self.app, f"/ws/rooms/{self.room.id}/?anon_id={anon_id}")

    async def test_capacity_is_enforced(self):
        a = self.communicator("alice")
        ok, _ = await a.connect()
        self.assertTrue(ok)
        b = self.communicator("bob")
        ok, code = await b.connect()
        self.assertFalse(ok)
        self.assertEqual(code, 4403)
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
        self.assertEqual(room.human_count, 0)
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
