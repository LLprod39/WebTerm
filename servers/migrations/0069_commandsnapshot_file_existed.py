from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("servers", "0068_retire_server_ai_read_only")]

    operations = [
        migrations.AddField(
            model_name="commandsnapshot",
            name="file_existed",
            field=models.BooleanField(
                null=True,
                default=None,
                help_text="Whether the file existed before the command; unknown for legacy captures",
            ),
        ),
    ]
