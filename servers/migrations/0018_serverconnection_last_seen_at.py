from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0017_server_trusted_host_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="serverconnection",
            name="last_seen_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddIndex(
            model_name="serverconnection",
            index=models.Index(fields=["user", "status", "-last_seen_at"], name="servers_ser_user_id_05b6d3_idx"),
        ),
        migrations.AddIndex(
            model_name="serverconnection",
            index=models.Index(fields=["status", "-last_seen_at"], name="servers_ser_status_d1ba92_idx"),
        ),
    ]
