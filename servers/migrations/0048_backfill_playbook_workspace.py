import hashlib
import json

from django.db import migrations
from django.db.models.functions import Coalesce
from django.utils import timezone


def _content_hash(content_format, source_yaml, tasks, bundle_hash=""):
    payload = {
        "content_format": content_format,
        "source_yaml": source_yaml,
        "tasks": tasks if isinstance(tasks, list) else [],
        "bundle_hash": bundle_hash or "",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def interrupt_legacy_playbook_runs(apps, schema_editor=None):
    """Fail closed at cutover: never replay an in-flight legacy mutation."""

    PlaybookRun = apps.get_model("servers", "PlaybookRun")
    ManagedSecret = apps.get_model("core_ui", "ManagedSecret")
    run_ids = list(
        PlaybookRun.objects.filter(status__in=["pending", "running"]).values_list("id", flat=True)
    )
    if not run_ids:
        return 0
    now = timezone.now()
    ManagedSecret.objects.filter(
        namespace__in=["playbook_run_variables", "playbook_run_master_password"],
        object_id__in=run_ids,
    ).delete()
    PlaybookRun.objects.filter(id__in=run_ids).update(
        status="failed",
        error_message=(
            "Interrupted during durable playbook execution migration; "
            "the mutation was not replayed."
        ),
        summary={
            "interrupted": True,
            "reason": "durable_execution_migration",
            "replayed": False,
        },
        finished_at=now,
        terminal_notified_at=now,
        terminal_notification_claimed_at=None,
        terminal_notification_last_error="",
    )
    return len(run_ids)


def backfill_playbook_workspace(apps, schema_editor):
    Playbook = apps.get_model("servers", "Playbook")
    CompatibilityRevision = apps.get_model("servers", "PlaybookCompatibilityRevision")
    PlaybookRevision = apps.get_model("servers", "PlaybookRevision")
    PlaybookDraft = apps.get_model("servers", "PlaybookDraft")
    PlaybookGrant = apps.get_model("servers", "PlaybookGrant")
    PlaybookRun = apps.get_model("servers", "PlaybookRun")

    interrupt_legacy_playbook_runs(apps, schema_editor)

    # The outbox starts with this migration. Historical terminal runs must not
    # resume old Operator turns when the new worker performs its first sweep.
    PlaybookRun.objects.filter(
        status__in=["completed", "failed", "partial", "cancelled"],
        terminal_notified_at__isnull=True,
    ).update(terminal_notified_at=Coalesce("finished_at", "created_at"))

    for playbook in Playbook.objects.all().iterator(chunk_size=200):
        source_yaml = playbook.source_yaml or ""
        tasks = playbook.tasks if isinstance(playbook.tasks, list) else []
        content_format = "ansible_yaml" if playbook.kind == "ansible" or source_yaml else "runbook_json"
        origin_type = "template" if playbook.is_template_clone else ("imported" if source_yaml else "manual")
        origin = PlaybookRevision.objects.create(
            playbook_id=playbook.id,
            revision_number=1,
            author_id=playbook.user_id,
            content_format=content_format,
            source_yaml=source_yaml,
            tasks=tasks,
            content_hash=_content_hash(content_format, source_yaml, tasks),
            origin_type=origin_type,
            message="Initial revision migrated from legacy playbook content",
            metadata={"migration": "0048_backfill_playbook_workspace"},
        )

        published = origin
        stripped_source_hash = hashlib.sha256(source_yaml.strip().encode("utf-8")).hexdigest() if source_yaml else ""
        matching_compatibility = CompatibilityRevision.objects.filter(
            playbook_id=playbook.id,
            source_hash=stripped_source_hash,
        )
        matching_compatibility.update(source_revision_id=origin.id)

        active = None
        if playbook.active_compatibility_revision_id:
            active = CompatibilityRevision.objects.filter(id=playbook.active_compatibility_revision_id).first()
        if (
            active
            and active.status == "validated"
            and active.source_hash == stripped_source_hash
            and (active.adapted_yaml or "").strip()
        ):
            adapted_yaml = active.adapted_yaml
            published = PlaybookRevision.objects.create(
                playbook_id=playbook.id,
                revision_number=2,
                parent_id=origin.id,
                author_id=active.user_id,
                content_format="ansible_yaml",
                source_yaml=adapted_yaml,
                tasks=tasks,
                content_hash=_content_hash("ansible_yaml", adapted_yaml, tasks),
                origin_type="adaptation",
                message="Validated compatibility adaptation migrated from legacy history",
                metadata={
                    "migration": "0048_backfill_playbook_workspace",
                    "legacy_compatibility_revision_id": active.id,
                    "semantic_guard": active.semantic_guard if isinstance(active.semantic_guard, dict) else {},
                    "change_summary": active.change_summary if isinstance(active.change_summary, list) else [],
                },
            )
            CompatibilityRevision.objects.filter(id=active.id).update(result_revision_id=published.id)

        Playbook.objects.filter(id=playbook.id).update(
            origin_revision_id=origin.id,
            published_revision_id=published.id,
        )
        PlaybookDraft.objects.create(
            playbook_id=playbook.id,
            base_revision_id=published.id,
            content_format=published.content_format,
            source_yaml=published.source_yaml,
            tasks=published.tasks if isinstance(published.tasks, list) else [],
            content_hash=published.content_hash,
            version=1,
            last_editor_id=playbook.user_id,
        )

        if playbook.visibility == "shared":
            PlaybookGrant.objects.create(
                playbook_id=playbook.id,
                workspace_shared=True,
                role="operator",
                can_view=True,
                can_validate=True,
                can_run=True,
                can_export=True,
                is_legacy=True,
                granted_by_id=playbook.user_id,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0047_playbook_workspace"),
    ]

    operations = [
        migrations.RunPython(backfill_playbook_workspace, migrations.RunPython.noop),
    ]
