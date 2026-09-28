from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("servers", "0069_commandsnapshot_file_existed")]

    operations = [
        migrations.AddField(
            model_name="server",
            name="os_type",
            field=models.CharField(
                choices=[("linux", "Linux"), ("windows", "Windows")],
                default="linux",
                help_text="OS family for the SSH shell: linux (bash) or windows (PowerShell).",
                max_length=16,
            ),
        ),
    ]
