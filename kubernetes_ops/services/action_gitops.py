from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from kubernetes_ops.models import K8sCluster
from kubernetes_ops.services.action_errors import ActionRequestValidationError
from kubernetes_ops.services.action_sanitizers import bounded_action_text

MAX_TEXT = 500
GITOPS_ALLOWED_PATH_RE = re.compile(r"^[A-Za-z0-9._/@+=:-]+$")


def gitops_merge_request_preview(
    *,
    target: dict[str, Any],
    cluster: K8sCluster | None,
    summary: str,
) -> tuple[K8sCluster | None, dict[str, Any], dict[str, Any]]:
    repository = _safe_repository_url(target.get("repository") or target.get("repo") or "")
    repository_ref = _repository_ref(repository)
    path = _safe_repo_path(target.get("path") or target.get("file") or target.get("chart_path") or "")
    source_branch = _safe_branch_name(target.get("source_branch") or target.get("branch") or "")
    target_branch = _safe_branch_name(target.get("target_branch") or target.get("base_branch") or "main")
    title = _bounded_text(target.get("title") or "Kubernetes GitOps change request", limit=120)
    changes = _gitops_changes(target, default_path=path)

    if not path:
        raise ActionRequestValidationError(
            "GitOps merge request requires a repository path.",
            code="gitops_path_required",
            payload={"target": target},
        )
    if not source_branch:
        raise ActionRequestValidationError(
            "GitOps merge request requires a source branch.",
            code="gitops_source_branch_required",
            payload={"target": target},
        )
    if source_branch == target_branch:
        raise ActionRequestValidationError(
            "GitOps merge request source_branch must differ from target_branch.",
            code="gitops_branch_conflict",
            payload={"target": target},
        )

    normalized = {
        "repository": repository,
        "repository_host": repository_ref["host"],
        "repository_path": repository_ref["path"],
        "git_provider": repository_ref["provider"],
        "source_branch": source_branch,
        "target_branch": target_branch,
        "path": path,
        "title": title,
        "changes": changes,
    }
    if cluster is not None:
        normalized.update(
            {
                "cluster_id": f"cluster_{cluster.id}",
                "cluster_name": cluster.name,
                "environment": cluster.environment,
            }
        )

    return (
        cluster,
        normalized,
        {
            "summary": summary,
            "blast_radius": "gitops_merge_request",
            "inventory_match": cluster is not None,
            "affected": [
                {
                    "repository": repository,
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "path": path,
                }
            ],
            "change_count": len(changes),
            "changes": changes,
            "git_provider": repository_ref["provider"],
            "gitops_write_performed": False,
            "cluster_mutation_performed": False,
            "merge_request_template": {
                "provider": repository_ref["provider"],
                "project_path": repository_ref["path"],
                "title": title,
                "description": _gitops_merge_request_description(normalized),
                "labels": ["webterm", "kubernetes-ops", "gitops"],
                "source_branch": source_branch,
                "target_branch": target_branch,
                "draft": True,
                "remove_source_branch": True,
                "squash": False,
                "commit_message": _gitops_commit_message(title),
                "file_changes": changes,
                "api_payload": {
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "title": f"Draft: {title}" if not title.lower().startswith("draft") else title,
                    "description": _gitops_merge_request_description(normalized),
                    "labels": ["webterm", "kubernetes-ops", "gitops"],
                    "remove_source_branch": True,
                    "squash": False,
                },
                "checklist": [
                    "CI pipeline passed",
                    "GitOps controller reconciled the target environment",
                    "Rancher/Fleet/Devtron inventory is healthy after sync",
                    "Rollback path is documented in the action report",
                ],
                "verification_plan": [
                    "merge_request_reviewed",
                    "ci_pipeline_passed",
                    "fleet_bundle_reconciled",
                    "webterm_inventory_healthy",
                ],
                "rollback_hint": "Revert or supersede this merge request through GitOps; do not patch the live cluster directly.",
            },
            "expected_verification": [
                "merge request review",
                "CI status",
                "GitOps reconciliation status",
                "post-sync WebTerm inventory health",
            ],
        },
    )


def _safe_repository_url(value: Any) -> str:
    repository = _bounded_text(value, limit=240)
    if not repository:
        raise ActionRequestValidationError(
            "GitOps merge request requires repository.",
            code="gitops_repository_required",
            payload={},
        )
    if "://" in repository:
        parsed = urlsplit(repository)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ActionRequestValidationError(
                "GitOps repository must be an http(s) URL or git SSH URL.",
                code="gitops_repository_invalid",
                payload={"repository": repository},
            )
        if parsed.username or parsed.password:
            raise ActionRequestValidationError(
                "GitOps repository URL must not contain credentials.",
                code="gitops_repository_credentials",
                payload={"repository": "[redacted]"},
            )
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    if re.match(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+(?:\.git)?$", repository):
        return repository
    raise ActionRequestValidationError(
        "GitOps repository must be an http(s) URL or git SSH URL.",
        code="gitops_repository_invalid",
        payload={"repository": repository},
    )


def _repository_ref(repository: str) -> dict[str, str]:
    parsed = urlsplit(repository)
    if parsed.scheme in {"https", "http"} and parsed.netloc:
        path = parsed.path.strip("/").removesuffix(".git")
        return {"provider": _provider_from_host(parsed.hostname or ""), "host": parsed.hostname or "", "path": path}
    match = re.match(
        r"^(?P<user>[A-Za-z0-9._-]+)@(?P<host>[A-Za-z0-9._-]+):(?P<path>[A-Za-z0-9._/-]+?)(?:\.git)?$", repository
    )
    if match:
        host = match.group("host")
        return {"provider": _provider_from_host(host), "host": host, "path": match.group("path").strip("/")}
    return {"provider": "git", "host": "", "path": ""}


def _provider_from_host(host: str) -> str:
    return "gitlab" if "gitlab" in host.lower() else "git"


def _safe_branch_name(value: Any) -> str:
    branch = _bounded_text(value, limit=120)
    if not branch:
        return ""
    if branch.startswith("/") or branch.endswith("/") or ".." in branch or re.search(r"\s|[~^:?*\\[]", branch):
        raise ActionRequestValidationError(
            "GitOps branch name is invalid.",
            code="gitops_branch_invalid",
            payload={"branch": branch},
        )
    return branch


def _gitops_changes(target: dict[str, Any], *, default_path: str) -> list[dict[str, str]]:
    raw_changes = target.get("changes")
    changes: list[dict[str, str]] = []
    if isinstance(raw_changes, list):
        for item in raw_changes[:10]:
            if isinstance(item, dict):
                item_path = _safe_repo_path(item.get("path") or item.get("file") or default_path)
                summary = _bounded_text(
                    item.get("summary") or item.get("description") or item.get("value") or "", limit=240
                )
                operation = _bounded_text(item.get("operation") or "update", limit=40).lower() or "update"
            else:
                item_path = default_path
                summary = _bounded_text(item, limit=240)
                operation = "update"
            if summary:
                changes.append({"path": item_path, "operation": operation, "summary": summary})
    if not changes:
        diff_summary = _bounded_text(target.get("diff_summary") or "", limit=240)
        if diff_summary:
            changes.append({"path": default_path, "operation": "update", "summary": diff_summary})
    if not changes:
        raise ActionRequestValidationError(
            "GitOps merge request requires changes or diff_summary.",
            code="gitops_changes_required",
            payload={"target": target},
        )
    return changes


def _safe_repo_path(value: Any) -> str:
    path = _bounded_text(value, limit=240)
    if not path:
        return ""
    if path.startswith("/") or "\\" in path or "\x00" in path:
        raise ActionRequestValidationError(
            "GitOps repository path is invalid.", code="gitops_path_invalid", payload={"path": path}
        )
    parts = [part for part in path.split("/") if part]
    if any(part in {".", ".."} for part in parts) or ".." in path:
        raise ActionRequestValidationError(
            "GitOps repository path is invalid.", code="gitops_path_invalid", payload={"path": "[redacted]"}
        )
    if not GITOPS_ALLOWED_PATH_RE.match(path):
        raise ActionRequestValidationError(
            "GitOps repository path is invalid.", code="gitops_path_invalid", payload={"path": path}
        )
    return path


def _gitops_commit_message(title: str) -> str:
    return f"chore(kubernetes): {title}"[:120]


def _gitops_merge_request_description(normalized: dict[str, Any]) -> str:
    change_lines = "\n".join(
        f"- {item['operation']} `{item['path']}`: {item['summary']}" for item in normalized["changes"]
    )
    return (
        "Requested by WebTerm Kubernetes Ops.\n\n"
        f"Repository: {normalized['repository']}\n"
        f"Source branch: {normalized['source_branch']}\n"
        f"Target branch: {normalized['target_branch']}\n"
        f"Path: {normalized['path']}\n\n"
        "Planned changes:\n"
        f"{change_lines}\n\n"
        "Execution policy: external GitOps merge request only; WebTerm does not mutate the cluster."
    )


def _bounded_text(value: Any, *, limit: int = MAX_TEXT) -> str:
    return bounded_action_text(value, limit=limit)
