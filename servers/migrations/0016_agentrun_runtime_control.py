from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0015_alter_agentrun_server"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentrun",
            name="runtime_control",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Runtime control mailbox for cross-process run control: "
                    "{stop_requested, pause_requested, reply_nonce, reply_ack_nonce, reply_text}"
                ),
            ),
        ),
    ]
