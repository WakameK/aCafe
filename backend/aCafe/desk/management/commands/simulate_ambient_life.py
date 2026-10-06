"""
くまの隠れ家の「キャラクターたちには自分の生活がある」世界観を実現するコマンド。

人間が誰もいない部屋を見て回り、
- AIキャラが2人に満たない部屋には、他の部屋にいないキャラを補充する
- 既に2人いる部屋では、たまにその2人でなんでもない雑談をさせる
- たまに、その部屋にいるキャラを1人退室させる(「自分の生活に戻る」演出)

cron や Django-Q2 のスケジュールタスクから、数分おきに実行することを想定している。

    python manage.py simulate_ambient_life
"""
import random

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.management.base import BaseCommand
from django.db import transaction

from desk import ai_manager
from desk.models import Message, Room
from desk.seats import live_count

CHAT_PROBABILITY = 0.5   # 既に2人いる部屋で、今回の実行時に雑談させる確率
LEAVE_PROBABILITY = 0.15  # 既に2人いる部屋で、1人を退室させる確率


class Command(BaseCommand):
    help = "人間が不在の部屋にAIキャラを補充し、たまに雑談させる(アンビエントな世界観の演出)"

    def handle(self, *args, **options):
        channel_layer = get_channel_layer()
        # 座席の部屋は対象外(一人で座った人のところに、しばらくしてからAIが入ってくる体験を壊さないため)
        empty_rooms = Room.objects.filter(seat__isnull=True).prefetch_related("active_characters")

        for room in empty_rooms:
            if live_count(room) > 0:
                continue
            active = list(room.active_characters.all())

            if len(active) < 2:
                self._fill_room(room, active, channel_layer)
            else:
                if random.random() < LEAVE_PROBABILITY:
                    self._character_leaves(room, active, channel_layer)
                elif random.random() < CHAT_PROBABILITY:
                    self._ambient_chat(room, active, channel_layer)

    def _fill_room(self, room, active, channel_layer):
        need = 2 - len(active)
        newcomers = ai_manager.pick_characters_for_room(room, count=need)
        for character in newcomers:
            with transaction.atomic():
                room.active_characters.add(character)
            async_to_sync(channel_layer.group_send)(
                f"room_{room.id}",
                {"type": "chat.presence", "event": "ai_join", "user": character.name},
            )
            self.stdout.write(f"[{room.name}] {character.name} が入室しました")

    def _character_leaves(self, room, active, channel_layer):
        leaver = random.choice(active)
        room.active_characters.remove(leaver)
        async_to_sync(channel_layer.group_send)(
            f"room_{room.id}",
            {"type": "chat.presence", "event": "leave", "user": leaver.name},
        )
        self.stdout.write(f"[{room.name}] {leaver.name} が退室しました")

    def _ambient_chat(self, room, active, channel_layer):
        a, b = random.sample(active, 2)
        exchange = ai_manager.generate_ambient_exchange(a, b, room, turns=random.randint(1, 2))
        for speaker, line in exchange:
            message = Message.objects.create(
                room=room, character=speaker, sender_type=Message.SENDER_AI, content=line
            )
            async_to_sync(channel_layer.group_send)(
                f"room_{room.id}",
                {
                    "type": "chat.message",
                    "sender_type": "ai",
                    "sender_name": speaker.name,
                    "message": line,
                    "message_id": message.id,
                },
            )
        self.stdout.write(f"[{room.name}] {a.name}と{b.name}が雑談しました")
