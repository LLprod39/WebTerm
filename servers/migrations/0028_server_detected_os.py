from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0027_add_command_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="server",
            name="detected_os",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Detected distro slug aligned with frontend ServerOsKind",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="server",
            name="detected_os_meta",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="OS detection metadata: id, version, pretty_name, detected_at, uname, ...",
            ),
        ),
    ]
