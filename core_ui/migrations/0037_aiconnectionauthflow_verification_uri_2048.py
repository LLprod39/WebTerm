from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core_ui", "0036_add_antigravity_subscription_target"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiconnectionauthflow",
            name="verification_uri",
            field=models.URLField(blank=True, default="", max_length=2048),
        ),
    ]
