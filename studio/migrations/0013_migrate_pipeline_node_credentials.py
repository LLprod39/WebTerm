from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import migrations

NAMESPACE = "studio_pipeline_secrets"
SECRET_FIELDS = ("bot_token", "tg_bot_token", "telegram_bot_token", "smtp_password")


def _fernet() -> Fernet:
    seed = os.getenv("MANAGED_SECRET_KEY") or os.getenv("APP_SECRET_ENCRYPTION_KEY") or settings.SECRET_KEY
    digest = hashlib.sha256(f"{seed}:managed-secret:v1".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def _sanitize_nodes(nodes, *, collect_secrets: bool) -> tuple[object, dict[str, dict[str, str]]]:
    if not isinstance(nodes, list):
        return nodes, {}
    secrets_by_node: dict[str, dict[str, str]] = {}
    safe_nodes = []
    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            safe_nodes.append(raw_node)
            continue
        node = dict(raw_node)
        node_id = str(node.get("id") or "").strip()
        data = dict(node.get("data") or {}) if isinstance(node.get("data"), dict) else {}
        node_secrets: dict[str, str] = {}
        for secret_key in SECRET_FIELDS:
            raw_value = data.pop(secret_key, None)
            data.pop(f"{secret_key}_clear", None)
            value = str(raw_value or "").strip()
            if value:
                data[f"{secret_key}_configured"] = True
                if collect_secrets and node_id:
                    node_secrets[secret_key] = value
        if node_id and node_secrets:
            secrets_by_node[node_id] = node_secrets
        node["data"] = data
        safe_nodes.append(node)
    return safe_nodes, secrets_by_node


def _redact_secret_values(value):
    if isinstance(value, dict):
        redacted = {
            str(key): _redact_secret_values(item)
            for key, item in value.items()
            if str(key) not in SECRET_FIELDS and not any(str(key) == f"{field}_clear" for field in SECRET_FIELDS)
        }
        for secret_key in SECRET_FIELDS:
            if str(value.get(secret_key) or "").strip():
                redacted[f"{secret_key}_configured"] = True
        return redacted
    if isinstance(value, list):
        return [_redact_secret_values(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_secret_values(item) for item in value]
    return value


def migrate_pipeline_credentials(apps, _schema_editor):
    Pipeline = apps.get_model("studio", "Pipeline")
    PipelineDraftRevision = apps.get_model("studio", "PipelineDraftRevision")
    PipelineDraftSession = apps.get_model("studio", "PipelineDraftSession")
    PipelineRun = apps.get_model("studio", "PipelineRun")
    ManagedSecret = apps.get_model("core_ui", "ManagedSecret")

    for pipeline in Pipeline.objects.all().only("id", "nodes").iterator(chunk_size=200):
        safe_nodes, secrets_by_node = _sanitize_nodes(pipeline.nodes, collect_secrets=True)
        Pipeline.objects.filter(pk=pipeline.pk).update(nodes=safe_nodes)
        if not secrets_by_node:
            continue
        secret_names = sorted(
            f"{node_id}:{key}" for node_id, values in secrets_by_node.items() for key in values
        )
        ManagedSecret.objects.update_or_create(
            namespace=NAMESPACE,
            object_id=pipeline.pk,
            key="default",
            defaults={
                "ciphertext": _encrypt({"nodes": secrets_by_node}),
                "metadata": {"kind": "studio_pipeline_node_credentials", "secret_names": secret_names},
            },
        )

    for run in PipelineRun.objects.all().only("id", "nodes_snapshot", "node_states").iterator(chunk_size=200):
        safe_nodes, _ignored = _sanitize_nodes(run.nodes_snapshot, collect_secrets=False)
        node_states = run.node_states if isinstance(run.node_states, dict) else {}
        safe_states = {}
        for node_id, raw_state in node_states.items():
            if not isinstance(raw_state, dict):
                safe_states[node_id] = raw_state
                continue
            state = dict(raw_state)
            state.pop("bot_token", None)
            safe_states[node_id] = state
        PipelineRun.objects.filter(pk=run.pk).update(nodes_snapshot=safe_nodes, node_states=safe_states)

    for draft in PipelineDraftSession.objects.all().only("id", "current_graph_snapshot").iterator(chunk_size=200):
        PipelineDraftSession.objects.filter(pk=draft.pk).update(
            current_graph_snapshot=_redact_secret_values(draft.current_graph_snapshot)
        )

    revision_json_fields = (
        "node_patch",
        "graph_patch",
        "preview_nodes",
        "resource_plan",
        "node_explanations",
        "response_payload",
    )
    for revision in PipelineDraftRevision.objects.all().only("id", *revision_json_fields).iterator(chunk_size=200):
        PipelineDraftRevision.objects.filter(pk=revision.pk).update(
            **{field: _redact_secret_values(getattr(revision, field)) for field in revision_json_fields}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core_ui", "0021_alter_groupapppermission_feature_and_more"),
        ("studio", "0012_alter_agentconfig_skill_slugs"),
    ]

    operations = [
        migrations.RunPython(migrate_pipeline_credentials, migrations.RunPython.noop),
    ]
