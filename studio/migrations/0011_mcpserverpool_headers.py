from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studio", "0010_agentconfig_sudo_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcpserverpool",
            name="headers",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    'Extra HTTP headers for SSE transport, e.g. {"X-Api-Version": "1"}. '
                    "For auth, store MCP_BEARER_TOKEN / MCP_AUTHORIZATION as a managed secret instead."
                ),
            ),
        ),
    ]
