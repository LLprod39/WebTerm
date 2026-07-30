from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0049_server_ai_read_only_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentrundispatch",
            name="max_attempts",
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddConstraint(
            model_name="agentrundispatch",
            constraint=models.CheckConstraint(
                condition=models.Q(("max_attempts__gte", 1)),
                name="agent_dispatch_max_attempts_gte_1",
            ),
        ),
    ]
