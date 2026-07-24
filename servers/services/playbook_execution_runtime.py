"""Bind isolated Ansible execution to one validated queue claim."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.utils import timezone

from servers.models import PlaybookRun
from servers.services.ansible_docker_runtime import (
    AnsibleRuntimeIdentity,
    bind_isolated_runtime_identity,
)
from servers.services.playbook_runner_support import PlaybookRunExecutionFence


def prepare_claim_runtime(
    run: PlaybookRun,
    detection: dict[str, Any],
    fence: PlaybookRunExecutionFence | None,
    hosts_total: int,
    save_run: Callable[..., bool],
) -> tuple[AnsibleRuntimeIdentity | None, bool]:
    fingerprint = run.execution_fingerprint if isinstance(run.execution_fingerprint, dict) else {}
    identity, error = bind_isolated_runtime_identity(
        run_id=run.id,
        dispatch_id=fence.dispatch_id if fence else None,
        attempt_count=fence.attempt_count if fence else None,
        expected_digest=str(fingerprint.get("runtime_digest") or ""),
        actual_digest=str(detection.get("runtime_digest") or ""),
        isolation_required=bool(detection.get("isolation_required")),
    )
    if not error:
        return identity, True
    save_run(
        status=PlaybookRun.STATUS_FAILED,
        error_message=error,
        finished_at=timezone.now(),
        summary={
            "engine": "ansible",
            "hosts_total": hosts_total,
            "runtime_mismatch": "runtime changed" in error.lower(),
        },
    )
    return None, False
