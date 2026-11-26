import django.db.models.deletion
from django.db import migrations, models

DEFAULT_TABLES = [
    "ゆるく雑談",
    "今日あったこと",
    "おすすめの本・音楽・食べもの",
    "ひとりごと",
]


def replace_seats_with_tables(apps, schema_editor):
    """定員つきの座席(カウンター席など)は話題ごとのテーブルに置き換える。部屋と発言ログは残す。"""
    Table = apps.get_model("desk", "Table")
    Table.objects.all().delete()
    for name in DEFAULT_TABLES:
        Table.objects.create(name=name, is_permanent=True)


class Migration(migrations.Migration):

    dependencies = [
        ("desk", "0006_presence_lease"),
    ]

    operations = [
        migrations.RenameModel(old_name="Seat", new_name="Table"),
        migrations.RenameField(model_name="table", old_name="label", new_name="name"),
        migrations.AlterField(
            model_name="table",
            name="name",
            field=models.CharField(max_length=30),
        ),
        migrations.RemoveField(model_name="table", name="capacity"),
        migrations.AddField(
            model_name="table",
            name="is_permanent",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="table",
            name="room",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="table",
                to="desk.room",
            ),
        ),
        migrations.RunPython(replace_seats_with_tables, migrations.RunPython.noop),
    ]
