from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core_ui", "0028_ai_provider_pilot_safety")]

    operations = [
        migrations.AddField(
            model_name="aiproviderpreference",
            name="reasoning_effort",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
