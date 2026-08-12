import hashlib
import json

from django.db import migrations, models
from django.db.models import Q


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


def migrate_invocation_statuses(apps, schema_editor):
    invocation = apps.get_model("core_ui", "AIProviderInvocation")
    invocation.objects.filter(status="completed").update(status="succeeded")
    invocation.objects.filter(status="auth_required").update(
        status="failed",
        error_code="provider_auth_required",
    )
    invocation.objects.filter(status="limit").update(
        status="failed",
        error_code="provider_quota_exceeded",
    )
    for row in invocation.objects.exclude(idempotency_key="").iterator():
        canonical = json.dumps(
            {
                "actor_user_id": row.user_id,
                "project_id": row.project_id,
                "source_kind": row.source_kind,
                "source_id": row.source_id,
                "purpose": row.purpose,
                "idempotency_key": row.idempotency_key,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        row.idempotency_scope = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        row.save(update_fields=["idempotency_scope"])


class Migration(migrations.Migration):
    dependencies = [("core_ui", "0027_aiconnectionauthflow_claimed_at_and_more")]

    operations = [
        migrations.AddField(
            model_name="aiconnectionauthflow",
            name="fencing_token",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="aiproviderinvocation",
            name="terminal_event",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="aiproviderinvocation",
            name="event_log",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="aiproviderinvocation",
            name="idempotency_scope",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.RemoveConstraint(
            model_name="aiproviderinvocation",
            name="cu_ai_invocation_idempotent",
        ),
        migrations.RunPython(migrate_invocation_statuses, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="aiproviderinvocation",
            constraint=models.UniqueConstraint(
                fields=("idempotency_scope",),
                condition=~Q(idempotency_scope=""),
                name="cu_ai_invocation_idempotent_scope",
            ),
        ),
        migrations.AlterField(
            model_name="aiproviderinvocation",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("leased", "Leased"),
                    ("running", "Running"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="queued",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="aiproviderinvocation",
            name="event_cursor",
            field=models.PositiveBigIntegerField(default=0),
        ),
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
