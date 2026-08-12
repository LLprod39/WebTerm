from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.db import OperationalError

from app.ai_runtime import (
    ExecutionMode,
    LLMExecutionContext,
    ProviderBinding,
    ProviderEventType,
    ProviderEventV1,
    ProviderRouteUnavailableError,
    ProviderRuntimeError,
)
from core_ui.models.ai_providers import (
    AIProviderConnection,
    AIProviderConnectionGrant,
    AIProviderInvocation,
    AIProviderPool,
    AIProviderPoolMember,
    AIProviderPreference,
)
from core_ui.models.projects import Project, ProjectMembership
from core_ui.services import ai_subscription_runtime as subscription_runtime
from core_ui.services.ai_provider_access import can_use_connection
from core_ui.services.ai_provider_auth import fence_connection_invocations
from core_ui.services.ai_provider_routing import (
    create_invocation_with_lease,
    release_provider_lease,
    resolve_execution_context,
)
from core_ui.services.ai_subscription_runtime import (
    _mark_invocation_running,
    _persist_fenced_event,
    _provider_span_attributes,
    stream_persisted_subscription_events,
)

pytestmark = pytest.mark.django_db


def _context(
    user: User,
    project: Project | None,
    *,
    purpose: str = "assistant",
    mode: ExecutionMode = ExecutionMode.INTERACTIVE,
    binding: ProviderBinding | None = None,
    idempotency_key: str = "",
) -> LLMExecutionContext:
    return LLMExecutionContext(
        actor_user_id=user.pk,
        project_id=project.pk if project else None,
        purpose=purpose,
        source_kind="test",
        source_id="source-1",
        mode=mode,
        binding=binding,
        idempotency_key=idempotency_key,
    )


def _workspace(user: User) -> Project:
    project = Project.objects.create(name="Ops", slug=f"ops-{user.pk}", owner=user)
    ProjectMembership.objects.create(project=project, user=user, role=ProjectMembership.ROLE_OWNER)
    return project


def _connection(
    *,
    owner: User | None,
    name: str,
    target_id: str = "codex_subscription",
    concurrency_limit: int = 1,
) -> AIProviderConnection:
    return AIProviderConnection.objects.create(
        target_id=target_id,
        scope="personal" if owner else "workspace",
        owner=owner,
        created_by=owner,
        name=name,
        status=AIProviderConnection.STATUS_CONNECTED,
        concurrency_limit=concurrency_limit,
    )


def test_personal_connection_is_owner_only() -> None:
    owner = User.objects.create_user("owner")
    other = User.objects.create_user("other")
    connection = _connection(owner=owner, name="My Codex")

    assert can_use_connection(
        connection,
        user_id=owner.pk,
        project_id=None,
        mode=ExecutionMode.INTERACTIVE,
    ).allowed
    denied = can_use_connection(
        connection,
        user_id=other.pk,
        project_id=None,
        mode=ExecutionMode.INTERACTIVE,
    )
    assert not denied.allowed
    assert "another user" in denied.reason


def test_workspace_grant_distinguishes_interactive_and_unattended() -> None:
    user = User.objects.create_user("operator")
    project = _workspace(user)
    connection = _connection(owner=None, name="Shared Codex")
    AIProviderConnectionGrant.objects.create(
        connection=connection,
        project=project,
        project_role=ProjectMembership.ROLE_OWNER,
        allow_interactive=True,
        allow_unattended=False,
    )

    assert can_use_connection(
        connection,
        user_id=user.pk,
        project_id=project.pk,
        mode=ExecutionMode.INTERACTIVE,
    ).allowed
    unattended = can_use_connection(
        connection,
        user_id=user.pk,
        project_id=project.pk,
        mode=ExecutionMode.UNATTENDED,
    )
    assert not unattended.allowed


def test_explicit_denied_binding_does_not_fall_back_to_user_default() -> None:
    user = User.objects.create_user("operator")
    owned = _connection(owner=user, name="Owned")
    denied = _connection(owner=None, name="Denied")
    AIProviderPreference.objects.create(
        user=user,
        purpose="assistant",
        target_id="codex_subscription",
        connection=owned,
    )

    with pytest.raises(ProviderRouteUnavailableError) as exc_info:
        resolve_execution_context(
            _context(user, None),
            explicit_binding=ProviderBinding("codex_subscription", connection_id=denied.pk),
        )

    assert exc_info.value.details["source"] == "explicit"
    assert "no matching connection grant" in exc_info.value.details["reason"]


def test_user_project_preference_precedes_global_and_workspace_default() -> None:
    user = User.objects.create_user("operator")
    project = _workspace(user)
    global_connection = _connection(owner=user, name="Global")
    project_connection = _connection(owner=user, name="Project")
    workspace_connection = _connection(owner=None, name="Workspace")
    AIProviderConnectionGrant.objects.create(connection=workspace_connection, project=project)
    AIProviderPreference.objects.create(
        user=user,
        purpose="assistant",
        target_id="codex_subscription",
        connection=global_connection,
    )
    AIProviderPreference.objects.create(
        user=user,
        project=project,
        purpose="assistant",
        target_id="codex_subscription",
        connection=project_connection,
    )
    AIProviderPreference.objects.create(
        project=project,
        purpose="assistant",
        target_id="codex_subscription",
        connection=workspace_connection,
    )

    resolved = resolve_execution_context(_context(user, project))

    assert resolved.binding.connection_id == project_connection.pk


def test_pool_selects_free_member_and_pins_it_for_invocation() -> None:
    user = User.objects.create_user("operator")
    project = _workspace(user)
    first = _connection(owner=None, name="Shared 1")
    second = _connection(owner=None, name="Shared 2")
    for connection in (first, second):
        AIProviderConnectionGrant.objects.create(
            connection=connection,
            project=project,
            allow_unattended=True,
        )
    pool = AIProviderPool.objects.create(name="Codex pool", target_id="codex_subscription")
    AIProviderPoolMember.objects.create(pool=pool, connection=first)
    AIProviderPoolMember.objects.create(pool=pool, connection=second)
    binding = ProviderBinding("codex_subscription", pool_id=pool.pk)

    first_invocation, first_lease = create_invocation_with_lease(
        _context(user, project, binding=binding, idempotency_key="pool-1"),
        owner_id="runner-1",
    )
    second_invocation, second_lease = create_invocation_with_lease(
        _context(user, project, binding=binding, idempotency_key="pool-2"),
        owner_id="runner-2",
    )

    assert first_invocation.connection_id == first.pk
    assert second_invocation.connection_id == second.pk
    assert first_lease.connection_id == first.pk
    assert second_lease.connection_id == second.pk


def test_idempotency_reuses_invocation_and_lease() -> None:
    user = User.objects.create_user("operator")
    connection = _connection(owner=user, name="Owned")
    context = _context(
        user,
        None,
        binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
        idempotency_key="same-turn",
    )

    first_invocation, first_lease = create_invocation_with_lease(context, owner_id="runner")
    second_invocation, second_lease = create_invocation_with_lease(context, owner_id="runner")

    assert second_invocation.pk == first_invocation.pk
    assert second_lease.pk == first_lease.pk


def test_released_slot_gets_higher_fencing_token() -> None:
    user = User.objects.create_user("operator")
    connection = _connection(owner=user, name="Owned")
    binding = ProviderBinding("codex_subscription", connection_id=connection.pk)
    _, first_lease = create_invocation_with_lease(
        _context(user, None, binding=binding, idempotency_key="fence-1"),
        owner_id="runner-1",
    )
    release_provider_lease(str(first_lease.lease_token), owner_id="runner-1")

    _, second_lease = create_invocation_with_lease(
        _context(user, None, binding=binding, idempotency_key="fence-2"),
        owner_id="runner-2",
    )

    assert second_lease.slot == first_lease.slot
    assert second_lease.fencing_token > first_lease.fencing_token


def test_busy_direct_connection_returns_typed_capacity_error() -> None:
    user = User.objects.create_user("operator")
    connection = _connection(owner=user, name="Owned")
    binding = ProviderBinding("codex_subscription", connection_id=connection.pk)
    create_invocation_with_lease(
        _context(user, None, binding=binding, idempotency_key="busy-1"),
        owner_id="runner-1",
    )

    with pytest.raises(ProviderRuntimeError) as exc_info:
        create_invocation_with_lease(
            _context(user, None, binding=binding, idempotency_key="busy-2"),
            owner_id="runner-2",
        )

    assert exc_info.value.code == "provider_capacity_unavailable"
    assert exc_info.value.retryable


def test_idempotency_key_is_scoped_and_cannot_replay_another_users_result() -> None:
    first_user = User.objects.create_user("idempotency-first-user")
    second_user = User.objects.create_user("idempotency-second-user")
    first_connection = _connection(owner=first_user, name="First account")
    second_connection = _connection(owner=second_user, name="Second account")
    first, _first_lease = create_invocation_with_lease(
        _context(
            first_user,
            None,
            binding=ProviderBinding("codex_subscription", connection_id=first_connection.pk),
            idempotency_key="shared-guessed-key",
        ),
        owner_id="first-owner",
    )
    second, _second_lease = create_invocation_with_lease(
        _context(
            second_user,
            None,
            binding=ProviderBinding("codex_subscription", connection_id=second_connection.pk),
            idempotency_key="shared-guessed-key",
        ),
        owner_id="second-owner",
    )

    assert second.pk != first.pk
    assert second.user_id == second_user.pk
    assert second.connection_id == second_connection.pk
    assert second.idempotency_scope != first.idempotency_scope


def test_pool_weight_affects_deterministic_slot_selection() -> None:
    user = User.objects.create_user("weighted-operator")
    project = _workspace(user)
    light = _connection(owner=None, name="Light", concurrency_limit=3)
    heavy = _connection(owner=None, name="Heavy", concurrency_limit=3)
    for connection in (light, heavy):
        AIProviderConnectionGrant.objects.create(connection=connection, project=project)
    pool = AIProviderPool.objects.create(name="Weighted pool", target_id="codex_subscription")
    AIProviderPoolMember.objects.create(pool=pool, connection=light, weight=1)
    AIProviderPoolMember.objects.create(pool=pool, connection=heavy, weight=3)
    binding = ProviderBinding("codex_subscription", pool_id=pool.pk)

    selected = []
    for index in range(4):
        invocation, _lease = create_invocation_with_lease(
            _context(user, project, binding=binding, idempotency_key=f"weighted-{index}"),
            owner_id=f"runner-{index}",
        )
        selected.append(invocation.connection_id)

    assert selected.count(heavy.pk) == 3
    assert selected.count(light.pk) == 1


def test_pool_weight_remains_balanced_across_fully_sequential_releases() -> None:
    user = User.objects.create_user("weighted-sequential-operator")
    project = _workspace(user)
    light = _connection(owner=None, name="Sequential light")
    heavy = _connection(owner=None, name="Sequential heavy")
    for connection in (light, heavy):
        AIProviderConnectionGrant.objects.create(connection=connection, project=project)
    pool = AIProviderPool.objects.create(name="Sequential weighted pool", target_id="codex_subscription")
    AIProviderPoolMember.objects.create(pool=pool, connection=light, weight=1)
    AIProviderPoolMember.objects.create(pool=pool, connection=heavy, weight=3)
    binding = ProviderBinding("codex_subscription", pool_id=pool.pk)

    selected: list[int] = []
    for index in range(40):
        owner_id = f"sequential-runner-{index}"
        invocation, lease = create_invocation_with_lease(
            _context(user, project, binding=binding, idempotency_key=f"weighted-sequential-{index}"),
            owner_id=owner_id,
        )
        selected.append(invocation.connection_id)
        release_provider_lease(str(lease.lease_token), owner_id=owner_id)

    assert selected.count(light.pk) == 10
    assert selected.count(heavy.pk) == 30


def test_pool_excludes_unhealthy_and_quota_exhausted_members() -> None:
    user = User.objects.create_user("health-aware-routing-operator")
    project = _workspace(user)
    healthy = _connection(owner=None, name="Healthy")
    unhealthy = _connection(owner=None, name="Unhealthy")
    quota_exhausted = _connection(owner=None, name="Quota exhausted")
    unhealthy.health = {"healthy": False, "status": "unhealthy"}
    unhealthy.save(update_fields=["health"])
    quota_exhausted.limits = {"quota_exhausted": True, "quota_remaining": 0}
    quota_exhausted.save(update_fields=["limits"])
    for connection in (healthy, unhealthy, quota_exhausted):
        AIProviderConnectionGrant.objects.create(connection=connection, project=project)
    pool = AIProviderPool.objects.create(name="Health-aware pool", target_id="codex_subscription")
    for connection in (healthy, unhealthy, quota_exhausted):
        AIProviderPoolMember.objects.create(pool=pool, connection=connection, weight=10)

    invocation, _lease = create_invocation_with_lease(
        _context(
            user,
            project,
            binding=ProviderBinding("codex_subscription", pool_id=pool.pk),
            idempotency_key="health-aware-routing",
        ),
        owner_id="health-aware-runner",
    )

    assert invocation.connection_id == healthy.pk


def test_stale_lease_is_fenced_from_persisting_events() -> None:
    user = User.objects.create_user("fenced-provider-worker")
    connection = _connection(owner=user, name="Owned")
    context = _context(
        user,
        None,
        binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
        idempotency_key="fenced-event",
    )
    invocation, stale = create_invocation_with_lease(context, owner_id="worker-old")
    release_provider_lease(str(stale.lease_token), owner_id="worker-old")
    same, current = create_invocation_with_lease(context, owner_id="worker-new")
    assert same.pk == invocation.pk
    assert current.fencing_token > stale.fencing_token

    with pytest.raises(ProviderRuntimeError, match="ownership was lost"):
        async_to_sync(_persist_fenced_event)(
            invocation.pk,
            ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": "stale"}),
            lease_token=str(stale.lease_token),
            fencing_token=stale.fencing_token,
            owner_id="worker-old",
        )

    invocation.refresh_from_db()
    assert invocation.event_cursor == 0


def test_invocation_lifecycle_is_leased_running_succeeded() -> None:
    user = User.objects.create_user("provider-lifecycle")
    connection = _connection(owner=user, name="Lifecycle")
    invocation, lease = create_invocation_with_lease(
        _context(
            user,
            None,
            binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
            idempotency_key="provider-lifecycle",
        ),
        owner_id="lifecycle-worker",
    )
    invocation.refresh_from_db()
    assert invocation.status == AIProviderInvocation.STATUS_LEASED

    fence = {
        "lease_token": str(lease.lease_token),
        "fencing_token": lease.fencing_token,
        "owner_id": "lifecycle-worker",
    }
    async_to_sync(_mark_invocation_running)(invocation.pk, **fence)
    invocation.refresh_from_db()
    assert invocation.status == AIProviderInvocation.STATUS_RUNNING

    async_to_sync(_persist_fenced_event)(
        invocation.pk,
        ProviderEventV1(ProviderEventType.COMPLETED, {"provider_session_id": "session-ok"}),
        **fence,
    )
    invocation.refresh_from_db()
    assert invocation.status == AIProviderInvocation.STATUS_SUCCEEDED
    assert invocation.error_code == ""


@pytest.mark.asyncio
async def test_invocation_heartbeat_database_failure_fences_and_cancels(monkeypatch) -> None:
    real_asyncio = asyncio

    async def no_wait(_seconds: int) -> None:
        return None

    def failed_heartbeat(*_args, **_kwargs):
        raise OperationalError("provider lease database unavailable")

    class _Client:
        def __init__(self) -> None:
            self.cancelled: list[str] = []

        async def cancel(self, invocation_ref: str) -> None:
            self.cancelled.append(invocation_ref)

    monkeypatch.setattr(
        subscription_runtime,
        "asyncio",
        SimpleNamespace(sleep=no_wait, CancelledError=real_asyncio.CancelledError),
    )
    monkeypatch.setattr(subscription_runtime, "heartbeat_provider_lease", failed_heartbeat)
    lease_lost = real_asyncio.Event()
    client = _Client()

    await subscription_runtime._lease_heartbeat_loop(
        SimpleNamespace(lease_token="lease-db-failure"),
        owner_id="heartbeat-owner",
        lease_lost=lease_lost,
        client=client,
        invocation_ref="invocation-db-failure",
    )

    assert lease_lost.is_set()
    assert client.cancelled == ["invocation-db-failure"]


@pytest.mark.asyncio
async def test_invocation_heartbeat_propagates_task_cancellation(monkeypatch) -> None:
    real_asyncio = asyncio

    async def cancelled_wait(_seconds: int) -> None:
        raise real_asyncio.CancelledError

    class _Client:
        async def cancel(self, _invocation_ref: str) -> None:
            raise AssertionError("task cancellation must not be translated into lease loss")

    monkeypatch.setattr(
        subscription_runtime,
        "asyncio",
        SimpleNamespace(sleep=cancelled_wait, CancelledError=real_asyncio.CancelledError),
    )
    lease_lost = real_asyncio.Event()

    with pytest.raises(real_asyncio.CancelledError):
        await subscription_runtime._lease_heartbeat_loop(
            SimpleNamespace(lease_token="lease-cancelled-task"),
            owner_id="heartbeat-owner",
            lease_lost=lease_lost,
            client=_Client(),
            invocation_ref="invocation-cancelled-task",
        )

    assert not lease_lost.is_set()


def test_usage_event_persists_only_allowlisted_numeric_counters() -> None:
    user = User.objects.create_user("provider-usage-redaction")
    connection = _connection(owner=user, name="Usage redaction")
    invocation, lease = create_invocation_with_lease(
        _context(
            user,
            None,
            binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
            idempotency_key="provider-usage-redaction",
        ),
        owner_id="usage-worker",
    )
    event = ProviderEventV1(
        ProviderEventType.USAGE,
        {
            "input_tokens": 12,
            "cached_input_tokens": 3,
            "output_tokens": 4.5,
            "reasoning_output_tokens": 2,
            "total_tokens": 21,
            "token": "provider-secret-token",
            "device_code": 12345678,
            "prompt": "sensitive prompt contents",
            "nested": {"input_tokens": 999},
            "completion_tokens": True,
        },
    )

    persisted = async_to_sync(_persist_fenced_event)(
        invocation.pk,
        event,
        lease_token=str(lease.lease_token),
        fencing_token=lease.fencing_token,
        owner_id="usage-worker",
    )

    expected = {
        "input_tokens": 12,
        "cached_input_tokens": 3,
        "output_tokens": 4.5,
        "reasoning_output_tokens": 2,
        "total_tokens": 21,
    }
    invocation.refresh_from_db()
    assert persisted.payload == expected
    assert invocation.usage == expected
    assert invocation.event_log[-1]["payload"] == expected


def test_auth_and_quota_events_are_failed_states_with_typed_error_codes() -> None:
    user = User.objects.create_user("provider-error-lifecycle")
    connection = _connection(owner=user, name="Error Lifecycle", concurrency_limit=2)
    cases = [
        (ProviderEventType.AUTH_REQUIRED, "provider_auth_required"),
        (ProviderEventType.LIMIT, "provider_quota_exceeded"),
    ]
    for index, (event_type, error_code) in enumerate(cases):
        invocation, lease = create_invocation_with_lease(
            _context(
                user,
                None,
                binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
                idempotency_key=f"provider-error-{index}",
            ),
            owner_id=f"error-worker-{index}",
        )
        async_to_sync(_persist_fenced_event)(
            invocation.pk,
            ProviderEventV1(event_type, {}),
            lease_token=str(lease.lease_token),
            fencing_token=lease.fencing_token,
            owner_id=f"error-worker-{index}",
        )
        invocation.refresh_from_db()
        assert invocation.status == AIProviderInvocation.STATUS_FAILED
        assert invocation.error_code == error_code
        release_provider_lease(str(lease.lease_token), owner_id=f"error-worker-{index}")


def test_terminal_idempotent_invocation_replays_without_runner_call(monkeypatch) -> None:
    user = User.objects.create_user("replay-provider-worker")
    connection = _connection(owner=user, name="Owned")
    context = _context(
        user,
        None,
        binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
        idempotency_key="replay-terminal",
    )
    invocation, lease = create_invocation_with_lease(context, owner_id="worker-first")
    event = ProviderEventV1(
        ProviderEventType.COMPLETED,
        {"provider_session_id": "provider-thread", "text": "durable result"},
    )
    invocation.status = AIProviderInvocation.STATUS_SUCCEEDED
    invocation.provider_session_id = "provider-thread"
    invocation.terminal_event = event.to_dict()
    invocation.event_cursor = 3
    invocation.save(update_fields=["status", "provider_session_id", "terminal_event", "event_cursor"])
    release_provider_lease(str(lease.lease_token), owner_id="worker-first")

    class _RunnerMustNotBeConstructed:
        def __init__(self):
            raise AssertionError("terminal replay reached runner transport")

    monkeypatch.setattr(
        "core_ui.services.ai_subscription_runtime.AiCliRunnerClient",
        _RunnerMustNotBeConstructed,
    )

    async def collect():
        return [
            item
            async for item in stream_persisted_subscription_events(
                context=context,
                messages=[{"role": "user", "content": "retry"}],
                tools=[],
                system_prompt=None,
            )
        ]

    replayed = async_to_sync(collect)()
    assert replayed == [event]


def test_idempotent_replay_returns_same_durable_text_tool_and_terminal_sequence(monkeypatch) -> None:
    user = User.objects.create_user("replay-sequence-worker")
    connection = _connection(owner=user, name="Replay sequence")
    context = _context(
        user,
        None,
        binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
        idempotency_key="replay-sequence",
    )
    source_events = [
        ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": "safe diagnosis"}),
        ProviderEventV1(
            ProviderEventType.TOOL_REQUEST,
            {"name": "read_console", "arguments": {"lines": 20}},
        ),
        ProviderEventV1(ProviderEventType.TOOL_RESULT, {"name": "read_console", "result": "healthy"}),
        ProviderEventV1(ProviderEventType.COMPLETED, {"provider_session_id": "durable-session"}),
    ]

    class _FakeRunnerClient:
        stream_calls = 0

        async def stream(self, _request):
            type(self).stream_calls += 1
            for item in source_events:
                yield item

        async def cancel(self, _invocation_ref):
            return True

    monkeypatch.setattr(
        "core_ui.services.ai_subscription_runtime.AiCliRunnerClient",
        _FakeRunnerClient,
    )

    async def collect():
        return [
            item
            async for item in stream_persisted_subscription_events(
                context=context,
                messages=[{"role": "user", "content": "diagnose"}],
                tools=[],
                system_prompt=None,
            )
        ]

    first = async_to_sync(collect)()
    replayed = async_to_sync(collect)()

    assert replayed == first
    assert [item.type for item in replayed] == [item.type for item in first]
    assert _FakeRunnerClient.stream_calls == 1


def test_closing_provider_stream_cancels_runner_and_persists_cancelled_terminal(monkeypatch) -> None:
    user = User.objects.create_user("provider-disconnect")
    connection = _connection(owner=user, name="Disconnect account")
    context = _context(
        user,
        None,
        binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
        idempotency_key="provider-disconnect",
    )

    class _DisconnectRunner:
        cancelled: list[str] = []

        async def stream(self, _request):
            yield ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": "partial"})
            await __import__("asyncio").Event().wait()

        async def cancel(self, invocation_ref):
            self.cancelled.append(invocation_ref)
            return True

    monkeypatch.setattr("core_ui.services.ai_subscription_runtime.AiCliRunnerClient", _DisconnectRunner)

    async def close_after_first():
        stream = stream_persisted_subscription_events(
            context=context,
            messages=[{"role": "user", "content": "diagnose"}],
            tools=[],
            system_prompt=None,
        )
        first = await anext(stream)
        await stream.aclose()
        return first

    assert async_to_sync(close_after_first)().payload == {"text": "partial"}
    invocation = AIProviderInvocation.objects.get(idempotency_scope__gt="")
    assert invocation.status == AIProviderInvocation.STATUS_CANCELLED
    assert invocation.terminal_event["payload"]["code"] == "provider_consumer_disconnected"
    assert _DisconnectRunner.cancelled
    assert not invocation.leases.filter(status="active").exists()


def test_revoke_midstream_appends_cancelled_event_for_replay(monkeypatch) -> None:
    user = User.objects.create_user("provider-revoke-replay")
    connection = _connection(owner=user, name="Revoke replay")
    context = _context(
        user,
        None,
        binding=ProviderBinding("codex_subscription", connection_id=connection.pk),
        idempotency_key="provider-revoke-replay",
    )
    invocation, lease = create_invocation_with_lease(context, owner_id="revoke-owner")
    async_to_sync(_persist_fenced_event)(
        invocation.pk,
        ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": "partial before revoke"}),
        lease_token=str(lease.lease_token),
        fencing_token=lease.fencing_token,
        owner_id="revoke-owner",
    )
    assert fence_connection_invocations(connection) == 1

    class _RunnerMustNotBeConstructed:
        def __init__(self):
            raise AssertionError("revoked replay reached runner")

    monkeypatch.setattr(
        "core_ui.services.ai_subscription_runtime.AiCliRunnerClient",
        _RunnerMustNotBeConstructed,
    )

    async def collect():
        return [
            item
            async for item in stream_persisted_subscription_events(
                context=context,
                messages=[],
                tools=[],
                system_prompt=None,
            )
        ]

    replayed = async_to_sync(collect)()
    assert [item.type for item in replayed] == [ProviderEventType.TEXT_DELTA, ProviderEventType.CANCELLED]
    assert replayed[-1].payload["code"] == "provider_connection_revoked"


def test_provider_trace_attributes_are_metadata_only() -> None:
    user = User.objects.create_user("provider-trace-metadata")
    context = _context(
        user,
        None,
        binding=ProviderBinding("codex_subscription", connection_id=123),
        idempotency_key="do-not-export-this-idempotency-secret",
    )
    marker = "PROMPT_SECRET_MARKER_9471"

    attributes = _provider_span_attributes(
        context,
        status=AIProviderInvocation.STATUS_FAILED,
        error_code="provider_timeout",
    )

    assert set(attributes) == {
        "ai.provider.target",
        "ai.provider.source_kind",
        "ai.provider.status",
        "ai.provider.error_code",
    }
    serialized = repr(attributes)
    assert marker not in serialized
    assert context.idempotency_key not in serialized
    assert "prompt" not in serialized.lower()
