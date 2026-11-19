from django.db import migrations

# 最初からAIたちがいる机。AIの入室・雑談・退室は desk_worker が動かす
AMBIENT_DESKS = [
    {"name": "窓辺の机", "topic": "のんびり雑談中"},
    {"name": "奥の机", "topic": "ひと休みしている人たちの机"},
]


def seed_desks(apps, schema_editor):
    Room = apps.get_model("desk", "Room")

    # 席数が固定だった頃の部屋は、一覧から外す。発言ログはDBにそのまま残る
    Room.objects.filter(is_archived=False).update(is_archived=True)

    if not Room.objects.filter(kind="ambient").exists():
        for desk in AMBIENT_DESKS:
            Room.objects.create(
                name=desk["name"],
                topic=desk["topic"],
                kind="ambient",
                capacity=6,
                mode="talk",
            )


def noop(apps, schema_editor):
    # 巻き戻しでは何もしない(片付けた部屋を勝手に復活させないため)
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("desk", "0006_rebuild_desk"),
    ]

    operations = [
        migrations.RunPython(seed_desks, noop),
    ]
