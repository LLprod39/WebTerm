"""Versioned PlaybookRun report, delta log, retry context, and export views."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from app.core.redacted_logging import redacted_log_text
from core_ui.decorators import require_feature
from servers.models import PlaybookRun
from servers.services.playbook_run_report import (
    TERMINAL_STATUSES,
    build_playbook_run_report,
    build_retry_context,
    compact_run_report_item,
    markdown_report,
    progress_snapshot,
    public_host_detail,
    report_etag,
)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DEFAULT_LOG_CHARS = 32_000
MAX_LOG_CHARS = 120_000


def _owned_run(user, run_id: int) -> PlaybookRun:
    return get_object_or_404(
        PlaybookRun.objects.select_related("playbook", "dispatch", "binding_profile"),
        id=run_id,
        user=user,
    )


def _integer_query(
    request, name: str, *, default: int, minimum: int, maximum: int
) -> tuple[int | None, JsonResponse | None]:
    raw = request.GET.get(name)
    if raw in (None, ""):
        return default, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, JsonResponse(
            {"success": False, "code": "invalid_query", "error": f"{name} must be an integer"}, status=400
        )
    if value < minimum or value > maximum:
        return None, JsonResponse(
            {"success": False, "code": "invalid_query", "error": f"{name} must be between {minimum} and {maximum}"},
            status=400,
        )
    return value, None


def _etag_response(request, payload: dict, *, key: str = "report") -> HttpResponse:
    etag = report_etag(payload)
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
    else:
        response = JsonResponse({"success": True, key: payload})
    response["ETag"] = etag
    response["Cache-Control"] = "private, no-cache"
    return response


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_run_report(request, run_id: int):
    return _etag_response(request, build_playbook_run_report(_owned_run(request.user, run_id)))


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_run_report_host(request, run_id: int, server_id: int):
    run = _owned_run(request.user, run_id)
    host = next(
        (
            item
            for item in (run.host_results if isinstance(run.host_results, list) else [])
            if isinstance(item, dict) and str(item.get("server_id")) == str(server_id)
        ),
        None,
    )
    if host is None:
        return JsonResponse(
            {"success": False, "code": "host_result_not_found", "error": "Host result not found"}, status=404
        )
    return _etag_response(request, public_host_detail(run, host), key="host")


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_run_report_log(request, run_id: int):
    run = _owned_run(request.user, run_id)
    limit, error = _integer_query(
        request,
        "limit_chars",
        default=DEFAULT_LOG_CHARS,
        minimum=1,
        maximum=MAX_LOG_CHARS,
    )
    if error:
        return error
    progress = progress_snapshot(run, dispatch=None)
    # Redact the complete retained tail before applying a cursor.  Redacting a
    # one-character slice would let a client reconstruct legacy secrets by
    # repeatedly requesting tiny chunks.
    text = redacted_log_text(run.live_log or "")
    stored_start = int(progress["log_start_cursor"])
    effective_start = stored_start
    stored_end = effective_start + len(text)
    after, error = _integer_query(
        request,
        "after",
        default=effective_start,
        minimum=0,
        maximum=9_223_372_036_854_775_807,
    )
    if error:
        return error
    assert after is not None and limit is not None
    reset_required = after < effective_start or after > stored_end
    cursor = effective_start if reset_required else after
    local_offset = min(max(cursor - effective_start, 0), len(text))
    chunk = text[local_offset : local_offset + limit]
    next_cursor = cursor + len(chunk)
    return JsonResponse(
        {
            "success": True,
            "text": chunk,
            "cursor": cursor,
            "next_cursor": next_cursor,
            "start_cursor": effective_start,
            "end_cursor": stored_end,
            "has_more": next_cursor < stored_end,
            "truncated": bool(progress["log_truncated"] or effective_start > 0),
            "reset_required": reset_required,
            "state_version": progress["state_version"],
        }
    )


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_run_retry_context(request, run_id: int):
    return _etag_response(request, build_retry_context(_owned_run(request.user, run_id)), key="retry_context")


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_run_report_list(request):
    limit, error = _integer_query(
        request,
        "limit",
        default=DEFAULT_PAGE_SIZE,
        minimum=1,
        maximum=MAX_PAGE_SIZE,
    )
    if error:
        return error
    cursor, error = _integer_query(request, "cursor", default=0, minimum=0, maximum=9_223_372_036_854_775_807)
    if error:
        return error
    statuses = [item.strip() for item in str(request.GET.get("status") or "").split(",") if item.strip()]
    valid_statuses = {value for value, _label in PlaybookRun.STATUS_CHOICES}
    if any(item not in valid_statuses for item in statuses):
        return JsonResponse({"success": False, "code": "invalid_status", "error": "Unknown run status"}, status=400)
    queryset = PlaybookRun.objects.filter(user=request.user).select_related("playbook", "dispatch").order_by("-id")
    if cursor:
        queryset = queryset.filter(id__lt=cursor)
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    playbook_id = str(request.GET.get("playbook_id") or "").strip()
    if playbook_id:
        if not playbook_id.isdigit():
            return JsonResponse(
                {"success": False, "code": "invalid_query", "error": "playbook_id must be an integer"}, status=400
            )
        queryset = queryset.filter(playbook_id=int(playbook_id))
    query = str(request.GET.get("q") or "").strip()[:200]
    if query:
        queryset = queryset.filter(
            Q(playbook__name__icontains=query) | Q(playbook_snapshot__name__icontains=query)
        )
    assert limit is not None
    rows = list(queryset[: limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = rows[-1].id if has_more and rows else None
    return JsonResponse(
        {
            "success": True,
            "items": [compact_run_report_item(run) for run in rows],
            "page": {"limit": limit, "next_cursor": next_cursor, "has_more": has_more},
            "filters": {"status": statuses, "playbook_id": int(playbook_id) if playbook_id else None, "q": query},
        }
    )


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_run_report_export(request, run_id: int):
    run = _owned_run(request.user, run_id)
    if run.status not in TERMINAL_STATUSES:
        return JsonResponse(
            {
                "success": False,
                "code": "run_not_terminal",
                "error": "A report export is available after the run finishes",
            },
            status=409,
        )
    report = build_playbook_run_report(run)
    report_json = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    report_markdown = markdown_report(report)
    execution_log = redacted_log_text(run.live_log or "")
    files = {
        "report.json": report_json,
        "report.md": report_markdown,
        "execution.log": execution_log,
    }
    for index, host in enumerate(run.host_results if isinstance(run.host_results, list) else [], start=1):
        if not isinstance(host, dict):
            continue
        server_id = host.get("server_id")
        suffix = str(server_id) if str(server_id or "").isdigit() else str(index)
        files[f"hosts/{suffix}.json"] = (
            json.dumps(public_host_detail(run, host), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    checksum_lines = [
        f"{hashlib.sha256(content.encode('utf-8')).hexdigest()}  {name}"
        for name, content in sorted(files.items())
    ]
    files["checksums.sha256"] = "\n".join(checksum_lines) + "\n"
    manifest = {
        "schema_version": 1,
        "report_schema_version": report["schema_version"],
        "run_id": run.id,
        "status": run.status,
        "generated_at": report["run"]["finished_at"] or report["run"]["created_at"],
        "log_truncated": bool(report["log"]["truncated"]),
        "log_file": "execution.log",
        "log_scope": "available_redacted_tail",
        "files": {
            name: {
                "size_bytes": len(content.encode("utf-8")),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
            for name, content in files.items()
        },
    }
    buffer = io.BytesIO()

    def _write_text(archive: zipfile.ZipFile, name: str, content: str) -> None:
        entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o600 << 16
        archive.writestr(entry, content)

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            _write_text(archive, name, content)
        _write_text(archive, "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    body = buffer.getvalue()
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
    else:
        response = HttpResponse(body, content_type="application/zip")
        filename = quote(f"ansible-run-{run.id}-report.zip")
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Log-Truncated"] = "true" if manifest["log_truncated"] else "false"
    response["ETag"] = etag
    response["Cache-Control"] = "private, no-cache"
    return response
