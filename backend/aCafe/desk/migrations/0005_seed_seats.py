from django.db import migrations

DEFAULT_SEATS = [
    ("カウンター席1", 2),
    ("カウンター席2", 2),
    ("カウンター席3", 2),
    ("テーブル席A", 4),
    ("テーブル席B", 4),
    ("ソファ席", 4),
]


def seed_seats(apps, schema_editor):
    Seat = apps.get_model("desk", "Seat")
    for label, capacity in DEFAULT_SEATS:
        Seat.objects.get_or_create(label=label, defaults={"capacity": capacity})


class Migration(migrations.Migration):

    dependencies = [
        ("desk", "0004_room_extras_and_seat"),
    ]

    operations = [
        migrations.RunPython(seed_seats, migrations.RunPython.noop),
    ]
