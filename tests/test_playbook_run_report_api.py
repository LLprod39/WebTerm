from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from servers.models import Playbook, PlaybookRun
from servers.models_playbook_workspace import PlaybookBindingProfile
from servers.services.playbook_run_report import _task_counts
from servers.services.playbook_runner_support import _persist_run
from servers.views.server_playbook_run_report_views import (
    playbook_run_report,
    playbook_run_report_export,
    playbook_run_report_host,
    playbook_run_report_list,
    playbook_run_report_log,
    playbook_run_retry_context,
)
from servers.views.server_playbook_serializers import _serialize_run
from tests.servers_api_smoke_harness import grant_feature


def _owner(username: str) -> User:
    user = User.objects.create_user(username=username, password="x")
    grant_feature(user, "automation")
    return user


def _request(user: User, path: str, *, etag: str = ""):
    headers = {"HTTP_IF_NONE_MATCH": etag} if etag else {}
    request = RequestFactory().get(path, **headers)
    request.user = user
    return request


def _json(response):
    return json.loads(response.content.decode("utf-8"))


def _playbook(user: User, name: str = "Health snapshot") -> Playbook:
    return Playbook.objects.create(user=user, name=name, kind=Playbook.KIND_ANSIBLE)


def test_task_counts_keep_changed_unreachable_and_cancelled_distinct():
    counts = _task_counts(
        [
            {"status": "success"},
            {"status": "changed"},
            {"status": "error"},
            {"status": "unreachable"},
            {"status": "skipped"},
            {"status": "cancelled"},
            {"status": "running"},
            {"status": "pending"},
        ]
    )

    assert counts == {
        "total": 8,
        "ok": 1,
        "changed": 1,
        "failed": 1,
        "unreachable": 1,
        "skipped": 1,
        "cancelled": 1,
        "running": 1,
        "pending": 1,
    }


@pytest.mark.django_db
def test_report_etag_failure_host_retry_and_export_are_redacted():
    owner = _owner("playbook-report-owner")
    playbook = _playbook(owner)
    binding_profile = PlaybookBindingProfile.objects.create(
        playbook=playbook,
        user=owner,
        name="Production checks",
        content_hash="a" * 64,
    )
    started_at = timezone.now() - timedelta(seconds=5)
    finished_at = started_at + timedelta(seconds=5)
    run = PlaybookRun.objects.create(
        user=owner,
        playbook=playbook,
        status=PlaybookRun.STATUS_RUNNING,
        playbook_snapshot={"name": "Health snapshot"},
        binding_profile=binding_profile,
        target_server_ids=[41],
        started_at=started_at,
        options={"engine": "ansible", "dry_run": False, "extra_vars": {"password": "must-not-leak"}},
        variable_manifest={
            "names": ["region", "admin_password"],
            "managed_secret_names": ["admin_password"],
            "values_redacted": True,
        },
        progress={
            "state_version": 7,
            "log_start_cursor": 20,
            "log_end_cursor": 20,
            "log_truncated": True,
        },
    )
    assert _persist_run(
        run.id,
        status=PlaybookRun.STATUS_FAILED,
        progress={
            "engine": "ansible",
            "task_number": 4,
            "tasks_total": 10,
            "total_kind": "estimated",
            "task": "api_key=persist-progress-secret",
        },
        summary={"hosts_total": 1, "hosts_failed": 1, "note": "password=persist-summary-secret"},
        host_results=[
            {
                "server_id": 41,
                "server_name": "node-a",
                "host": "10.0.0.41",
                "status": "failed",
                "task_results": [
                    {
                        "task_id": "install",
                        "command": "install package",
                        "description": "Install package",
                        "status": "error",
                        "output": "password=hunter2-secret",
                        "exit_code": 1,
                    }
                ],
            }
        ],
        live_log="Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
        error_message="Task failed: token=private-value-123456",
        finished_at=finished_at,
    )
    run.refresh_from_db()
    persisted = json.dumps(
        {
            "progress": run.progress,
            "summary": run.summary,
            "host_results": run.host_results,
            "live_log": run.live_log,
            "error_message": run.error_message,
        }
    )
    for secret in (
        "persist-progress-secret",
        "persist-summary-secret",
        "hunter2-secret",
        "abcdefghijklmnopqrstuvwxyz123456",
        "private-value-123456",
    ):
        assert secret not in persisted

    response = playbook_run_report(_request(owner, "/report/"), run.id)

    assert response.status_code == 200
    payload = _json(response)["report"]
    assert payload["progress"]["phase"] == "finished"
    assert payload["progress"]["total_kind"] == "estimated"
    assert payload["progress"]["percent"] is None
    assert payload["run"]["duration_ms"] == 5_000
    assert payload["run"]["binding_profile_name"] == "Production checks"
    assert payload["failure"]["code"] == "task_failed"
    assert payload["actions"]["can_export"] is True
    assert "must-not-leak" not in response.content.decode()
    assert "hunter2-secret" not in response.content.decode()
    assert response["ETag"]
    not_modified = playbook_run_report(_request(owner, "/report/", etag=response["ETag"]), run.id)
    assert not_modified.status_code == 304

    host_response = playbook_run_report_host(_request(owner, "/host/"), run.id, 41)
    assert host_response.status_code == 200
    assert "hunter2-secret" not in host_response.content.decode()
    assert _json(host_response)["host"]["tasks"][0]["status"] == "failed"

    retry = _json(playbook_run_retry_context(_request(owner, "/retry/"), run.id))["retry_context"]
    assert retry["can_retry"] is False  # no immutable revision was retained
    assert retry["failed_server_ids"] == [41]
    assert "extra_vars" not in retry["options"]
    assert retry["required_variable_names"] == ["region", "admin_password"]

    export_response = playbook_run_report_export(_request(owner, "/export/"), run.id)
    assert export_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        assert set(archive.namelist()) == {
            "report.json",
            "report.md",
            "execution.log",
            "hosts/41.json",
            "checksums.sha256",
            "manifest.json",
        }
        combined = b"\n".join(archive.read(name) for name in archive.namelist()).decode("utf-8")
        manifest = json.loads(archive.read("manifest.json"))
        checksums = archive.read("checksums.sha256").decode("utf-8").splitlines()
        for line in checksums:
            expected_hash, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected_hash
    assert "hunter2-secret" not in combined
    assert "abcdefghijklmnopqrstuvwxyz123456" not in combined
    assert manifest["log_truncated"] is True
    assert manifest["log_scope"] == "available_redacted_tail"
    export_not_modified = playbook_run_report_export(_request(owner, "/export/", etag=export_response["ETag"]), run.id)
    assert export_not_modified.status_code == 304

    stranger = _owner("playbook-report-stranger")
    with pytest.raises(Http404):
        playbook_run_report(_request(stranger, "/report/"), run.id)


@pytest.mark.django_db
def test_progress_persistence_versions_phases_and_monotonic_log_cursors():
    owner = _owner("playbook-progress-owner")
    run = PlaybookRun.objects.create(
        user=owner,
        status=PlaybookRun.STATUS_RUNNING,
        progress={"state_version": 5, "engine": "shell", "tasks_total": 4, "tasks_done": 1},
        live_log="abc",
    )

    assert _persist_run(
        run.id,
        live_log="abcdef",
        progress={"engine": "shell", "tasks_total": 4, "tasks_done": 2, "total_kind": "exact"},
    )
    run.refresh_from_db()
    assert run.progress["state_version"] == 6
    assert run.progress["phase"] == "executing"
    assert run.progress["total_kind"] == "exact"
    assert (run.progress["log_start_cursor"], run.progress["log_end_cursor"]) == (0, 6)

    assert _persist_run(run.id, live_log="defXYZ", progress={"tasks_done": 3})
    run.refresh_from_db()
    assert run.progress["state_version"] == 7
    assert (run.progress["log_start_cursor"], run.progress["log_end_cursor"]) == (3, 9)
    assert run.progress["log_truncated"] is True

    assert _persist_run(
        run.id,
        status=PlaybookRun.STATUS_FAILED,
        error_message="boom",
        finished_at=timezone.now(),
    )
    run.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_FAILED
    assert run.progress["state_version"] == 8
    assert run.progress["phase"] == "finished"


@pytest.mark.django_db
def test_delta_log_reset_active_export_and_filtered_cursor_page():
    owner = _owner("playbook-report-page-owner")
    playbook = _playbook(owner, "Patch fleet")
    first = PlaybookRun.objects.create(
        user=owner,
        playbook=playbook,
        status=PlaybookRun.STATUS_RUNNING,
        playbook_snapshot={"name": "Patch fleet"},
        started_at=timezone.now() - timedelta(seconds=2),
        progress={
            "state_version": 3,
            "engine": "shell",
            "tasks_total": 8,
            "tasks_done": 2,
            "total_kind": "exact",
            "log_start_cursor": 10,
            "log_end_cursor": 16,
            "log_truncated": True,
        },
        live_log="abcdef",
        variable_manifest={"names": "not-a-list", "managed_secret_names": "also-not-a-list"},
    )
    PlaybookRun.objects.create(user=owner, playbook=playbook, status=PlaybookRun.STATUS_FAILED)
    third = PlaybookRun.objects.create(user=owner, playbook=playbook, status=PlaybookRun.STATUS_RUNNING)

    reset = _json(playbook_run_report_log(_request(owner, "/log/?after=0&limit_chars=2"), first.id))
    assert reset["reset_required"] is True
    assert reset["cursor"] == 10 and reset["next_cursor"] == 12 and reset["text"] == "ab"
    delta = _json(playbook_run_report_log(_request(owner, "/log/?after=12&limit_chars=2"), first.id))
    assert delta["reset_required"] is False and delta["text"] == "cd" and delta["has_more"] is True

    active_export = playbook_run_report_export(_request(owner, "/export/"), first.id)
    assert active_export.status_code == 409
    assert _json(active_export)["code"] == "run_not_terminal"
    running_report = _json(playbook_run_report(_request(owner, "/report/"), first.id))["report"]
    assert running_report["run"]["duration_ms"] >= 2_000
    retry_context = _json(playbook_run_retry_context(_request(owner, "/retry/"), first.id))["retry_context"]
    assert retry_context["required_variable_names"] == []
    assert retry_context["managed_variable_names"] == []

    page_one = _json(playbook_run_report_list(_request(owner, "/runs/?status=running&limit=1")))
    assert [item["id"] for item in page_one["items"]] == [third.id]
    assert page_one["page"]["has_more"] is True
    page_two = _json(
        playbook_run_report_list(
            _request(owner, f"/runs/?status=running&limit=1&cursor={page_one['page']['next_cursor']}")
        )
    )
    assert [item["id"] for item in page_two["items"]] == [first.id]
    assert "inventory_preview" not in page_two["items"][0]
    assert "execution_fingerprint" not in page_two["items"][0]


@pytest.mark.django_db
def test_legacy_log_cannot_be_reconstructed_with_single_character_cursors():
    owner = _owner("playbook-report-legacy-secret-owner")
    secret = "glpat-abcdefghijklmnopqrstuvwxyz123456"
    raw_log = f"checkout token={secret}\nfinished"
    run = PlaybookRun.objects.create(
        user=owner,
        status=PlaybookRun.STATUS_FAILED,
        live_log=raw_log,
        variable_manifest={
            "names": ["region", "deploy_password"],
            "managed_secret_names": ["deploy_password"],
        },
        progress={
            "state_version": 1,
            "log_start_cursor": 0,
            "log_end_cursor": len(raw_log),
        },
    )

    first = _json(playbook_run_report_log(_request(owner, "/log/?after=0&limit_chars=1"), run.id))
    public_end = first["end_cursor"]
    reconstructed = first["text"]
    cursor = first["next_cursor"]
    while cursor < public_end:
        chunk = _json(
            playbook_run_report_log(
                _request(owner, f"/log/?after={cursor}&limit_chars=1"),
                run.id,
            )
        )
        reconstructed += chunk["text"]
        cursor = chunk["next_cursor"]

    assert secret not in reconstructed
    assert "[REDACTED" in reconstructed
    legacy_payload = _serialize_run(run)
    assert secret not in json.dumps(legacy_payload)
    assert legacy_payload["variable_manifest"] == {
        "names": ["region", "deploy_password"],
        "managed_secret_names": ["deploy_password"],
        "values_redacted": True,
    }
