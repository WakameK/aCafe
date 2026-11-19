from django.db import migrations

# 最初からAIたちがいる焚火。AIの入室・雑談・退室は desk_worker が動かす
AMBIENT_FIRES = [
    {"name": "窓辺の焚火", "topic": "のんびり雑談中"},
    {"name": "奥の焚火", "topic": "ひと休みしている人たち"},
]


def seed_fires(apps, schema_editor):
    Room = apps.get_model("desk", "Room")

    # 席数が固定だった頃の部屋は「legacy」にして、一覧から外す(発言ログはそのまま残る)
    Room.objects.exclude(kind__in=["ambient", "legacy"]).update(kind="legacy")

    if not Room.objects.filter(kind="ambient").exists():
        for fire in AMBIENT_FIRES:
            Room.objects.create(
                name=fire["name"],
                topic=fire["topic"],
                kind="ambient",
                capacity=6,
                mode="talk",
                fire_level=0.7,
            )


def noop(apps, schema_editor):
    # 巻き戻しでは何もしない(legacyにした部屋を勝手に戻さないため)
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("desk", "0006_rebuild_as_fire"),
    ]

    operations = [
        migrations.RunPython(seed_fires, noop),
    ]
