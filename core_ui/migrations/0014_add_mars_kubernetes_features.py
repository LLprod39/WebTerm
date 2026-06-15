from django.db import migrations, models


FEATURE_CHOICES = [
    ("servers", "Servers"),
    ("dashboard", "Dashboard"),
    ("agents", "Agents"),
    ("studio", "Studio"),
    ("studio_pipelines", "Studio Pipelines"),
    ("studio_runs", "Studio Runs"),
    ("studio_agents", "Studio Agents"),
    ("studio_skills", "Studio Skills"),
    ("studio_mcp", "Studio MCP"),
    ("studio_notifications", "Studio Notifications"),
    ("kubernetes", "Kubernetes"),
    ("mars", "MARS"),
    ("settings", "Settings"),
    ("orchestrator", "Orchestrator"),
    ("knowledge_base", "Knowledge Base"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("core_ui", "0013_dashboardlayout"),
    ]

    operations = [
        migrations.AlterField(
            model_name="groupapppermission",
            name="feature",
            field=models.CharField(choices=FEATURE_CHOICES, max_length=30),
        ),
        migrations.AlterField(
            model_name="userapppermission",
            name="feature",
            field=models.CharField(choices=FEATURE_CHOICES, max_length=30),
        ),
    ]
