# Generated manually for Telegram notification + AI assistant features.

from django.db import migrations, models


FEATURE_CHOICES = [
    ("servers", "Servers"),
    ("dashboard", "Dashboard"),
    ("agents", "Agents"),
    ("chat", "Chat"),
    ("automation", "Automation"),
    ("ai_connections_personal", "Personal AI Connections"),
    ("ai_connections_admin", "AI Connections Administration"),
    ("studio", "Studio"),
    ("studio_pipelines", "Studio Pipelines"),
    ("studio_runs", "Studio Runs"),
    ("studio_agents", "Studio Agents"),
    ("studio_skills", "Studio Skills"),
    ("studio_mcp", "Studio MCP"),
    ("studio_notifications", "Studio Notifications"),
    ("telegram_notifications", "Telegram Notifications"),
    ("telegram_assistant", "Telegram AI Assistant"),
    ("kubernetes", "Kubernetes"),
    ("kubernetes_admin_read", "Kubernetes Admin Read"),
    ("kubernetes_admin_write", "Kubernetes Admin Write"),
    ("kubernetes_break_glass", "Kubernetes Break Glass"),
    ("kubernetes_secret_read", "Kubernetes Secret Read"),
    ("mars", "MARS"),
    ("settings", "Settings"),
    ("orchestrator", "Orchestrator"),
    ("knowledge_base", "Knowledge Base"),
    ("web_research", "Web Research"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("core_ui", "0032_add_cursor_subscription_target"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userapppermission",
            name="feature",
            field=models.CharField(choices=FEATURE_CHOICES, max_length=30),
        ),
        migrations.AlterField(
            model_name="groupapppermission",
            name="feature",
            field=models.CharField(choices=FEATURE_CHOICES, max_length=30),
        ),
    ]
