from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from servers.models import BackgroundWorkerState, PlaybookRun, PlaybookRunDispatch
from servers.playbooks.dispatch import (
    cancel_playbook_dispatch_for_run,
    claim_next_playbook_dispatch,
    complete_playbook_dispatch,
    enqueue_playbook_run_dispatch,
    execute_playbook_dispatch,
    recover_expired_playbook_dispatches,
)
from servers.services.ansible_docker_runtime import RuntimeCleanupResult


def _run(user: User) -> PlaybookRun:
    return PlaybookRun.objects.create(
        user=user,
        playbook_snapshot={"name": "Runtime lifecycle", "source_yaml": "- hosts: all\n  tasks: []\n"},
        target_server_ids=[],
        options={"engine": "ansible"},
    )


@pytest.mark.django_db(transaction=True)
def test_retry_safe_claim_is_not_requeued_until_exact_runtime_cleanup_succeeds(monkeypatch):
    user = User.objects.create_user(username="playbook-runtime-cleanup-fence", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run, mutation_safe_to_retry=True)
    claimed = claim_next_playbook_dispatch(worker_name="dead-worker", global_concurrency=1)
    assert claimed is not None
    PlaybookRun.objects.filter(pk=run.id).update(status=PlaybookRun.STATUS_RUNNING)
    PlaybookRunDispatch.objects.filter(pk=dispatch.id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    identities = []
    monkeypatch.setattr(
        "servers.services.ansible_docker_runtime.isolated_execution_required",
        lambda: True,
    )

    def cleanup(identity):
        identities.append(identity)
        return RuntimeCleanupResult("unavailable", "Docker daemon unavailable")

    monkeypatch.setattr(
        "servers.services.ansible_docker_runtime.cleanup_ansible_runtime_job",
        cleanup,
    )

    summary = recover_expired_playbook_dispatches()

    dispatch.refresh_from_db()
    run.refresh_from_db()
    assert summary == {"requeued": 0, "interrupted": 1, "canceled": 0}
    assert dispatch.status == PlaybookRunDispatch.STATUS_INTERRUPTED
    assert run.status == PlaybookRun.STATUS_FAILED
    assert identities[0].run_id == run.id
    assert identities[0].dispatch_id == dispatch.id
    assert identities[0].attempt_count == claimed.attempt_count


@pytest.mark.django_db(transaction=True)
def test_cancel_claimed_dispatch_removes_exact_daemon_job_on_commit(monkeypatch):
    user = User.objects.create_user(username="playbook-runtime-cancel", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run)
    claimed = claim_next_playbook_dispatch(worker_name="worker", global_concurrency=1)
    assert claimed is not None
    identities = []
    monkeypatch.setattr(
        "servers.services.ansible_docker_runtime.isolated_execution_required",
        lambda: True,
    )

    def cleanup(identity):
        identities.append(identity)
        return RuntimeCleanupResult("removed")

    monkeypatch.setattr(
        "servers.services.ansible_docker_runtime.cleanup_ansible_runtime_job",
        cleanup,
    )

    assert cancel_playbook_dispatch_for_run(run.id) is True

    assert len(identities) == 1
    assert identities[0].slug == f"pb-r{run.id}-d{dispatch.id}-a{claimed.attempt_count}"


@pytest.mark.django_db(transaction=True)
def test_worker_shutdown_event_cancels_foreground_execution_without_stale_writes(monkeypatch):
    user = User.objects.create_user(username="playbook-worker-shutdown", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run)
    claim_next_playbook_dispatch(worker_name="worker", lease_seconds=60, global_concurrency=1)
    shutdown = threading.Event()
    shutdown.set()
    observed = []

    def fake_execute(_run_id: int, *, lease_check, **_kwargs) -> None:
        observed.append(lease_check())

    monkeypatch.setattr("servers.playbooks.worker.execute_playbook_run", fake_execute)

    execute_playbook_dispatch(
        dispatch.id,
        worker_name="worker",
        lease_seconds=60,
        shutdown_event=shutdown,
    )

    dispatch.refresh_from_db()
    assert observed == [False]
    assert dispatch.status == PlaybookRunDispatch.STATUS_CLAIMED


@pytest.mark.django_db(transaction=True)
def test_execution_plane_command_passes_shutdown_event_to_dispatch(monkeypatch):
    user = User.objects.create_user(username="playbook-dispatch-command", password="x")
    run = _run(user)
    dispatch = enqueue_playbook_run_dispatch(run=run)
    observed = []

    def fake_execute(
        dispatch_id: int,
        *,
        worker_name: str,
        lease_seconds: int,
        shutdown_event=None,
    ) -> None:
        observed.append(shutdown_event)
        complete_playbook_dispatch(dispatch_id, worker_name=worker_name)

    monkeypatch.setattr(
        "servers.management.commands.run_playbook_execution_plane.execute_playbook_dispatch",
        fake_execute,
    )
    runtime_fingerprint = {
        "method": "isolated-execution-worker",
        "available": True,
        "runtime_digest": "sha256:" + "a" * 64,
    }
    monkeypatch.setattr(
        "servers.management.commands.run_playbook_execution_plane._execution_runtime_fingerprint",
        lambda: runtime_fingerprint,
    )

    call_command(
        "run_playbook_execution_plane",
        once=True,
        worker_key="pytest-playbook-worker",
        global_concurrency=1,
    )

    dispatch.refresh_from_db()
    assert dispatch.status == PlaybookRunDispatch.STATUS_COMPLETED
    assert isinstance(observed[0], threading.Event)
    worker = BackgroundWorkerState.objects.get(worker_kind="playbook_execution", worker_key="pytest-playbook-worker")
    assert worker.last_summary["runtime_fingerprint"] == runtime_fingerprint


@pytest.mark.django_db
def test_validation_uses_live_execution_worker_fingerprint():
    from servers.services.playbooks.validation import runtime_fingerprint

    fingerprint = {
        "method": "isolated-execution-worker",
        "available": True,
        "runtime_digest": "sha256:" + "b" * 64,
        "image": "webterm-ansible:latest",
    }
    BackgroundWorkerState.objects.create(
        worker_kind="playbook_execution",
        worker_key="runtime-source",
        status=BackgroundWorkerState.STATUS_RUNNING,
        heartbeat_at=timezone.now(),
        lease_expires_at=timezone.now() + timedelta(minutes=3),
        last_summary={"runtime_fingerprint": fingerprint},
    )

    assert runtime_fingerprint() == fingerprint
