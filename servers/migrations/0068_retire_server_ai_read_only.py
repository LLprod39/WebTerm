from django.db import migrations


def retire_ai_read_only(apps, schema_editor):
    Server = apps.get_model("servers", "Server")
    Server.objects.filter(ai_read_only=True).update(ai_read_only=False)


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0067_agentrun_execution_outcome"),
    ]

    operations = [
        migrations.RunPython(retire_ai_read_only, migrations.RunPython.noop),
    ]
