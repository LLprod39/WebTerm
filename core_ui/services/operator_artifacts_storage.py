"""CRUD + extraction of Operator chat artifacts (playbooks/scripts)."""

from __future__ import annotations

from typing import Any

from core_ui.models import ChatArtifact, ChatMessage, ChatSession


def serialize_artifact(artifact: ChatArtifact) -> dict[str, Any]:
    return {
        "id": artifact.pk,
        "session_id": artifact.session_id,
        "message_id": artifact.message_id,
        "kind": artifact.kind,
        "title": artifact.title,
        "content": artifact.content,
        "version": artifact.version,
        "metadata": artifact.metadata or {},
        "saved_playbook_id": artifact.saved_playbook_id,
        "created_at": artifact.created_at.isoformat(),
        "updated_at": artifact.updated_at.isoformat(),
    }


def list_artifacts(session: ChatSession) -> list[dict[str, Any]]:
    rows = session.artifacts.order_by("-updated_at", "-id")[:50]
    return [serialize_artifact(a) for a in rows]


def create_artifact(
    *,
    session: ChatSession,
    kind: str,
    title: str,
    content: str,
    message: ChatMessage | None = None,
    metadata: dict | None = None,
) -> ChatArtifact:
    kind_norm = str(kind or ChatArtifact.KIND_OTHER).strip().lower()
    allowed = {c[0] for c in ChatArtifact.KIND_CHOICES}
    if kind_norm not in allowed:
        kind_norm = ChatArtifact.KIND_OTHER
    return ChatArtifact.objects.create(
        session=session,
        message=message,
        kind=kind_norm,
        title=(title or "Artifact")[:200],
        content=content or "",
        version=1,
        metadata=metadata or {},
    )


def update_artifact_content(
    artifact: ChatArtifact,
    *,
    content: str,
    title: str | None = None,
    bump_version: bool = True,
) -> ChatArtifact:
    artifact.content = content or ""
    if title is not None:
        artifact.title = title[:200]
    if bump_version:
        artifact.version = int(artifact.version or 1) + 1
    fields = ["content", "updated_at"]
    if title is not None:
        fields.append("title")
    if bump_version:
        fields.append("version")
    artifact.save(update_fields=fields)
    return artifact


def get_artifact_for_user(user, artifact_id: int) -> ChatArtifact | None:
    return ChatArtifact.objects.select_related("session").filter(pk=artifact_id, session__user=user).first()


def extract_artifacts_from_tool_result(
    *,
    session: ChatSession,
    message: ChatMessage | None,
    action_type: str,
    result: dict[str, Any],
) -> list[ChatArtifact]:
    """Best-effort: persist yaml/scripts from tool results as artifacts."""
    created: list[ChatArtifact] = []
    if not isinstance(result, dict):
        return created
    # Nested result from execute_tool wrap
    payload = result.get("result") if isinstance(result.get("result"), dict) else result

    yaml_text = str(payload.get("yaml") or payload.get("source_yaml") or "").strip()
    if yaml_text and ("playbook" in action_type or "ansible" in action_type or yaml_text.startswith("---")):
        created.append(
            create_artifact(
                session=session,
                kind=ChatArtifact.KIND_ANSIBLE,
                title=str(payload.get("name") or payload.get("title") or "Ansible playbook")[:200],
                content=yaml_text,
                message=message,
                metadata={"source_action": action_type},
            )
        )

    script = str(payload.get("script") or "").strip()
    if script:
        created.append(
            create_artifact(
                session=session,
                kind=ChatArtifact.KIND_SCRIPT,
                title=str(payload.get("title") or "Script")[:200],
                content=script,
                message=message,
                metadata={"source_action": action_type},
            )
        )

    # create_playbook returns playbook without yaml in body sometimes
    pb = payload.get("playbook") if isinstance(payload.get("playbook"), dict) else None
    if pb and pb.get("id") and not created:
        created.append(
            create_artifact(
                session=session,
                kind=ChatArtifact.KIND_ANSIBLE if pb.get("kind") == "ansible" else ChatArtifact.KIND_OTHER,
                title=str(pb.get("name") or f"Playbook #{pb['id']}")[:200],
                content=f"# playbook_id={pb['id']}\n# Open in Playbooks UI to edit\n",
                message=message,
                metadata={"playbook_id": pb["id"], "source_action": action_type},
            )
        )
        if created:
            created[-1].saved_playbook_id = int(pb["id"])
            created[-1].save(update_fields=["saved_playbook_id", "updated_at"])

    return created
