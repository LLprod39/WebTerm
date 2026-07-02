from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminRecording, K8sAdminRecordingEvent, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_node_debug import complete_node_debug_stream, prepare_node_debug_stream_context
from kubernetes_ops.services.admin_recording import append_interactive_recording_event
from kubernetes_ops.services.admin_terminal import complete_cluster_terminal_stream, prepare_cluster_terminal_stream_context
from kubernetes_ops.services.provider_interactive_shell_streams import open_provider_interactive_shell_stream


def build_kubernetes_release_interactive_shell_stream_evidence(user, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "interactive shell stream proof skipped"}
    if not user or not getattr(user, "is_staff", False):
        return {"success": False, "status": "missing", "reason": "staff user is required for interactive shell stream proof"}
    try:
        with transaction.atomic():
            _grant_break_glass_features(user)
            provider = K8sProvider.objects.create(
                name="release-interactive-shell-rancher",
                kind=K8sProvider.KIND_RANCHER,
                base_url="https://rancher.release-shell.example.test",
                auth_mode=K8sProvider.AUTH_NONE,
                labels={
                    "cluster_terminal_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/webterm-terminal/exec",
                    "node_debug_path_template": "/k8s/clusters/{cluster_id}/api/v1/nodes/{node_name}/proxy/debug",
                },
            )
            cluster = K8sCluster.objects.create(
                name="release-interactive-shell",
                environment="test",
                rancher_provider=provider,
                rancher_cluster_id="c-release-interactive-shell",
            )
            K8sProvider.objects.exclude(pk=provider.pk).update(enabled=False)
            proof = _run_interactive_shell_checks(user=user, provider=provider, cluster=cluster)
            transaction.set_rollback(True)
            return proof
    except Exception as exc:
        return {"success": False, "status": "error", "error": str(exc)}


def _run_interactive_shell_checks(*, user, provider: K8sProvider, cluster: K8sCluster) -> dict[str, Any]:
    initial_action_count = K8sAdminAction.objects.count()
    initial_recording_count = K8sAdminRecording.objects.count()
    initial_event_count = K8sAdminRecordingEvent.objects.count()
    requests: list[dict[str, Any]] = []

    terminal_session = _terminal_session(user=user, cluster=cluster)
    node_session = _node_session(user=user, cluster=cluster)
    with _temporary_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="local",
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True,
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=True,
    ):
        terminal = _terminal_stream_proof(user=user, session=terminal_session, requests=requests)
        node_debug = _node_debug_stream_proof(user=user, session=node_session, requests=requests)
        provider_stream = _provider_stream_open_proof(provider=provider, requests=requests)

    created_action_count = K8sAdminAction.objects.count() - initial_action_count
    created_recording_count = K8sAdminRecording.objects.count() - initial_recording_count
    created_event_count = K8sAdminRecordingEvent.objects.count() - initial_event_count
    checks = [terminal, node_debug, provider_stream]
    success = (
        all(item["success"] for item in checks)
        and created_action_count == 2
        and created_recording_count == 2
        and created_event_count >= 4
        and all(_request_body_safe(item) for item in requests)
    )
    return {
        "success": success,
        "status": "ready" if success else "failed",
        "mode": "transaction_rollback",
        "checks": checks,
        "checked_count": len(checks),
        "actions_created": created_action_count,
        "recordings_created": created_recording_count,
        "recording_events_created": created_event_count,
        "provider_requests": _request_summaries(requests),
        "provider_requests_safe": all(_request_body_safe(item) for item in requests),
        "persistent_rows": False,
        "production_live_provider_evidence": False,
    }


def _terminal_stream_proof(*, user, session: K8sAdminSession, requests: list[dict[str, Any]]) -> dict[str, Any]:
    context = prepare_cluster_terminal_stream_context(
        user=user,
        session=session,
        reason="release interactive shell terminal smoke",
        stream_id="release-terminal-smoke",
        timeout_seconds=2,
    )
    append_interactive_recording_event(recording_pk=context["_recording_pk"], stream="stdin", data="PASSWORD=release-terminal-secret", sequence=1)
    append_interactive_recording_event(recording_pk=context["_recording_pk"], stream="stdout", data="TOKEN=release-terminal-token", sequence=2)
    summary = complete_cluster_terminal_stream(
        user=user,
        action_id=context["action"]["id"],
        session_pk=context["_session_pk"],
        stream_id=context["stream_id"],
        stdout_count=1,
        stderr_count=0,
        exit_code=0,
        close_reason="provider_eof",
    )
    recording = K8sAdminRecording.objects.get(pk=context["_recording_pk"])
    events = list(recording.events.order_by("sequence"))
    request = _open_provider_stream(
        provider=context["_provider"],
        path=context["_terminal_path"],
        operation="cluster_terminal",
        target={"namespace": context["namespace"]},
        requests=requests,
    )
    return {
        "id": "cluster_terminal_stream",
        "success": (
            context["policy"]["provider_transport_enabled"] is True
            and summary["status"] == K8sAdminAction.STATUS_COMPLETED
            and recording.status == K8sAdminRecording.STATUS_COMPLETED
            and recording.transcript_stored is True
            and _events_are_redacted(events)
            and request["operation"] == "cluster_terminal"
        ),
        "status": summary["status"],
        "recording_status": recording.status,
        "event_count": len(events),
        "transcript_stored": recording.transcript_stored,
        "redaction_ok": _events_are_redacted(events),
        "provider_operation": request["operation"],
        "provider_target_keys": sorted(request["target_keys"]),
    }


def _node_debug_stream_proof(*, user, session: K8sAdminSession, requests: list[dict[str, Any]]) -> dict[str, Any]:
    context = prepare_node_debug_stream_context(
        user=user,
        session=session,
        node_name="release-worker-1",
        reason="release interactive shell node debug smoke",
        stream_id="release-node-debug-smoke",
        timeout_seconds=2,
    )
    append_interactive_recording_event(recording_pk=context["_recording_pk"], stream="stdout", data="TOKEN=release-node-token", sequence=1)
    append_interactive_recording_event(recording_pk=context["_recording_pk"], stream="stderr", data="PASSWORD=release-node-secret", sequence=2)
    summary = complete_node_debug_stream(
        user=user,
        action_id=context["action"]["id"],
        session_pk=context["_session_pk"],
        stream_id=context["stream_id"],
        stdout_count=1,
        stderr_count=1,
        exit_code=0,
        close_reason="provider_eof",
    )
    recording = K8sAdminRecording.objects.get(pk=context["_recording_pk"])
    events = list(recording.events.order_by("sequence"))
    request = _open_provider_stream(
        provider=context["_provider"],
        path=context["_node_debug_path"],
        operation="node_debug",
        target={"kind": "Node", "name": context["target"]["name"]},
        requests=requests,
    )
    return {
        "id": "node_debug_stream",
        "success": (
            context["policy"]["provider_transport_enabled"] is True
            and summary["status"] == K8sAdminAction.STATUS_COMPLETED
            and recording.status == K8sAdminRecording.STATUS_COMPLETED
            and recording.transcript_stored is True
            and _events_are_redacted(events)
            and request["operation"] == "node_debug"
        ),
        "status": summary["status"],
        "recording_status": recording.status,
        "event_count": len(events),
        "transcript_stored": recording.transcript_stored,
        "redaction_ok": _events_are_redacted(events),
        "provider_operation": request["operation"],
        "provider_target_keys": sorted(request["target_keys"]),
    }


def _provider_stream_open_proof(*, provider: K8sProvider, requests: list[dict[str, Any]]) -> dict[str, Any]:
    request = _open_provider_stream(
        provider=provider,
        path="/k8s/clusters/c-release-interactive-shell/api/v1/namespaces/release-shell/pods/webterm-terminal/exec",
        operation="cluster_terminal",
        target={"namespace": "release-shell"},
        requests=requests,
    )
    return {
        "id": "provider_interactive_shell_stream_opener",
        "success": request["method"] == "POST" and request["stdin"] is True and request["tty"] is True and request["event_stream_ok"] is True,
        "method": request["method"],
        "stdin": request["stdin"],
        "tty": request["tty"],
        "event_stream_ok": request["event_stream_ok"],
    }


def _open_provider_stream(*, provider: K8sProvider, path: str, operation: str, target: dict[str, Any], requests: list[dict[str, Any]]) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def transport(url, _headers, _timeout, *, method="GET", body=None):
        captured.update({"url": str(url), "method": str(method).upper(), "body": dict(body or {})})
        return {"events": [{"stream": "stdout", "data": "TOKEN=provider-secret"}, {"stream": "status", "exit_code": 0}]}

    stream = open_provider_interactive_shell_stream(
        provider,
        path,
        timeout=2,
        operation=operation,
        target=target,
        stdin=True,
        tty=True,
        transport=transport,
    )
    stream.write_stdin("PASSWORD=provider-stdin-secret")
    first_event = stream.read_event(max_bytes=4096)
    stream.close()
    body = captured.get("body") if isinstance(captured.get("body"), dict) else {}
    request = {
        "operation": str(body.get("operation") or ""),
        "target_keys": sorted((body.get("target") or {}).keys()) if isinstance(body.get("target"), dict) else [],
        "stdin": bool(body.get("stdin")),
        "tty": bool(body.get("tty")),
        "method": captured.get("method", ""),
        "path": _public_path(captured.get("url", "")),
        "event_stream_ok": first_event.stream == "stdout",
    }
    requests.append(request)
    return request


def _grant_break_glass_features(user) -> None:
    for feature in ("kubernetes", "kubernetes_break_glass"):
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


def _terminal_session(*, user, cluster: K8sCluster) -> K8sAdminSession:
    return K8sAdminSession.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace="release-shell",
        mode=K8sAdminSession.MODE_BREAK_GLASS,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_CRITICAL,
        reason="release interactive shell terminal session",
        approval_ref="REL-INTERACTIVE-SHELL",
        approved_by=user,
        approved_at=timezone.now(),
        allowed_verbs=["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
        allowed_kinds=["pod"],
        allowed_namespaces=["release-shell"],
        expires_at=timezone.now() + timedelta(minutes=15),
    )


def _node_session(*, user, cluster: K8sCluster) -> K8sAdminSession:
    return K8sAdminSession.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace="",
        mode=K8sAdminSession.MODE_BREAK_GLASS,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_CRITICAL,
        reason="release interactive shell node debug session",
        approval_ref="REL-INTERACTIVE-SHELL-NODE",
        approved_by=user,
        approved_at=timezone.now(),
        allowed_verbs=["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
        allowed_kinds=["node"],
        allowed_namespaces=["*"],
        expires_at=timezone.now() + timedelta(minutes=15),
    )


def _events_are_redacted(events: list[K8sAdminRecordingEvent]) -> bool:
    serialized = " ".join(event.data for event in events)
    return bool(events) and "release-terminal-secret" not in serialized and "release-node-secret" not in serialized and "provider-secret" not in serialized


def _request_body_safe(request: dict[str, Any]) -> bool:
    serialized = str(request)
    return "provider-secret" not in serialized and "provider-stdin-secret" not in serialized


def _request_summaries(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in item.items() if key != "path"} for item in requests]


def _public_path(value: object) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    return raw.split("?", 1)[0].split("#", 1)[0][:300]


@contextmanager
def _temporary_settings(**overrides):
    previous = {key: getattr(settings, key, None) for key in overrides}
    missing = {key for key in overrides if not hasattr(settings, key)}
    try:
        for key, value in overrides.items():
            setattr(settings, key, value)
        yield
    finally:
        for key, value in previous.items():
            if key in missing:
                try:
                    delattr(settings, key)
                except AttributeError:
                    pass
            else:
                setattr(settings, key, value)
