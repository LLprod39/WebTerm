import hashlib
import json
from datetime import UTC

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

GENESIS_HASH = "0" * 64
HASH_ALGORITHM = "sha256-v1"


def _canonical_timestamp(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _event_hash(event, *, run_ref, owner_user_ref, sequence_no, previous_hash):
    record = {
        "created_at": _canonical_timestamp(event.created_at),
        "event_type": event.event_type,
        "hash_algorithm": HASH_ALGORITHM,
        "message": event.message,
        "owner_user_ref": owner_user_ref,
        "payload": event.payload or {},
        "previous_hash": previous_hash,
        "run_ref": run_ref,
        "schema": "agent-run-event-v1",
        "sequence_no": sequence_no,
        "task_id": event.task_id,
    }
    payload = json.dumps(
        record,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def backfill_agent_event_chains(apps, schema_editor):
    AgentRun = apps.get_model("servers", "AgentRun")
    AgentRunEvent = apps.get_model("servers", "AgentRunEvent")
    run_owners = {
        row["id"]: row["user_id"] or row["agent__user_id"]
        for row in AgentRun.objects.values("id", "user_id", "agent__user_id")
    }
    current_run = None
    sequence_no = 0
    previous_hash = GENESIS_HASH
    pending_updates = []
    update_fields = (
        "run_ref",
        "owner_user_ref",
        "sequence_no",
        "previous_hash",
        "event_hash",
        "hash_algorithm",
    )
    for event in AgentRunEvent.objects.order_by("run_id", "created_at", "id").iterator(chunk_size=500):
        if event.run_id != current_run:
            current_run = event.run_id
            sequence_no = 0
            previous_hash = GENESIS_HASH
        sequence_no += 1
        owner_user_ref = run_owners.get(event.run_id)
        event_hash = _event_hash(
            event,
            run_ref=event.run_id,
            owner_user_ref=owner_user_ref,
            sequence_no=sequence_no,
            previous_hash=previous_hash,
        )
        event.run_ref = event.run_id
        event.owner_user_ref = owner_user_ref
        event.sequence_no = sequence_no
        event.previous_hash = previous_hash
        event.event_hash = event_hash
        event.hash_algorithm = HASH_ALGORITHM
        pending_updates.append(event)
        if len(pending_updates) >= 500:
            AgentRunEvent.objects.bulk_update(pending_updates, update_fields, batch_size=500)
            pending_updates.clear()
        previous_hash = event_hash
    if pending_updates:
        AgentRunEvent.objects.bulk_update(pending_updates, update_fields, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0050_agent_dispatch_max_attempts"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentrunevent",
            name="event_hash",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="agentrunevent",
            name="hash_algorithm",
            field=models.CharField(default=HASH_ALGORITHM, editable=False, max_length=20),
        ),
        migrations.AddField(
            model_name="agentrunevent",
            name="owner_user_ref",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="agentrunevent",
            name="previous_hash",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="agentrunevent",
            name="run_ref",
            field=models.PositiveBigIntegerField(null=True),
        ),
        migrations.AddField(
            model_name="agentrunevent",
            name="sequence_no",
            field=models.PositiveBigIntegerField(null=True),
        ),
        migrations.AlterField(
            model_name="agentrunevent",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now, editable=False),
        ),
        migrations.RunPython(backfill_agent_event_chains, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="agentrunevent",
            name="event_hash",
            field=models.CharField(max_length=64),
        ),
        migrations.AlterField(
            model_name="agentrunevent",
            name="previous_hash",
            field=models.CharField(max_length=64),
        ),
        migrations.AlterField(
            model_name="agentrunevent",
            name="run_ref",
            field=models.PositiveBigIntegerField(),
        ),
        migrations.AlterField(
            model_name="agentrunevent",
            name="sequence_no",
            field=models.PositiveBigIntegerField(),
        ),
        migrations.AlterField(
            model_name="agentrunevent",
            name="run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="events",
                to="servers.agentrun",
            ),
        ),
        migrations.AlterModelOptions(
            name="agentrunevent",
            options={
                "base_manager_name": "objects",
                "default_manager_name": "objects",
                "ordering": ["run_ref", "sequence_no"],
            },
        ),
        migrations.RemoveIndex(
            model_name="agentrunevent",
            name="servers_age_run_id_5b5cd7_idx",
        ),
        migrations.RemoveIndex(
            model_name="agentrunevent",
            name="servers_age_event_t_0cff98_idx",
        ),
        migrations.AddConstraint(
            model_name="agentrunevent",
            constraint=models.UniqueConstraint(
                fields=("run_ref", "sequence_no"),
                name="agent_event_run_sequence_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="agentrunevent",
            index=models.Index(fields=["run_ref", "sequence_no"], name="agent_evt_run_seq_idx"),
        ),
        migrations.AddIndex(
            model_name="agentrunevent",
            index=models.Index(fields=["event_type", "created_at"], name="agent_evt_type_time_idx"),
        ),
        migrations.AddIndex(
            model_name="agentrunevent",
            index=models.Index(fields=["event_hash"], name="agent_evt_hash_idx"),
        ),
    ]
