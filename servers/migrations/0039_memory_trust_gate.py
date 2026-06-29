from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


def archive_duplicate_active_snapshots(apps, schema_editor):
    ServerMemorySnapshot = apps.get_model("servers", "ServerMemorySnapshot")
    duplicates = (
        ServerMemorySnapshot.objects.filter(is_active=True)
        .values("server_id", "memory_key")
        .annotate(count=models.Count("id"))
        .filter(count__gt=1)
    )
    for duplicate in duplicates:
        items = list(
            ServerMemorySnapshot.objects.filter(
                server_id=duplicate["server_id"],
                memory_key=duplicate["memory_key"],
                is_active=True,
            ).order_by("-version", "-updated_at", "-id")
        )
        for stale in items[1:]:
            stale.is_active = False
            stale.layer = "archive"
            stale.save(update_fields=["is_active", "layer", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0038_add_scheduled_agents_worker_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="servermemoryevent",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="servermemoryevent",
            name="idempotency_key",
            field=models.CharField(blank=True, db_index=True, max_length=180),
        ),
        migrations.AddField(
            model_name="servermemoryevent",
            name="payload_hash",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="servermemoryevent",
            name="compacted_episode",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="compacted_events",
                to="servers.servermemoryepisode",
            ),
        ),
        migrations.AddField(
            model_name="servermemoryevent",
            name="compacted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servermemoryevent",
            name="compaction_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="servermemorysnapshot",
            name="layer",
            field=models.CharField(
                choices=[("canonical", "Canonical"), ("candidate", "Candidate"), ("archive", "Archive")],
                default="canonical",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="servermemoryrevalidation",
            name="status",
            field=models.CharField(
                choices=[
                    ("open", "Open"),
                    ("scheduled", "Scheduled"),
                    ("verified_true", "Verified True"),
                    ("verified_false", "Verified False"),
                    ("resolved", "Resolved (legacy)"),
                    ("superseded", "Superseded"),
                    ("expired_unverified", "Expired Unverified"),
                    ("ignored_by_human", "Ignored by Human"),
                ],
                default="open",
                max_length=20,
            ),
        ),
        migrations.RunPython(archive_duplicate_active_snapshots, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="servermemoryevent",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("idempotency_key", "")),
                fields=("server", "idempotency_key"),
                name="uniq_server_memory_event_idempotency_key",
            ),
        ),
        migrations.AddConstraint(
            model_name="servermemorysnapshot",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("server", "memory_key"),
                name="uniq_active_server_memory_snapshot",
            ),
        ),
    ]
