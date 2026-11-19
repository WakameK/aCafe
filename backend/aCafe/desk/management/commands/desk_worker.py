"""
焚火の世話係。AIの気まぐれな入室、火の管理、止まった接続の片付けなどを、一定間隔で繰り返す。

    python manage.py desk_worker            # 常駐(docker-compose の desk-worker サービスが実行する)
    python manage.py desk_worker --once     # 1回だけ(動作確認用)
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from desk import services, worker

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "焚火の世話(AIの出入り・火の管理・止まった接続の片付け)を一定間隔で行う"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="1回だけ実行して終わる")
        parser.add_argument("--interval", type=float, default=None, help="実行の間隔(秒)")

    def handle(self, *args, **options):
        interval = options["interval"] or services.cfg("DESK_TICK_SECONDS", 15)
        self.stdout.write(f"desk_worker 開始(間隔 {interval} 秒)")
        while True:
            try:
                close_old_connections()
                worker.run_tick()
            except Exception:
                # マイグレーション前でテーブルが無い、DBがロックされているなど。次の回でやり直す
                logger.warning("desk tick failed", exc_info=True)
            if options["once"]:
                break
            time.sleep(interval)
