"""Durable execution-plane contract for prepared playbook runs."""

from __future__ import annotations

import importlib
import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from core_ui.managed_secrets import (
    get_playbook_run_master_password,
    get_playbook_run_variables,
    set_playbook_run_master_password,
    set_playbook_run_variables,
)
from core_ui.models import ManagedSecret
from servers.models import PlaybookRun, PlaybookRunDispatch
from servers.playbooks.dispatch import (
    cancel_playbook_dispatch_for_run,
    claim_next_playbook_dispatch,
    complete_playbook_dispatch,
    enqueue_playbook_run_dispatch,
    execute_playbook_dispatch,
    heartbeat_playbook_dispatch,
    recover_expired_playbook_dispatches,
)
from servers.services.playbook_runner_support import _persist_run


def _run(user: User, *, options: dict | None = None) -> PlaybookRun:
    return PlaybookRun.objects.create(
        user=user,
        playbook_snapshot={"name": "Durable demo", "source_yaml": "- hosts: all\n  tasks: []\n"},
        target_server_ids=[],
        options=options or {"engine": "ansible"},
    )


@pytest.mark.django_db
def test_enqueue_is_idempotent_and_dispatch_never_contains_runtime_secrets():
    user = User.objects.create_user(username="playbook-dispatch-secret", password="x")
    run = _run(
        user,
        options={
            "engine": "ansible",
            "dry_run": False,
            "extra_vars": {"database_password": "extra-var-secret"},
        },
    )

    first = enqueue_playbook_run_dispatch(run=run, master_password="master-password-secret")
    second = enqueue_playbook_run_dispatch(run=run, master_password="master-password-secret")

    assert first.id == second.id
    assert PlaybookRunDispatch.objects.filter(run=run).count() == 1
    assert get_playbook_run_master_password(run.id) == "master-password-secret"
    persisted_dispatch = json.dumps(
        {
            "metadata": first.metadata,
            "error": first.error,
            "claimed_by": first.claimed_by,
        },
        sort_keys=True,
    )
    assert "master-password-secret" not in persisted_dispatch
    assert "extra-var-secret" not in persisted_dispatch
    assert "extra_vars" not in persisted_dispatch


@pytest.mark.django_db
def test_legacy_start_facade_enqueues_without_spawning_execution_thread(monkeypatch):
    from servers.services import playbook_runner

    user = User.objects.create_user(username="playbook-start-facade", password="x")
    run = _run(user)

    def forbidden_thread(*_args, **_kwargs):
        raise AssertionError("execution must not start in an HTTP daemon thread")

    monkeypatch.setattr(playbook_runner.threading, "Thread", forbidden_thread)
    playbook_runner.start_playbook_run_async(run.id, master_password="queued-secret")

    dispatch = PlaybookRunDispatch.objects.get(run=run)
    assert dispatch.status == PlaybookRunDispatch.STATUS_QUEUED
    assert get_playbook_run_master_password(run.id) == "queued-secret"


@pytest.mark.django_db
def test_claim_enforces_global_concurrency_across_workers():
    user = User.objects.create_user(username="playbook-dispatch-limit", password="x")
    first = enqueue_playbook_run_dispatch(run=_run(user))
    second = enqueue_playbook_run_dispatch(run=_run(user))

    claimed = claim_next_playbook_dispatch(
        worker_name="worker-a",
        lease_seconds=60,
        global_concurrency=1,
    )
    assert claimed is not None and claimed.id == first.id
    assert (
        claim_next_playbook_dispatch(
            worker_name="worker-b",
            lease_seconds=60,
            global_concurrency=1,
        )
        is None
    )

    complete_playbook_dispatch(first.id, worker_name="worker-a")
    claimed_second = claim_next_playbook_dispatch(
        worker_name="worker-b",
        lease_seconds=60,
        global_concurrency=1,
    )
    assert claimed_second is not None and claimed_second.id == second.id


@pytest.mark.django_db
def test_claim_enforces_user_cap_without_blocking_another_user():
    first_user = User.objects.create_user(username="playbook-user-cap-a", password="x")
    second_user = User.objects.create_user(username="playbook-user-cap-b", password="x")
    first = enqueue_playbook_run_dispatch(run=_run(first_user))
    waiting_same_user = enqueue_playbook_run_dispatch(run=_run(first_user))
    other_user = enqueue_playbook_run_dispatch(run=_run(second_user))

    claimed_first = claim_next_playbook_dispatch(
        worker_name="worker-a",
        global_concurrency=3,
        per_user_concurrency=1,
    )
    claimed_other = claim_next_playbook_dispatch(
        worker_name="worker-b",
        global_concurrency=3,
        per_user_concurrency=1,
    )

    assert claimed_first is not None and claimed_first.id == first.id
    assert claimed_other is not None and claimed_other.id == other_user.id
    assert (
        claim_next_playbook_dispatch(
            worker_name="worker-c",
            global_concurrency=3,
            per_user_concurrency=1,
        )
        is None
    )

    complete_playbook_dispatch(first.id, worker_name="worker-a")
    claimed_waiting = claim_next_playbook_dispatch(
        worker_name="worker-c",
        global_concurrency=3,
        per_user_concurrency=1,
    )
    assert claimed_waiting is not None and claimed_waiting.id == waiting_same_user.id


@pytest.mark.django_db(transaction=True)
def test_claim_rechecks_target_authorization_after_preflight(monkeypatch):
    from servers.models import Server

    user = User.objects.create_user(username="playbook-claim-auth", password="x")
    server = Server.objects.create(
        user=user,
        name="revoked-target",
        host="127.0.0.30",
        username="root",
        auth_method="key",
        is_active=True,
    )
    run = _run(user)
    run.target_server_ids = [server.id]
    run.save(update_fields=["target_server_ids"])
    dispatch = enqueue_playbook_run_dispatch(run=run)
    server.is_active = False
    server.save(update_fields=["is_active"])
    monkeypatch.setattr(
        "core_ui.services.operator_async.notify_playbook_run_terminal",
        lambda _run_id: None,
    )

    assert claim_next_playbook_dispatch(worker_name="worker", global_concurrency=1) is None

    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_FAILED
    assert dispatch.status == PlaybookRunDispatch.STATUS_FAILED
    assert "authorization or connection identity changed" in dispatch.error.lower()


@pytest.mark.django_db(transaction=True)
def test_claim_rechecks_target_connection_identity_after_preflight(monkeypatch):
    from servers.models import Server
    from servers.services.playbooks.target_identity import target_connection_identity_hashes

    user = User.objects.create_user(username="playbook-claim-identity", password="x")
    server = Server.objects.create(
        user=user,
        name="changed-endpoint",
        host="127.0.0.31",
        username="root",
        auth_method="key",
        is_active=True,
    )
    run = _run(user)
    run.target_server_ids = [server.id]
    run.playbook_snapshot = {
        **run.playbook_snapshot,
        "target_connection_identities": target_connection_identity_hashes([server]),
    }
    run.save(update_fields=["target_server_ids", "playbook_snapshot"])
    dispatch = enqueue_playbook_run_dispatch(run=run)
    server.host = "127.0.0.32"
    server.save(update_fields=["host"])
    monkeypatch.setattr(
        "core_ui.services.operator_async.notify_playbook_run_terminal",
        lambda _run_id: None,
    )

    assert claim_next_playbook_dispatch(worker_name="worker", global_concurrency=1) is None

    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_FAILED
    assert dispatch.status == PlaybookRunDispatch.STATUS_FAILED
    assert run.summary["authorization_or_identity_changed"] is True


@pytest.mark.django_db
def test_workspace_migration_interrupts_active_legacy_runs_and_cleans_secrets():
    from django.apps import apps as django_apps

    user = User.objects.create_user(username="playbook-migration-cutover", password="x")
    pending = _run(user)
    running = _run(user)
    PlaybookRun.objects.filter(pk=running.id).update(status=PlaybookRun.STATUS_RUNNING)
    for run in (pending, running):
        set_playbook_run_variables(run.id, {"token": f"secret-{run.id}"})
        set_playbook_run_master_password(run.id, f"master-{run.id}")

    migration = importlib.import_module("servers.migrations.0048_backfill_playbook_workspace")
    assert migration.interrupt_legacy_playbook_runs(django_apps) == 2

    for run in (pending, running):
        run.refresh_from_db()
        assert run.status == PlaybookRun.STATUS_FAILED
        assert run.summary == {
            "interrupted": True,
            "reason": "durable_execution_migration",
            "replayed": False,
        }
        assert run.finished_at is not None
        assert run.terminal_notified_at is not None
        assert not PlaybookRunDispatch.objects.filter(run=run).exists()
        assert not ManagedSecret.objects.filter(
            namespace__in=["playbook_run_variables", "playbook_run_master_password"],
            object_id=run.id,
        ).exists()


@pytest.mark.django_db(transaction=True)
def test_expired_mutating_claim_is_interrupted_and_never_requeued(monkeypatch):
    user = User.objects.create_user(username="playbook-dispatch-interrupted", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run, master_password="temporary-master-password")
    PlaybookRun.objects.filter(pk=run.id).update(status=PlaybookRun.STATUS_RUNNING)
    PlaybookRunDispatch.objects.filter(pk=dispatch.id).update(
        status=PlaybookRunDispatch.STATUS_CLAIMED,
        claimed_by="dead-worker",
        lease_expires_at=timezone.now() - timedelta(seconds=1),
        mutation_safe_to_retry=False,
    )
    monkeypatch.setattr(
        "core_ui.services.operator_async.schedule_async_resume_on_commit",
        lambda **_kwargs: None,
    )

    summary = recover_expired_playbook_dispatches()

    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert summary == {"requeued": 0, "interrupted": 1, "canceled": 0}
    assert dispatch.status == PlaybookRunDispatch.STATUS_INTERRUPTED
    assert run.status == PlaybookRun.STATUS_FAILED
    assert "lease expired" in run.error_message.lower()
    assert get_playbook_run_master_password(run.id) == ""
    assert claim_next_playbook_dispatch(worker_name="other-worker", global_concurrency=10) is None


@pytest.mark.django_db
def test_only_explicitly_retry_safe_expired_claim_is_requeued():
    user = User.objects.create_user(username="playbook-dispatch-retry", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run, master_password="keep-until-retry")
    PlaybookRun.objects.filter(pk=run.id).update(status=PlaybookRun.STATUS_RUNNING)
    PlaybookRunDispatch.objects.filter(pk=dispatch.id).update(
        status=PlaybookRunDispatch.STATUS_CLAIMED,
        claimed_by="dead-worker",
        lease_expires_at=timezone.now() - timedelta(seconds=1),
        mutation_safe_to_retry=True,
    )

    summary = recover_expired_playbook_dispatches()

    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert summary == {"requeued": 1, "interrupted": 0, "canceled": 0}
    assert dispatch.status == PlaybookRunDispatch.STATUS_QUEUED
    assert run.status == PlaybookRun.STATUS_PENDING
    assert get_playbook_run_master_password(run.id) == "keep-until-retry"
    assert claim_next_playbook_dispatch(worker_name="retry-worker", global_concurrency=1).id == dispatch.id


@pytest.mark.django_db
def test_heartbeat_attempt_token_rejects_a_stale_worker_after_reclaim():
    user = User.objects.create_user(username="playbook-attempt-fence", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run, mutation_safe_to_retry=True)
    first_claim = claim_next_playbook_dispatch(worker_name="same-worker", global_concurrency=1)
    assert first_claim is not None
    first_attempt = first_claim.attempt_count
    PlaybookRunDispatch.objects.filter(pk=dispatch.id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    recover_expired_playbook_dispatches()
    second_claim = claim_next_playbook_dispatch(worker_name="same-worker", global_concurrency=1)
    assert second_claim is not None and second_claim.attempt_count == first_attempt + 1

    assert (
        heartbeat_playbook_dispatch(
            dispatch.id,
            worker_name="same-worker",
            attempt_count=first_attempt,
        )
        is False
    )
    assert (
        heartbeat_playbook_dispatch(
            dispatch.id,
            worker_name="same-worker",
            attempt_count=second_claim.attempt_count,
        )
        is True
    )


@pytest.mark.django_db(transaction=True)
def test_lost_lease_stops_stale_worker_and_fences_terminal_writes(monkeypatch):
    user = User.objects.create_user(username="playbook-stale-worker", password="x")
    run = _run(user)
    set_playbook_run_variables(run.id, {"token": "keep-for-new-attempt"})
    dispatch = enqueue_playbook_run_dispatch(
        run=run,
        master_password="keep-master-for-new-attempt",
        mutation_safe_to_retry=True,
    )
    claim_next_playbook_dispatch(worker_name="stale-worker", lease_seconds=60, global_concurrency=1)

    def lose_claim(run_id: int, *, execution_fence, lease_check, **_kwargs) -> None:
        PlaybookRunDispatch.objects.filter(pk=dispatch.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1),
        )
        assert recover_expired_playbook_dispatches()["requeued"] == 1
        assert lease_check() is False
        assert (
            _persist_run(
                run_id,
                execution_fence=execution_fence,
                status=PlaybookRun.STATUS_COMPLETED,
            )
            is False
        )

    monkeypatch.setattr("servers.playbooks.worker.execute_playbook_run", lose_claim)

    execute_playbook_dispatch(dispatch.id, worker_name="stale-worker", lease_seconds=60)

    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_PENDING
    assert dispatch.status == PlaybookRunDispatch.STATUS_QUEUED
    assert get_playbook_run_master_password(run.id) == "keep-master-for-new-attempt"
    assert get_playbook_run_variables(run.id) == {"token": "keep-for-new-attempt"}


@pytest.mark.django_db(transaction=True)
def test_canceling_queued_dispatch_finishes_run_without_execution(monkeypatch):
    user = User.objects.create_user(username="playbook-dispatch-cancel", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run, master_password="cancel-me")
    monkeypatch.setattr(
        "core_ui.services.operator_async.schedule_async_resume_on_commit",
        lambda **_kwargs: None,
    )

    result = cancel_playbook_dispatch_for_run(run.id, reason="user_requested")

    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert result is True
    assert run.cancel_requested is True
    assert run.status == PlaybookRun.STATUS_CANCELLED
    assert dispatch.status == PlaybookRunDispatch.STATUS_CANCELED
    assert get_playbook_run_master_password(run.id) == ""
    assert claim_next_playbook_dispatch(worker_name="worker", global_concurrency=1) is None


@pytest.mark.django_db(transaction=True)
def test_cancel_api_uses_durable_dispatch_state(monkeypatch):
    user = User.objects.create_user(username="playbook-dispatch-cancel-api", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run)
    monkeypatch.setattr(
        "core_ui.services.operator_async.schedule_async_resume_on_commit",
        lambda **_kwargs: None,
    )
    client = Client()
    client.force_login(user)

    response = client.post(f"/servers/api/playbooks/runs/{run.id}/cancel/")

    assert response.status_code == 200
    assert response.json()["run"]["status"] == PlaybookRun.STATUS_CANCELLED
    dispatch.refresh_from_db()
    assert dispatch.status == PlaybookRunDispatch.STATUS_CANCELED


@pytest.mark.django_db(transaction=True)
def test_worker_executes_claimed_run_with_jit_secret_and_cleans_it(monkeypatch):
    user = User.objects.create_user(username="playbook-dispatch-worker", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run, master_password="jit-master-password")
    claim_next_playbook_dispatch(worker_name="worker", lease_seconds=60, global_concurrency=1)
    received: list[tuple[int, str]] = []

    def fake_execute(run_id: int, *, master_password: str = "", **_kwargs) -> None:
        from servers.services.playbook_run_state import transition_playbook_run

        received.append((run_id, master_password))
        transition_playbook_run(run_id, PlaybookRun.STATUS_COMPLETED, summary={"hosts_ok": 1})

    monkeypatch.setattr("servers.playbooks.worker.execute_playbook_run", fake_execute)
    monkeypatch.setattr(
        "core_ui.services.operator_async.schedule_async_resume_on_commit",
        lambda **_kwargs: None,
    )

    execute_playbook_dispatch(dispatch.id, worker_name="worker", lease_seconds=60)

    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert received == [(run.id, "jit-master-password")]
    assert run.status == PlaybookRun.STATUS_COMPLETED
    assert dispatch.status == PlaybookRunDispatch.STATUS_COMPLETED
    assert get_playbook_run_master_password(run.id) == ""


@pytest.mark.django_db(transaction=True)
def test_worker_failure_redacts_jit_secrets_from_dispatch_error(monkeypatch):
    user = User.objects.create_user(username="playbook-dispatch-redaction", password="x")
    run = _run(user)
    set_playbook_run_variables(run.id, {"nested": {"api_token": "runtime-variable-secret"}})
    dispatch = enqueue_playbook_run_dispatch(run=run, master_password="runtime-master-secret")
    claim_next_playbook_dispatch(worker_name="worker", lease_seconds=60, global_concurrency=1)

    def fail_with_secrets(run_id: int, *, master_password: str = "", **_kwargs) -> None:
        raise RuntimeError(f"failed with {master_password} and runtime-variable-secret")

    monkeypatch.setattr("servers.playbooks.worker.execute_playbook_run", fail_with_secrets)
    monkeypatch.setattr(
        "core_ui.services.operator_async.schedule_async_resume_on_commit",
        lambda **_kwargs: None,
    )

    with pytest.raises(RuntimeError):
        execute_playbook_dispatch(dispatch.id, worker_name="worker", lease_seconds=60)

    dispatch.refresh_from_db()
    assert dispatch.status == PlaybookRunDispatch.STATUS_FAILED
    assert "runtime-master-secret" not in dispatch.error
    assert "runtime-variable-secret" not in dispatch.error
    assert "[REDACTED]" in dispatch.error
    assert get_playbook_run_master_password(run.id) == ""
    assert get_playbook_run_variables(run.id) == {}
