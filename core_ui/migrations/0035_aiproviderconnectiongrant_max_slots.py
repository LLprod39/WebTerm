from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_ui", "0034_chatsession_kind_telegram"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiproviderconnectiongrant",
            name="max_slots",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="aiproviderconnectiongrant",
            constraint=models.CheckConstraint(
                condition=models.Q(max_slots__isnull=True)
                | models.Q(max_slots__gte=1, max_slots__lte=8),
                name="cu_ai_grant_max_slots_range",
            ),
        ),
    ]
