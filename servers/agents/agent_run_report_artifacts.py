import json
from typing import Any

from django.utils import timezone

from servers.agents.agent_run_report_base import (
    ARTIFACT_CONTENT_LIMIT,
    ARTIFACT_MANIFEST_KEY,
    REPORT_SCHEMA_VERSION,
    _bytes_label,
    _json_safe,
    _sha256_text,
    _text,
)
from servers.agents.agent_run_report_execution import _serialize_run
from servers.models import AgentRun, AgentRunArtifact


def _build_artifact_state(report_state: dict[str, Any]) -> dict[str, Any]:
    if report_state.get("artifacts_ready"):
        return {
            "ready": True,
            "title": "Артефакты отчёта готовы",
            "description": "Файлы собраны из финального отчёта и сохранённых данных запуска.",
            "empty_title": "",
            "empty_description": "",
        }
    return {
        "ready": False,
        "title": "Артефакты ещё не готовы",
        "description": "Артефакты появятся только после того, как агент сохранит финальный markdown-отчёт.",
        "empty_title": "Артефакты появятся после финального отчёта",
        "empty_description": report_state.get("next_expected") or "Дождитесь завершения агента.",
    }


def _build_artifact_state_for_artifacts(
    run: AgentRun,
    report_state: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    artifact_state = _build_artifact_state(report_state)
    total_size = sum(int(item.get("size_bytes") or 0) for item in artifacts)
    server_artifact_count = sum(1 for item in artifacts if item.get("download_kind") == "server")
    artifact_state.update(
        {
            "bundle_ready": bool(server_artifact_count),
            "bundle_download_url": _artifact_bundle_download_url(run.id) if server_artifact_count else "",
            "artifact_count": server_artifact_count or len(artifacts),
            "total_size_bytes": total_size,
            "total_size_label": _bytes_label(total_size),
            "manifest_ready": any(item.get("id") == ARTIFACT_MANIFEST_KEY for item in artifacts),
            "manifest_name": "artifact-manifest.json"
            if any(item.get("id") == ARTIFACT_MANIFEST_KEY for item in artifacts)
            else "",
        }
    )
    return artifact_state


def _artifact(
    id_: str, name: str, type_: str, description: str, content: str, created_at: str | None
) -> dict[str, Any]:
    original_size = len(content.encode("utf-8", errors="replace"))
    safe_content = content
    truncated = False
    if len(safe_content) > ARTIFACT_CONTENT_LIMIT:
        safe_content = safe_content[: ARTIFACT_CONTENT_LIMIT - 1].rstrip() + "…"
        truncated = True
    encoded_size = len(safe_content.encode("utf-8", errors="replace"))
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "description": description,
        "size_bytes": encoded_size,
        "original_size_bytes": original_size,
        "size_label": _bytes_label(encoded_size),
        "created_at": created_at,
        "artifact_id": None,
        "download_kind": "inline",
        "download_url": "",
        "content_type": "application/json" if name.endswith(".json") else "text/markdown",
        "content": safe_content,
        "truncated": truncated,
        "checksum_sha256": _sha256_text(safe_content),
    }


def _build_artifact_manifest(run: AgentRun, artifacts: list[dict[str, Any]], created_at: str | None) -> dict[str, Any]:
    manifest_items = []
    total_size = 0
    for item in artifacts:
        if item.get("id") == ARTIFACT_MANIFEST_KEY:
            continue
        size_bytes = int(item.get("size_bytes") or 0)
        total_size += size_bytes
        manifest_items.append(
            {
                "key": str(item.get("id") or ""),
                "name": str(item.get("name") or ""),
                "type": str(item.get("type") or ""),
                "content_type": str(item.get("content_type") or ""),
                "size_bytes": size_bytes,
                "checksum_sha256": str(item.get("checksum_sha256") or _sha256_text(str(item.get("content") or ""))),
                "truncated": bool(item.get("truncated")),
            }
        )
    content = json.dumps(
        _json_safe(
            {
                "schema_version": REPORT_SCHEMA_VERSION,
                "kind": "agent_run_artifact_manifest",
                "run_id": run.id,
                "agent_id": run.agent_id,
                "agent_name": run.agent.name if run.agent_id and run.agent else "Agent",
                "status": run.status,
                "generated_at": timezone.now().isoformat(),
                "artifact_count": len(manifest_items),
                "total_size_bytes": total_size,
                "artifacts": manifest_items,
            }
        ),
        ensure_ascii=False,
        indent=2,
    )
    return _artifact(
        ARTIFACT_MANIFEST_KEY,
        "artifact-manifest.json",
        "JSON",
        "Integrity manifest with artifact sizes and SHA-256 checksums.",
        content,
        created_at,
    )


def _build_artifacts(
    run: AgentRun,
    *,
    markdown: str,
    events: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    created_at = (
        run.completed_at.isoformat() if run.completed_at else run.started_at.isoformat() if run.started_at else None
    )
    context = {
        "run": _serialize_run(run),
        "report": {key: value for key, value in report.items() if key not in {"markdown"}},
        "agent_steps": steps,
    }
    artifacts = [
        _artifact(
            "run-context",
            "run-context.json",
            "JSON",
            "Normalized run metadata and structured report context.",
            json.dumps(_json_safe(context), ensure_ascii=False, indent=2),
            created_at,
        ),
        _artifact(
            "commands-output",
            "commands-output.json",
            "JSON",
            "Command output captured during the run.",
            json.dumps(_json_safe(logs), ensure_ascii=False, indent=2),
            created_at,
        ),
        _artifact(
            "events",
            "events.json",
            "JSON",
            "Persistent agent events for this run.",
            json.dumps(_json_safe(events), ensure_ascii=False, indent=2),
            created_at,
        ),
    ]
    if markdown.strip():
        artifacts.insert(
            0,
            _artifact("final-report", "final-report.md", "Markdown", "Readable final report.", markdown, created_at),
        )
    artifacts.append(_build_artifact_manifest(run, artifacts, created_at))
    return artifacts


def _artifact_download_url(run_id: int, artifact_id: int) -> str:
    return f"/servers/api/agents/runs/{run_id}/artifacts/{artifact_id}/download/"


def _artifact_bundle_download_url(run_id: int) -> str:
    return f"/servers/api/agents/runs/{run_id}/artifacts/download-all/"


def _build_persisted_artifacts(run: AgentRun) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []

    def sort_key(artifact: AgentRunArtifact) -> tuple[int, str, int]:
        metadata = artifact.metadata if isinstance(artifact.metadata, dict) else {}
        try:
            position = int(metadata.get("position", 99))
        except (TypeError, ValueError):
            position = 99
        return position, artifact.name, artifact.id

    for artifact in sorted(AgentRunArtifact.objects.filter(run=run), key=sort_key):
        metadata = artifact.metadata if isinstance(artifact.metadata, dict) else {}
        artifacts.append(
            {
                "id": artifact.artifact_key,
                "name": artifact.name,
                "type": artifact.artifact_type,
                "description": artifact.description,
                "size_bytes": int(artifact.size_bytes or 0),
                "original_size_bytes": int(metadata.get("original_size_bytes") or artifact.size_bytes or 0),
                "size_label": _bytes_label(int(artifact.size_bytes or 0)),
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                "artifact_id": artifact.id,
                "download_kind": "server",
                "download_url": _artifact_download_url(run.id, artifact.id),
                "content_type": artifact.content_type,
                "content": "",
                "truncated": bool(artifact.truncated),
                "checksum_sha256": _text(metadata.get("checksum_sha256") or "", limit=80),
                "metadata": _json_safe(metadata),
            }
        )
    return artifacts


def _artifact_owner_id(run: AgentRun) -> int | None:
    if run.user_id:
        return run.user_id
    if run.agent_id and run.agent:
        return run.agent.user_id
    return None


def _sync_agent_run_artifacts(run: AgentRun, artifacts: list[dict[str, Any]]) -> None:
    if not run.pk:
        return
    owner_id = _artifact_owner_id(run)
    synced_keys: set[str] = set()
    for position, item in enumerate(artifacts):
        artifact_key = _text(item.get("id") or item.get("name") or "artifact", limit=80) or "artifact"
        content = str(item.get("content") or "")
        size_bytes = len(content.encode("utf-8", errors="replace"))
        checksum_sha256 = str(item.get("checksum_sha256") or _sha256_text(content))
        synced_keys.add(artifact_key)
        AgentRunArtifact.objects.update_or_create(
            run=run,
            artifact_key=artifact_key,
            defaults={
                "user_id": owner_id,
                "name": _text(item.get("name") or f"{artifact_key}.txt", limit=255),
                "artifact_type": _text(item.get("type") or "Text", limit=40),
                "description": _text(item.get("description") or "", limit=1000),
                "content_type": _text(item.get("content_type") or "text/plain;charset=utf-8", limit=120),
                "content": content,
                "size_bytes": size_bytes,
                "truncated": bool(item.get("truncated")),
                "metadata": {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "source": "agent_run_report",
                    "position": position,
                    "checksum_sha256": checksum_sha256,
                    "original_size_bytes": int(item.get("original_size_bytes") or size_bytes),
                    "manifest": artifact_key == ARTIFACT_MANIFEST_KEY,
                },
            },
        )
    AgentRunArtifact.objects.filter(run=run).exclude(artifact_key__in=synced_keys).delete()


__all__ = [name for name in globals() if not name.startswith("__")]
