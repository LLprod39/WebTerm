from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_ui", "0019_operator_chat"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatturnstate",
            name="status",
            field=models.CharField(
                choices=[
                    ("running", "Running"),
                    ("awaiting_confirm", "Awaiting confirm"),
                    ("awaiting_async", "Awaiting async"),
                    ("resuming", "Resuming"),
                    ("done", "Done"),
                    ("failed", "Failed"),
                    ("limit", "Limit"),
                ],
                default="running",
                max_length=30,
            ),
        ),
    ]
