"""Device-code authentication and verification for isolated CLI connections."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from datetime import timedelta
from urllib.parse import urlparse

from asgiref.sync import async_to_sync, sync_to_async
from django.apps import apps
from django.db import close_old_connections, transaction
from django.db.models import F, Q
from django.utils import timezone

from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1
from app.ai_runtime import ProviderEventType, ProviderRuntimeError
from app.core.ai_cli_runner_client import AiCliRunnerClient
from core_ui.models.ai_providers import (
    AIConnectionAuthFlow,
    AIProviderConnection,
    AIProviderInvocation,
    AIProviderLease,
)

AUTH_FLOW_LEASE_SECONDS = 90
AUTH_FLOW_HEARTBEAT_SECONDS = 30


def start_connection_auth(connection: AIProviderConnection) -> AIConnectionAuthFlow:
    with transaction.atomic():
        locked = AIProviderConnection.objects.select_for_update().get(pk=connection.pk)
        now = timezone.now()
        locked.auth_flows.filter(
            status=AIConnectionAuthFlow.STATUS_PENDING,
            expires_at__lte=now,
        ).update(
            status=AIConnectionAuthFlow.STATUS_EXPIRED,
            completed_at=now,
            verification_uri="",
            user_code="",
        )
        pending = locked.auth_flows.filter(status=AIConnectionAuthFlow.STATUS_PENDING).first()
        if pending is not None:
            return pending
        if not locked.credential_ref:
            locked.credential_ref = f"connection_{locked.public_id.hex}"
        locked.status = AIProviderConnection.STATUS_PENDING_AUTH
        locked.last_error_code = ""
        locked.save(update_fields=["credential_ref", "status", "last_error_code", "updated_at"])
        flow = AIConnectionAuthFlow.objects.create(
            connection=locked,
            expires_at=timezone.now() + timedelta(minutes=20),
        )
        if os.getenv("AI_CLI_AUTH_IN_PROCESS", "true").strip().lower() in {"1", "true", "yes"}:
            transaction.on_commit(lambda: _spawn_auth_worker(flow.pk))
        return flow


def queue_connection_verification(connection: AIProviderConnection) -> AIConnectionAuthFlow:
    """Queue a bounded verification flow without blocking an HTTP request."""
    with transaction.atomic():
        locked = AIProviderConnection.objects.select_for_update().get(pk=connection.pk)
        pending = locked.auth_flows.filter(status=AIConnectionAuthFlow.STATUS_PENDING).first()
        if pending is not None:
            return pending
        flow = AIConnectionAuthFlow.objects.create(
            connection=locked,
            flow_kind="verification",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        if os.getenv("AI_CLI_AUTH_IN_PROCESS", "true").strip().lower() in {"1", "true", "yes"}:
            transaction.on_commit(lambda: _spawn_auth_worker(flow.pk))
        return flow


def _spawn_auth_worker(flow_id: int) -> None:
    thread = threading.Thread(
        target=_auth_worker_entrypoint,
        args=(flow_id,),
        name=f"ai-provider-auth-{flow_id}",
        daemon=True,
    )
    thread.start()


def _auth_worker_entrypoint(flow_id: int) -> None:
    close_old_connections()
    try:
        worker_name = f"inproc:{socket.gethostname()}:{threading.get_ident()}"[:120]
        fencing_token = claim_auth_flow(flow_id, worker_name=worker_name)
        if fencing_token is not None:
            asyncio.run(
                _run_auth_flow(
                    flow_id,
                    worker_name=worker_name,
                    fencing_token=fencing_token,
                )
            )
    finally:
        close_old_connections()


@transaction.atomic
def claim_auth_flow(flow_id: int, *, worker_name: str) -> int | None:
    now = timezone.now()
    flow = (
        AIConnectionAuthFlow.objects.select_for_update()
        .filter(pk=flow_id, status=AIConnectionAuthFlow.STATUS_PENDING)
        .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
        .first()
    )
    if flow is None or (flow.expires_at and flow.expires_at <= now):
        return None
    flow.claimed_at = now
    flow.claimed_by = str(worker_name or "auth-worker")[:120]
    flow.fencing_token += 1
    flow.lease_expires_at = min(
        flow.expires_at or now + timedelta(seconds=AUTH_FLOW_LEASE_SECONDS),
        now + timedelta(seconds=AUTH_FLOW_LEASE_SECONDS),
    )
    flow.save(update_fields=["claimed_at", "claimed_by", "lease_expires_at", "fencing_token"])
    return flow.fencing_token


@transaction.atomic
def claim_next_auth_flow(*, worker_name: str) -> tuple[int, int] | None:
    now = timezone.now()
    AIConnectionAuthFlow.objects.select_for_update(skip_locked=True).filter(
        status=AIConnectionAuthFlow.STATUS_PENDING,
        expires_at__lte=now,
    ).update(
        status=AIConnectionAuthFlow.STATUS_EXPIRED,
        completed_at=now,
        verification_uri="",
        user_code="",
    )
    flow = (
        AIConnectionAuthFlow.objects.select_for_update(skip_locked=True)
        .filter(status=AIConnectionAuthFlow.STATUS_PENDING, expires_at__gt=now)
        .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
        .order_by("created_at", "id")
        .first()
    )
    if flow is None:
        return None
    flow.claimed_at = now
    flow.claimed_by = str(worker_name or "auth-worker")[:120]
    flow.fencing_token += 1
    flow.lease_expires_at = min(
        flow.expires_at,
        now + timedelta(seconds=AUTH_FLOW_LEASE_SECONDS),
    )
    flow.save(update_fields=["claimed_at", "claimed_by", "lease_expires_at", "fencing_token"])
    return flow.pk, flow.fencing_token


@transaction.atomic
def heartbeat_auth_flow(
    flow_id: int,
    *,
    worker_name: str,
    fencing_token: int,
    lease_seconds: int = AUTH_FLOW_LEASE_SECONDS,
) -> bool:
    now = timezone.now()
    flow = (
        AIConnectionAuthFlow.objects.select_for_update()
        .filter(
            pk=flow_id,
            status=AIConnectionAuthFlow.STATUS_PENDING,
            claimed_by=worker_name,
            fencing_token=fencing_token,
            lease_expires_at__gt=now,
        )
        .first()
    )
    if flow is None or (flow.expires_at and flow.expires_at <= now):
        return False
    flow.lease_expires_at = min(
        flow.expires_at or now + timedelta(seconds=lease_seconds),
        now + timedelta(seconds=max(30, lease_seconds)),
    )
    flow.save(update_fields=["lease_expires_at"])
    return True


async def run_claimed_auth_flow(flow_id: int, *, worker_name: str, fencing_token: int) -> None:
    await _run_auth_flow(flow_id, worker_name=worker_name, fencing_token=fencing_token)


async def _run_auth_flow(flow_id: int, *, worker_name: str, fencing_token: int) -> None:
    flow = await _load_flow(flow_id)
    if flow is None or flow.status != AIConnectionAuthFlow.STATUS_PENDING:
        return
    connection = flow.connection
    request = RunnerRequestV1(
        action=(RunnerAction.VERIFY if flow.flow_kind == "verification" else RunnerAction.AUTH_START),
        connection_ref=connection.credential_ref,
        target_id=connection.target_id,
        invocation_id=f"auth_{flow.public_id.hex}",
    )
    terminal_type: ProviderEventType | None = None
    error_code = ""
    client = AiCliRunnerClient()
    lease_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _auth_flow_heartbeat_loop(
            flow_id,
            worker_name=worker_name,
            fencing_token=fencing_token,
            lease_lost=lease_lost,
            client=client,
            invocation_ref=request.invocation_id,
        )
    )
    try:
        async for event in client.stream(request):
            if lease_lost.is_set():
                return
            if event.type is ProviderEventType.AUTH_REQUIRED:
                if flow.flow_kind == "verification":
                    terminal_type = event.type
                    error_code = str(event.payload.get("code") or "provider_auth_required")
                else:
                    await _record_device_code(
                        flow_id,
                        event.payload,
                        worker_name=worker_name,
                        fencing_token=fencing_token,
                    )
            if event.type in {
                ProviderEventType.COMPLETED,
                ProviderEventType.ERROR,
                ProviderEventType.CANCELLED,
                ProviderEventType.LIMIT,
            }:
                terminal_type = event.type
                error_code = str(event.payload.get("code") or "")
    except ProviderRuntimeError as exc:
        terminal_type = ProviderEventType.ERROR
        error_code = exc.code
    except Exception:  # noqa: BLE001 - provider/runtime details must not reach the auth record
        terminal_type = ProviderEventType.ERROR
        error_code = "provider_auth_runtime_failed"
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
    if not lease_lost.is_set():
        await _complete_auth_flow(
            flow_id,
            terminal_type,
            error_code,
            worker_name=worker_name,
            fencing_token=fencing_token,
        )


async def _auth_flow_heartbeat_loop(
    flow_id: int,
    *,
    worker_name: str,
    fencing_token: int,
    lease_lost: asyncio.Event,
    client: AiCliRunnerClient,
    invocation_ref: str,
) -> None:
    try:
        while True:
            await asyncio.sleep(AUTH_FLOW_HEARTBEAT_SECONDS)
            owned = await sync_to_async(heartbeat_auth_flow, thread_sensitive=True)(
                flow_id,
                worker_name=worker_name,
                fencing_token=fencing_token,
            )
            if not owned:
                raise ProviderRuntimeError("provider_auth_lease_lost", "Provider auth flow ownership was lost")
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - any heartbeat failure invalidates ownership
        lease_lost.set()
        try:
            await client.cancel(invocation_ref)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - ownership stays lost if manager is unavailable
            return


def verify_connection(connection: AIProviderConnection) -> dict[str, object]:
    return async_to_sync(_verify_connection_async)(connection.pk)


def revoke_connection_credentials(connection: AIProviderConnection) -> bool:
    if not connection.credential_ref:
        return True
    return async_to_sync(AiCliRunnerClient().revoke_connection)(connection.credential_ref)


@transaction.atomic
def fence_connection_invocations(connection: AIProviderConnection) -> int:
    """Fence active work before credential cleanup so stale workers cannot persist."""
    now = timezone.now()
    leases = AIProviderLease.objects.select_for_update().filter(
        connection=connection,
        status=AIProviderLease.STATUS_ACTIVE,
    )
    invocation_ids = list(leases.values_list("invocation_id", flat=True))
    leases.update(status=AIProviderLease.STATUS_RELEASED, released_at=now)
    terminal = {
        "version": 1,
        "type": ProviderEventType.CANCELLED.value,
        "payload": {"code": "provider_connection_revoked"},
    }
    invocations = list(
        AIProviderInvocation.objects.select_for_update().filter(
            pk__in=invocation_ids,
            status__in=[
                AIProviderInvocation.STATUS_QUEUED,
                AIProviderInvocation.STATUS_LEASED,
                AIProviderInvocation.STATUS_RUNNING,
            ],
        )
    )
    for invocation in invocations:
        invocation.status = AIProviderInvocation.STATUS_CANCELLED
        invocation.error_code = "provider_connection_revoked"
        invocation.completed_at = now
        invocation.terminal_event = terminal
        invocation.event_log = [*(invocation.event_log or []), terminal][-512:]
        invocation.event_cursor = F("event_cursor") + 1
        invocation.save(
            update_fields=[
                "status",
                "error_code",
                "completed_at",
                "terminal_event",
                "event_log",
                "event_cursor",
            ]
        )
    return len(invocations)


def _clear_connection_binding_refs(value: object, connection_id: int) -> bool:
    """Clear matching provider_binding objects inside mutable JSON documents."""

    changed = False
    if isinstance(value, list):
        for item in value:
            changed = _clear_connection_binding_refs(item, connection_id) or changed
        return changed
    if not isinstance(value, dict):
        return False
    for key, item in list(value.items()):
        if key == "provider_binding" and isinstance(item, dict):
            pinned_id = item.get("connection_id") or item.get("selected_connection_id")
            if str(pinned_id or "") == str(connection_id):
                value[key] = {}
                changed = True
                continue
        changed = _clear_connection_binding_refs(item, connection_id) or changed
    return changed


@transaction.atomic
def clear_connection_provider_pins(connection: AIProviderConnection) -> int:
    """Remove mutable pins while preserving completed-run provider provenance."""

    pin_fields = (
        ("core_ui", "ChatSession", "provider_binding", None),
        (
            "core_ui",
            "ChatTurnState",
            "provider_binding_snapshot",
            {"status__in": ["running", "awaiting_confirm", "awaiting_async", "resuming"]},
        ),
        ("servers", "TerminalAiProviderState", "provider_binding", None),
        ("servers", "ServerAgent", "provider_binding", None),
        (
            "servers",
            "AgentRun",
            "provider_binding_snapshot",
            {"status__in": ["pending", "running", "paused", "waiting", "plan_review"]},
        ),
        ("studio", "AgentConfig", "provider_binding", None),
        ("studio", "Pipeline", "provider_binding", None),
        (
            "studio",
            "PipelineRun",
            "provider_binding_snapshot",
            {"status__in": ["pending", "running", "hibernating"]},
        ),
    )
    cleared = 0
    for app_label, model_name, field_name, extra_filters in pin_fields:
        model = apps.get_model(app_label, model_name)
        queryset = model.objects.filter(
            Q(**{f"{field_name}__connection_id": connection.pk})
            | Q(**{f"{field_name}__selected_connection_id": connection.pk})
        )
        if extra_filters:
            queryset = queryset.filter(**extra_filters)
        updates = {field_name: {}}
        if any(field.name == "provider_session_id" for field in model._meta.fields):
            updates["provider_session_id"] = ""
        cleared += queryset.update(**updates)

    pipeline_model = apps.get_model("studio", "Pipeline")
    for pipeline in pipeline_model.objects.only("pk", "nodes").iterator():
        nodes = pipeline.nodes if isinstance(pipeline.nodes, list) else []
        if _clear_connection_binding_refs(nodes, connection.pk):
            pipeline_model.objects.filter(pk=pipeline.pk).update(nodes=nodes)
            cleared += 1

    template_model = apps.get_model("studio", "PipelineTemplate")
    for template in template_model.objects.only("pk", "nodes").iterator():
        nodes = template.nodes if isinstance(template.nodes, list) else []
        if _clear_connection_binding_refs(nodes, connection.pk):
            template_model.objects.filter(pk=template.pk).update(nodes=nodes)
            cleared += 1

    active_draft_statuses = ["drafting", "needs_input", "ready", "invalid", "blocked"]
    draft_model = apps.get_model("studio", "PipelineDraftSession")
    for draft in draft_model.objects.filter(status__in=active_draft_statuses).only("pk", "current_graph_snapshot"):
        snapshot = draft.current_graph_snapshot if isinstance(draft.current_graph_snapshot, dict) else {}
        if _clear_connection_binding_refs(snapshot, connection.pk):
            draft_model.objects.filter(pk=draft.pk).update(current_graph_snapshot=snapshot)
            cleared += 1

    revision_model = apps.get_model("studio", "PipelineDraftRevision")
    draft_json_fields = ("node_patch", "graph_patch", "preview_nodes", "response_payload")
    revisions = revision_model.objects.filter(session__status__in=active_draft_statuses).only("pk", *draft_json_fields)
    for revision in revisions:
        updates = {}
        for field_name in draft_json_fields:
            value = getattr(revision, field_name)
            if _clear_connection_binding_refs(value, connection.pk):
                updates[field_name] = value
        if updates:
            revision_model.objects.filter(pk=revision.pk).update(**updates)
            cleared += 1

    preference_model = apps.get_model("core_ui", "AIProviderPreference")
    deleted, _ = preference_model.objects.filter(connection=connection, user__isnull=False).delete()
    cleared += deleted
    for membership in connection.pool_memberships.select_related("pool"):
        viable_member_exists = membership.pool.members.filter(
            enabled=True,
            connection__enabled=True,
            connection__status=AIProviderConnection.STATUS_CONNECTED,
        ).exists()
        if not viable_member_exists:
            deleted, _ = membership.pool.preferences.filter(user__isnull=False).delete()
            cleared += deleted
    return cleared


def retry_pending_credential_cleanup(*, limit: int = 10) -> int:
    """Retry fail-closed credential cleanup after the manager becomes available."""
    ids = list(
        AIProviderConnection.objects.filter(
            enabled=False,
            status=AIProviderConnection.STATUS_DISABLED,
            credential_ref__gt="",
            health__cleanup_pending=True,
        )
        .order_by("updated_at", "pk")
        .values_list("pk", flat=True)[: max(1, min(int(limit), 50))]
    )
    cleaned = 0
    for connection_id in ids:
        connection = AIProviderConnection.objects.filter(pk=connection_id).first()
        if connection is None:
            continue
        try:
            removed = revoke_connection_credentials(connection)
        except Exception:  # noqa: BLE001 - leave the durable cleanup marker for the next cycle
            continue
        if not removed:
            continue
        with transaction.atomic():
            locked = AIProviderConnection.objects.select_for_update().get(pk=connection_id)
            if locked.enabled or locked.status != AIProviderConnection.STATUS_DISABLED:
                continue
            locked.status = AIProviderConnection.STATUS_REVOKED
            locked.credential_ref = ""
            locked.health = {key: value for key, value in (locked.health or {}).items() if key != "cleanup_pending"}
            locked.last_error_code = ""
            locked.save(
                update_fields=[
                    "status",
                    "credential_ref",
                    "health",
                    "last_error_code",
                    "updated_at",
                ]
            )
            cleaned += 1
    return cleaned


async def _verify_connection_async(connection_id: int) -> dict[str, object]:
    connection = await _load_connection(connection_id)
    request = RunnerRequestV1(
        action=RunnerAction.VERIFY,
        connection_ref=connection.credential_ref,
        target_id=connection.target_id,
        invocation_id=f"verify_{connection.public_id.hex}",
    )
    authenticated = False
    error_code = "provider_verification_incomplete"
    try:
        async for event in AiCliRunnerClient().stream(request):
            if event.type is ProviderEventType.COMPLETED:
                authenticated = bool(event.payload.get("authenticated", True))
                error_code = ""
            elif event.type is ProviderEventType.AUTH_REQUIRED:
                error_code = "provider_auth_required"
            elif event.type is ProviderEventType.ERROR:
                error_code = str(event.payload.get("code") or "provider_error")
    except ProviderRuntimeError as exc:
        error_code = exc.code
    await _record_verification(connection_id, authenticated, error_code)
    return {"authenticated": authenticated, "error_code": error_code}


@transaction.atomic
def cancel_pending_auth_flows(connection: AIProviderConnection) -> None:
    now = timezone.now()
    AIConnectionAuthFlow.objects.select_for_update().filter(
        connection=connection,
        status=AIConnectionAuthFlow.STATUS_PENDING,
    ).update(
        status=AIConnectionAuthFlow.STATUS_CANCELLED,
        completed_at=now,
        lease_expires_at=None,
        claimed_by="",
        verification_uri="",
        user_code="",
    )


@sync_to_async(thread_sensitive=True)
def _load_flow(flow_id: int):
    return AIConnectionAuthFlow.objects.select_related("connection").filter(pk=flow_id).first()


@sync_to_async(thread_sensitive=True)
def _load_connection(connection_id: int):
    return AIProviderConnection.objects.get(pk=connection_id)


@sync_to_async(thread_sensitive=True)
def _record_device_code(
    flow_id: int,
    payload: dict,
    *,
    worker_name: str,
    fencing_token: int,
) -> None:
    ownership_filter = {
        "pk": flow_id,
        "status": AIConnectionAuthFlow.STATUS_PENDING,
        "claimed_by": worker_name,
        "fencing_token": fencing_token,
        "lease_expires_at__gt": timezone.now(),
    }
    target_id = (
        AIConnectionAuthFlow.objects.filter(
            **ownership_filter,
        )
        .values_list("connection__target_id", flat=True)
        .first()
    )
    if target_id is None:
        return
    verification_uri = str(payload.get("verification_uri") or "")[:500]
    if not _allowed_verification_uri(target_id, verification_uri):
        raise ProviderRuntimeError(
            "provider_auth_uri_invalid",
            "Provider returned an untrusted device verification URL",
        )
    AIConnectionAuthFlow.objects.filter(
        pk=flow_id,
        status=AIConnectionAuthFlow.STATUS_PENDING,
        claimed_by=worker_name,
        fencing_token=fencing_token,
        lease_expires_at__gt=timezone.now(),
    ).update(
        verification_uri=verification_uri,
        user_code=str(payload.get("user_code") or "")[:64],
    )


def _allowed_verification_uri(target_id: str, value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    allowed_hosts = (
        {"auth.openai.com", "chatgpt.com", "openai.com"}
        if target_id == "codex_subscription"
        else {"accounts.x.ai", "x.ai", "grok.com"}
    )
    hostname = parsed.hostname.lower()
    return any(hostname == host or hostname.endswith(f".{host}") for host in allowed_hosts)


@sync_to_async(thread_sensitive=True)
def _complete_auth_flow(
    flow_id: int,
    terminal_type: ProviderEventType | None,
    error_code: str,
    *,
    worker_name: str,
    fencing_token: int,
) -> None:
    with transaction.atomic():
        flow = AIConnectionAuthFlow.objects.select_for_update().select_related("connection").get(pk=flow_id)
        if flow.status != AIConnectionAuthFlow.STATUS_PENDING:
            return
        if (
            flow.claimed_by != worker_name
            or flow.fencing_token != fencing_token
            or not flow.lease_expires_at
            or flow.lease_expires_at <= timezone.now()
        ):
            return
        now = timezone.now()
        connection = flow.connection
        if terminal_type is ProviderEventType.COMPLETED:
            flow.status = AIConnectionAuthFlow.STATUS_COMPLETED
            connection.status = AIProviderConnection.STATUS_CONNECTED
            connection.auth_revision += 1
            connection.last_error_code = ""
            connection.last_verified_at = now
        else:
            flow.status = (
                AIConnectionAuthFlow.STATUS_EXPIRED
                if flow.expires_at and flow.expires_at <= now
                else AIConnectionAuthFlow.STATUS_FAILED
            )
            flow.error_code = (error_code or "provider_auth_failed")[:80]
            connection.status = AIProviderConnection.STATUS_AUTH_REQUIRED
            connection.last_error_code = flow.error_code
        flow.completed_at = now
        flow.lease_expires_at = None
        flow.claimed_by = ""
        flow.verification_uri = ""
        flow.user_code = ""
        flow.save(
            update_fields=[
                "status",
                "error_code",
                "completed_at",
                "lease_expires_at",
                "claimed_by",
                "verification_uri",
                "user_code",
            ]
        )
        connection.save(update_fields=["status", "auth_revision", "last_error_code", "last_verified_at", "updated_at"])


@sync_to_async(thread_sensitive=True)
def _record_verification(connection_id: int, authenticated: bool, error_code: str) -> None:
    now = timezone.now()
    AIProviderConnection.objects.filter(pk=connection_id).update(
        status=(AIProviderConnection.STATUS_CONNECTED if authenticated else AIProviderConnection.STATUS_AUTH_REQUIRED),
        last_error_code=error_code[:80],
        last_verified_at=now,
        updated_at=now,
    )
