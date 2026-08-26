from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import OperationalError
from django.utils import timezone

from app.ai_runtime import ProviderEventType, ProviderEventV1
from core_ui.models.ai_providers import AIConnectionAuthFlow, AIProviderConnection
from core_ui.services import ai_provider_auth as provider_auth
from core_ui.services.ai_provider_auth import (
    _allowed_verification_uri,
    _complete_auth_flow,
    cancel_pending_auth_flows,
    claim_auth_flow,
    claim_next_auth_flow,
    heartbeat_auth_flow,
)
from servers.models import BackgroundWorkerState

pytestmark = pytest.mark.django_db(transaction=True)


def _flow(name: str = "Codex") -> AIConnectionAuthFlow:
    owner = User.objects.create_user(f"owner-{name.lower()}")
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=owner,
        name=name,
        status=AIProviderConnection.STATUS_PENDING_AUTH,
        credential_ref=f"connection_{name.lower()}_1234",
    )
    return AIConnectionAuthFlow.objects.create(
        connection=connection,
        expires_at=timezone.now() + timedelta(minutes=20),
    )


def test_auth_flow_claim_is_exclusive_until_lease_expires() -> None:
    flow = _flow()

    first_fence = claim_auth_flow(flow.pk, worker_name="worker-a")
    assert first_fence == 1
    assert claim_auth_flow(flow.pk, worker_name="worker-b") is None

    AIConnectionAuthFlow.objects.filter(pk=flow.pk).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    second_fence = claim_auth_flow(flow.pk, worker_name="worker-b")
    assert second_fence == 2
    flow.refresh_from_db()
    assert flow.claimed_by == "worker-b"
    assert heartbeat_auth_flow(flow.pk, worker_name="worker-a", fencing_token=first_fence) is False
    assert heartbeat_auth_flow(flow.pk, worker_name="worker-b", fencing_token=second_fence) is True
    flow.refresh_from_db()
    assert flow.lease_expires_at < flow.expires_at


def test_auth_worker_claims_oldest_pending_flow() -> None:
    first = _flow("First")
    second = _flow("Second")
    AIConnectionAuthFlow.objects.filter(pk=first.pk).update(
        created_at=timezone.now() - timedelta(minutes=1),
    )

    claim = claim_next_auth_flow(worker_name="worker-a")

    assert claim == (first.pk, 1)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.claimed_by == "worker-a"
    assert second.claimed_by == ""


def test_auth_worker_once_records_heartbeat_lifecycle() -> None:
    call_command("run_ai_provider_auth_worker", once=True, worker_key="pytest-auth-worker")

    state = BackgroundWorkerState.objects.get(
        worker_kind=BackgroundWorkerState.KIND_AI_PROVIDER_AUTH,
        worker_key="pytest-auth-worker",
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert state.heartbeat_at is not None
    assert state.last_started_at is not None
    assert state.last_stopped_at is not None


def test_default_auth_worker_identity_is_unique_per_process_instance(monkeypatch) -> None:
    monkeypatch.setattr(
        "core_ui.management.commands.run_ai_provider_auth_worker.socket.gethostname",
        lambda: "auth-host",
    )
    monkeypatch.setattr("core_ui.management.commands.run_ai_provider_auth_worker.os.getpid", lambda: 4321)

    class _Uuid:
        hex = "abcdef0123456789"

    monkeypatch.setattr(
        "core_ui.management.commands.run_ai_provider_auth_worker.uuid.uuid4",
        lambda: _Uuid(),
    )
    call_command("run_ai_provider_auth_worker", once=True)

    assert BackgroundWorkerState.objects.filter(worker_key="auth-host:4321:abcdef012345").exists()


def test_terminal_and_cancelled_auth_flows_clear_device_code_material() -> None:
    completed = _flow("Completed")
    fencing_token = claim_auth_flow(completed.pk, worker_name="worker-complete")
    assert fencing_token == 1
    AIConnectionAuthFlow.objects.filter(pk=completed.pk).update(
        verification_uri="https://auth.openai.com/device",
        user_code="SECRET-CODE",
    )
    async_to_sync(_complete_auth_flow)(
        completed.pk,
        ProviderEventType.COMPLETED,
        "",
        worker_name="worker-complete",
        fencing_token=fencing_token,
    )
    completed.refresh_from_db()
    assert completed.verification_uri == ""
    assert completed.user_code == ""

    cancelled = _flow("Cancelled")
    AIConnectionAuthFlow.objects.filter(pk=cancelled.pk).update(
        verification_uri="https://auth.openai.com/device",
        user_code="ANOTHER-CODE",
    )
    cancel_pending_auth_flows(cancelled.connection)
    cancelled.refresh_from_db()
    assert cancelled.status == AIConnectionAuthFlow.STATUS_CANCELLED
    assert cancelled.verification_uri == ""
    assert cancelled.user_code == ""


def test_device_code_update_cannot_repopulate_flow_cancelled_mid_write(monkeypatch) -> None:
    flow = _flow("DeviceCodeRace")
    fencing_token = claim_auth_flow(flow.pk, worker_name="device-code-worker")
    assert fencing_token == 1

    def cancel_before_conditional_update(_target_id: str, _verification_uri: str) -> bool:
        cancel_pending_auth_flows(flow.connection)
        return True

    monkeypatch.setattr(provider_auth, "_allowed_verification_uri", cancel_before_conditional_update)
    async_to_sync(provider_auth._record_device_code)(
        flow.pk,
        {
            "verification_uri": "https://auth.openai.com/device",
            "user_code": "MUST-NOT-RETURN",
        },
        worker_name="device-code-worker",
        fencing_token=fencing_token,
    )

    flow.refresh_from_db()
    assert flow.status == AIConnectionAuthFlow.STATUS_CANCELLED
    assert flow.verification_uri == ""
    assert flow.user_code == ""


def test_device_code_update_preserves_current_owned_flow() -> None:
    flow = _flow("DeviceCodeCurrent")
    fencing_token = claim_auth_flow(flow.pk, worker_name="device-code-current-worker")
    assert fencing_token == 1

    async_to_sync(provider_auth._record_device_code)(
        flow.pk,
        {
            "verification_uri": "https://auth.openai.com/device",
            "user_code": "CURRENT-CODE",
        },
        worker_name="device-code-current-worker",
        fencing_token=fencing_token,
    )

    flow.refresh_from_db()
    assert flow.status == AIConnectionAuthFlow.STATUS_PENDING
    assert flow.verification_uri == "https://auth.openai.com/device"
    assert flow.user_code == "CURRENT-CODE"


def test_verification_auth_required_is_not_treated_as_device_url(monkeypatch) -> None:
    flow = _flow("VerifyLoggedOut")
    flow.flow_kind = "verification"
    flow.save(update_fields=["flow_kind"])
    fencing_token = claim_auth_flow(flow.pk, worker_name="verify-worker")
    assert fencing_token == 1

    class _Client:
        async def stream(self, _request):
            yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})

        async def cancel(self, _invocation_ref: str) -> bool:
            return True

    monkeypatch.setattr(provider_auth, "AiCliRunnerClient", _Client)

    async_to_sync(provider_auth._run_auth_flow)(
        flow.pk,
        worker_name="verify-worker",
        fencing_token=fencing_token,
    )

    flow.refresh_from_db()
    flow.connection.refresh_from_db()
    assert flow.status == AIConnectionAuthFlow.STATUS_FAILED
    assert flow.error_code == "provider_auth_required"
    assert flow.connection.status == AIProviderConnection.STATUS_AUTH_REQUIRED
    assert flow.connection.last_error_code == "provider_auth_required"


@pytest.mark.asyncio
async def test_auth_heartbeat_database_failure_fences_and_attempts_cancel(monkeypatch) -> None:
    real_asyncio = asyncio

    async def no_wait(_seconds: int) -> None:
        return None

    def failed_heartbeat(*_args, **_kwargs):
        raise OperationalError("auth flow database unavailable")

    class _Client:
        def __init__(self) -> None:
            self.cancelled: list[str] = []

        async def cancel(self, invocation_ref: str) -> None:
            self.cancelled.append(invocation_ref)
            raise OSError("runner manager unavailable")

    monkeypatch.setattr(
        provider_auth,
        "asyncio",
        SimpleNamespace(sleep=no_wait, CancelledError=real_asyncio.CancelledError),
    )
    monkeypatch.setattr(provider_auth, "heartbeat_auth_flow", failed_heartbeat)
    lease_lost = real_asyncio.Event()
    client = _Client()

    await provider_auth._auth_flow_heartbeat_loop(
        123,
        worker_name="auth-heartbeat-worker",
        fencing_token=7,
        lease_lost=lease_lost,
        client=client,
        invocation_ref="auth-heartbeat-invocation",
    )

    assert lease_lost.is_set()
    assert client.cancelled == ["auth-heartbeat-invocation"]


@pytest.mark.asyncio
async def test_auth_heartbeat_propagates_task_cancellation(monkeypatch) -> None:
    real_asyncio = asyncio

    async def cancelled_wait(_seconds: int) -> None:
        raise real_asyncio.CancelledError

    class _Client:
        async def cancel(self, _invocation_ref: str) -> None:
            raise AssertionError("task cancellation must not be translated into lease loss")

    monkeypatch.setattr(
        provider_auth,
        "asyncio",
        SimpleNamespace(sleep=cancelled_wait, CancelledError=real_asyncio.CancelledError),
    )
    lease_lost = real_asyncio.Event()

    with pytest.raises(real_asyncio.CancelledError):
        await provider_auth._auth_flow_heartbeat_loop(
            123,
            worker_name="auth-heartbeat-worker",
            fencing_token=7,
            lease_lost=lease_lost,
            client=_Client(),
            invocation_ref="auth-heartbeat-cancelled-task",
        )

    assert not lease_lost.is_set()


def test_reclaimed_auth_flow_fences_same_named_stale_worker() -> None:
    flow = _flow("SameNameFence")
    stale_fence = claim_auth_flow(flow.pk, worker_name="worker-same-name")
    assert stale_fence == 1
    AIConnectionAuthFlow.objects.filter(pk=flow.pk).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    current_fence = claim_auth_flow(flow.pk, worker_name="worker-same-name")
    assert current_fence == 2

    assert (
        heartbeat_auth_flow(
            flow.pk,
            worker_name="worker-same-name",
            fencing_token=stale_fence,
        )
        is False
    )
    assert (
        heartbeat_auth_flow(
            flow.pk,
            worker_name="worker-same-name",
            fencing_token=current_fence,
        )
        is True
    )

    async_to_sync(_complete_auth_flow)(
        flow.pk,
        ProviderEventType.COMPLETED,
        "",
        worker_name="worker-same-name",
        fencing_token=stale_fence,
    )
    flow.refresh_from_db()
    assert flow.status == AIConnectionAuthFlow.STATUS_PENDING
    assert flow.fencing_token == current_fence


def test_device_verification_url_is_restricted_to_provider_hosts() -> None:
    assert _allowed_verification_uri("codex_subscription", "https://auth.openai.com/device")
    assert _allowed_verification_uri("grok_subscription", "https://accounts.x.ai/device")
    assert not _allowed_verification_uri("codex_subscription", "https://openai.com.evil.example/device")
    assert not _allowed_verification_uri("grok_subscription", "http://accounts.x.ai/device")
    assert not _allowed_verification_uri("grok_subscription", "https://user:pass@x.ai/device")
