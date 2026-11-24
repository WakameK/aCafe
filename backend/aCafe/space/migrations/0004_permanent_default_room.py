from django.db import migrations


def mark_permanent(apps, schema_editor):
    SpaceRoom = apps.get_model("space", "SpaceRoom")
    SpaceRoom.objects.filter(slug="campfire").update(is_permanent=True)


def unmark_permanent(apps, schema_editor):
    SpaceRoom = apps.get_model("space", "SpaceRoom")
    SpaceRoom.objects.filter(slug="campfire").update(is_permanent=False)


class Migration(migrations.Migration):
    dependencies = [
        ("space", "0003_fire"),
    ]

    operations = [
        migrations.RunPython(mark_permanent, unmark_permanent),
    ]