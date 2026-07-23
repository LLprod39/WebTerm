"""
Studio pipeline run endpoints.
"""

import hmac
import json
import re
import sys

import httpx
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from studio.models import PipelineRun
from studio.pipeline_runtime import get_executor_for_run, update_runtime_control
from studio.views.notification_views import _load_notif_config

STUDIO_FEATURE_RUNS = "studio_runs"


def _json_body(request) -> dict:
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _ok(data, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _run_queryset_for_user(user):
    qs = PipelineRun.objects.select_related("pipeline", "pipeline__owner", "triggered_by")
    if _is_admin(user):
        return qs.order_by("-created_at")
    return qs.filter(pipeline__owner=user).order_by("-created_at")


def _normalize_node_lookup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _resolve_run_node_id(node_states: dict, requested_node_id: str) -> str | None:
    if requested_node_id in node_states:
        return requested_node_id

    normalized_requested = _normalize_node_lookup_key(requested_node_id)
    if not normalized_requested:
        return None

    matches = [
        str(node_id) for node_id in node_states if _normalize_node_lookup_key(str(node_id)) == normalized_requested
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _lookup_run_node_snapshot(run: PipelineRun, node_id: str) -> dict | None:
    for node in run.nodes_snapshot or []:
        if str(node.get("id") or "") == node_id:
            return node
    return None


def _package_attr(name: str, fallback):
    package = sys.modules.get("studio.views")
    return getattr(package, name, fallback)


def _send_approval_telegram_confirmation(run: PipelineRun, node_id: str, decision: str) -> None:
    node = _lookup_run_node_snapshot(run, node_id) or {}
    node_data = node.get("data") or {}
    notif_cfg = _load_notif_config()
    bot_token = str(node_data.get("tg_bot_token") or notif_cfg.get("telegram_bot_token") or "").strip()
    chat_id = str(node_data.get("tg_chat_id") or notif_cfg.get("telegram_chat_id") or "").strip()
    if not bot_token or not chat_id:
        return

    label = str(node_data.get("label") or node_id)
    emoji = "✅" if decision == "approved" else "❌"
    verdict_text = "одобрено" if decision == "approved" else "отклонено"
    message = (
        f"{emoji} *Решение записано*\n\n"
        f"*Пайплайн:* {run.pipeline.name}\n"
        f"*Запуск:* #{run.pk}\n"
        f"*Узел:* {label}\n"
        f"*Решение:* {verdict_text}"
    )
    http_client = _package_attr("httpx", httpx)
    try:
        http_client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
    except Exception:
        return


@require_feature(STUDIO_FEATURE_RUNS)
def api_runs(request):
    qs = _run_queryset_for_user(request.user)[:100]
    return _ok([run.to_dict() for run in qs])


@require_feature(STUDIO_FEATURE_RUNS)
def api_run_detail(request, run_id: int):
    run = _run_queryset_for_user(request.user).filter(pk=run_id).first()
    if run is None:
        return _err("Run not found", 404)
    return _ok(run.to_dict())


@require_feature(STUDIO_FEATURE_RUNS)
@require_http_methods(["POST"])
def api_run_stop(request, run_id: int):
    run = _run_queryset_for_user(request.user).filter(pk=run_id).first()
    if run is None:
        return _err("Run not found", 404)

    executor_getter = _package_attr("get_executor_for_run", get_executor_for_run)
    control_updater = _package_attr("update_runtime_control", update_runtime_control)
    executor = executor_getter(run.id)
    control, stop_delivered = control_updater(run, live_executor=executor, stop_requested=True)

    if run.status in {PipelineRun.STATUS_PENDING, PipelineRun.STATUS_RUNNING}:
        run.status = PipelineRun.STATUS_STOPPED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
    return _ok({"ok": True, "live_executor": stop_delivered, "runtime_control": control})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_run_approve(request, run_id: int, node_id: str):
    """
    Public endpoint authenticated only by the one-time token embedded in the URL.
    """
    if request.method == "GET":
        token = request.GET.get("token", "")
        decision = request.GET.get("decision", "")
        response_text = request.GET.get("response", "")
    else:
        body = _json_body(request)
        token = body.get("token", "")
        decision = body.get("decision", "")
        response_text = body.get("response_text", "")

    if not token:
        return _err("token is required", 400)
    if decision not in ("approved", "rejected"):
        return _err("decision must be 'approved' or 'rejected'", 400)

    try:
        run = PipelineRun.objects.get(pk=run_id)
    except PipelineRun.DoesNotExist:
        return _err("Run not found", 404)

    resolved_node_id = _resolve_run_node_id(run.node_states, node_id)
    if not resolved_node_id:
        return _err(f"Node '{node_id}' not found in run #{run_id}", 404)

    node_state = run.node_states.get(resolved_node_id)
    if not node_state:
        return _err(f"Node '{node_id}' not found in run #{run_id}", 404)

    stored_token = node_state.get("approval_token", "")
    if not stored_token or not hmac.compare_digest(str(stored_token), str(token)):
        return _err("Invalid or expired token", 403)

    if node_state.get("approval_decision"):
        existing = node_state["approval_decision"]
        return _ok({"ok": True, "message": f"Already decided: {existing}"})

    run.node_states[resolved_node_id] = {
        **node_state,
        "approval_decision": decision,
        "approval_response": response_text,
        "decided_at": timezone.now().isoformat(),
    }
    PipelineRun.objects.filter(pk=run_id).update(node_states=run.node_states)
    _send_approval_telegram_confirmation(run, resolved_node_id, decision)

    emoji = "✅" if decision == "approved" else "❌"
    safe_pipeline_name = escape(run.pipeline.name)
    safe_decision = escape(decision.capitalize())
    html = (
        "<html><body style='font-family:sans-serif;max-width:600px;margin:60px auto;text-align:center'>"
        f"<h1>{emoji} {safe_decision}</h1>"
        f"<p>Your decision for pipeline <strong>{safe_pipeline_name}</strong> (run #{int(run_id)}) "
        "has been recorded.</p>"
        "<p style='color:#888'>You can close this tab.</p>"
        "</body></html>"
    )

    return HttpResponse(html, content_type="text/html")
