from django.db import migrations

# いまのUnityビルドは ws://localhost:8000/ws/space/campfire/ に固定でつなぐ。
# consumer はDBにある部屋にしか入れないので、最初の部屋として campfire を用意しておく。
DEFAULT_SLUG = "campfire"
DEFAULT_NAME = "はじまりの焚火"


def create_default_room(apps, schema_editor):
    SpaceRoom = apps.get_model("space", "SpaceRoom")
    SpaceRoom.objects.get_or_create(slug=DEFAULT_SLUG, defaults={"name": DEFAULT_NAME})


def delete_default_room(apps, schema_editor):
    SpaceRoom = apps.get_model("space", "SpaceRoom")
    SpaceRoom.objects.filter(slug=DEFAULT_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("space", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_room, delete_default_room),
    ]
