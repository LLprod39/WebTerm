"""
Settings configuration API endpoints.
"""

import json
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from loguru import logger

from app.core.model_config import model_manager
from core_ui.activity import log_user_activity
from core_ui.context_processors import user_can_feature
from core_ui.models import UserActivityLog


def _load_delegate_ui_preference(user) -> str:
    delegate_ui = "chat"
    if "tasks" not in (getattr(settings, "INSTALLED_APPS", None) or []):
        return delegate_ui
    try:
        from tasks.models import UserDelegatePreference

        pref = UserDelegatePreference.objects.filter(user=user).first()
        if pref:
            delegate_ui = pref.delegate_ui
    except Exception as exc:
        logger.debug("Failed to load delegate preference: %s", exc)
    return delegate_ui


def _api_key_status(config) -> dict:
    return {
        "gemini_set": bool(os.getenv("GEMINI_API_KEY")),
        "grok_set": bool(os.getenv("GROK_API_KEY")),
        "openai_set": bool(os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_API_KEY")),
        "anthropic_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "claude_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "ollama_local_set": bool(
            getattr(config, "ollama_base_url", "") or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
        ),
        "ollama_cloud_set": bool(os.getenv("OLLAMA_API_KEY")),
        "ollama_set": bool(
            getattr(config, "ollama_base_url", "") or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
        )
        or bool(os.getenv("OLLAMA_API_KEY")),
        "cursor_set": bool(os.getenv("CURSOR_API_KEY")),
        "codex_set": bool(os.getenv("CODEX_API_KEY") or os.getenv("OPENAI_API_KEY")),
    }


def _settings_config_payload(config, delegate_ui: str) -> dict:
    return {
        "default_provider": config.default_provider,
        "internal_llm_provider": getattr(config, "internal_llm_provider", "grok") or "grok",
        "default_orchestrator_mode": getattr(config, "default_orchestrator_mode", "ralph_internal")
        or "ralph_internal",
        "ralph_max_iterations": getattr(config, "ralph_max_iterations", 20) or 20,
        "ralph_completion_promise": getattr(config, "ralph_completion_promise", "COMPLETE") or "COMPLETE",
        "gemini_enabled": getattr(config, "gemini_enabled", False),
        "grok_enabled": getattr(config, "grok_enabled", True),
        "openai_enabled": getattr(config, "openai_enabled", False),
        "claude_enabled": getattr(config, "claude_enabled", False),
        "ollama_enabled": getattr(config, "ollama_enabled", False),
        "chat_model_gemini": config.chat_model_gemini,
        "chat_model_grok": config.chat_model_grok,
        "chat_model_openai": getattr(config, "chat_model_openai", "gpt-5-mini"),
        "chat_model_claude": getattr(config, "chat_model_claude", "claude-sonnet-4-6"),
        "chat_model_ollama": getattr(config, "chat_model_ollama", "") or "",
        "rag_model": config.rag_model,
        "agent_model_gemini": config.agent_model_gemini,
        "agent_model_grok": config.agent_model_grok,
        "agent_model_openai": getattr(config, "agent_model_openai", "gpt-5-mini"),
        "agent_model_ollama": getattr(config, "agent_model_ollama", "") or "",
        "ollama_base_url": getattr(config, "ollama_base_url", "http://127.0.0.1:11434")
        or "http://127.0.0.1:11434",
        "ollama_runtime_mode": getattr(config, "ollama_runtime_mode", "auto") or "auto",
        "ollama_cloud_enabled": getattr(config, "ollama_cloud_enabled", False),
        "ollama_cloud_base_url": getattr(config, "ollama_cloud_base_url", "https://ollama.com") or "https://ollama.com",
        "ollama_think_mode": getattr(config, "ollama_think_mode", "") or "",
        "default_agent_output_path": getattr(config, "default_agent_output_path", "") or "",
        "cursor_chat_mode": getattr(config, "cursor_chat_mode", "ask") or "ask",
        "cursor_sandbox": getattr(config, "cursor_sandbox", "") or "",
        "cursor_approve_mcps": getattr(config, "cursor_approve_mcps", False),
        "allow_model_selection": getattr(config, "allow_model_selection", False),
        "delegate_ui": delegate_ui,
        "domain_auth_enabled": (
            getattr(config, "domain_auth_enabled", None)
            if getattr(config, "domain_auth_enabled", None) is not None
            else bool(getattr(settings, "DOMAIN_AUTH_ENABLED", False))
        ),
        "domain_auth_header": (
            getattr(config, "domain_auth_header", None)
            if getattr(config, "domain_auth_header", None)
            else str(getattr(settings, "DOMAIN_AUTH_HEADER", "REMOTE_USER") or "REMOTE_USER")
        ),
        "domain_auth_auto_create": (
            getattr(config, "domain_auth_auto_create", None)
            if getattr(config, "domain_auth_auto_create", None) is not None
            else bool(getattr(settings, "DOMAIN_AUTH_AUTO_CREATE", True))
        ),
        "domain_auth_lowercase_usernames": (
            getattr(config, "domain_auth_lowercase_usernames", None)
            if getattr(config, "domain_auth_lowercase_usernames", None) is not None
            else bool(getattr(settings, "DOMAIN_AUTH_LOWERCASE_USERNAMES", True))
        ),
        "domain_auth_default_profile": (
            getattr(config, "domain_auth_default_profile", None)
            if getattr(config, "domain_auth_default_profile", None)
            else str(getattr(settings, "DOMAIN_AUTH_DEFAULT_PROFILE", "server_only") or "server_only")
        ),
        "openai_reasoning_effort": getattr(config, "openai_reasoning_effort", "low") or "low",
        "chat_llm_provider": getattr(config, "chat_llm_provider", "") or "",
        "chat_llm_model": getattr(config, "chat_llm_model", "") or "",
        "agent_llm_provider": getattr(config, "agent_llm_provider", "") or "",
        "agent_llm_model": getattr(config, "agent_llm_model", "") or "",
        "orchestrator_llm_provider": getattr(config, "orchestrator_llm_provider", "") or "",
        "orchestrator_llm_model": getattr(config, "orchestrator_llm_model", "") or "",
        "log_terminal_commands": getattr(config, "log_terminal_commands", True),
        "log_ai_assistant": getattr(config, "log_ai_assistant", True),
        "log_agent_runs": getattr(config, "log_agent_runs", True),
        "log_pipeline_runs": getattr(config, "log_pipeline_runs", True),
        "log_auth_events": getattr(config, "log_auth_events", True),
        "log_server_changes": getattr(config, "log_server_changes", True),
        "log_settings_changes": getattr(config, "log_settings_changes", True),
        "log_file_operations": getattr(config, "log_file_operations", False),
        "log_mcp_calls": getattr(config, "log_mcp_calls", True),
        "log_http_requests": getattr(config, "log_http_requests", True),
        "retention_days": getattr(config, "retention_days", 90) or 90,
        "export_format": getattr(config, "export_format", "json") or "json",
    }


def _allowed_settings_keys() -> set[str]:
    return {
        "default_provider",
        "chat_model_gemini",
        "chat_model_grok",
        "chat_model_openai",
        "rag_model",
        "agent_model_gemini",
        "agent_model_grok",
        "agent_model_openai",
        "default_agent_output_path",
        "cursor_chat_mode",
        "cursor_sandbox",
        "cursor_approve_mcps",
        "internal_llm_provider",
        "allow_model_selection",
        "gemini_enabled",
        "grok_enabled",
        "openai_enabled",
        "claude_enabled",
        "ollama_enabled",
        "chat_model_claude",
        "chat_model_ollama",
        "default_orchestrator_mode",
        "ralph_max_iterations",
        "ralph_completion_promise",
        "ollama_base_url",
        "ollama_runtime_mode",
        "ollama_cloud_enabled",
        "ollama_cloud_base_url",
        "ollama_think_mode",
        "domain_auth_enabled",
        "domain_auth_header",
        "domain_auth_auto_create",
        "domain_auth_lowercase_usernames",
        "domain_auth_default_profile",
        "chat_llm_provider",
        "chat_llm_model",
        "agent_llm_provider",
        "agent_llm_model",
        "orchestrator_llm_provider",
        "orchestrator_llm_model",
        "agent_model_ollama",
        "openai_reasoning_effort",
        "log_terminal_commands",
        "log_ai_assistant",
        "log_agent_runs",
        "log_pipeline_runs",
        "log_auth_events",
        "log_server_changes",
        "log_settings_changes",
        "log_file_operations",
        "log_mcp_calls",
        "log_http_requests",
        "retention_days",
        "export_format",
    }


def _audit_logging_keys() -> set[str]:
    return {
        "log_terminal_commands",
        "log_ai_assistant",
        "log_agent_runs",
        "log_pipeline_runs",
        "log_auth_events",
        "log_server_changes",
        "log_settings_changes",
        "log_file_operations",
        "log_mcp_calls",
        "log_http_requests",
        "retention_days",
        "export_format",
    }


def _normalize_settings_update(data: dict) -> JsonResponse | None:
    if "domain_auth_header" in data and data["domain_auth_header"] is not None:
        data["domain_auth_header"] = str(data["domain_auth_header"]).strip() or "REMOTE_USER"
    if "domain_auth_default_profile" in data and data["domain_auth_default_profile"] is not None:
        profile = str(data["domain_auth_default_profile"]).strip().lower()
        if profile not in {"server_only", "admin_full", "reset_defaults", "custom"}:
            return JsonResponse({"success": False, "error": "Invalid domain_auth_default_profile"}, status=400)
        data["domain_auth_default_profile"] = profile
    if "retention_days" in data and data["retention_days"] is not None:
        try:
            data["retention_days"] = max(1, min(int(data["retention_days"]), 3650))
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "error": "Invalid retention_days"}, status=400)
    if "export_format" in data and data["export_format"] is not None:
        export_format = str(data["export_format"]).strip().lower()
        if export_format not in {"json", "csv", "syslog"}:
            return JsonResponse({"success": False, "error": "Invalid export_format"}, status=400)
        data["export_format"] = export_format
    if "ollama_base_url" in data and data["ollama_base_url"] is not None:
        data["ollama_base_url"] = str(data["ollama_base_url"]).strip().rstrip("/") or "http://127.0.0.1:11434"
    if "ollama_cloud_base_url" in data and data["ollama_cloud_base_url"] is not None:
        data["ollama_cloud_base_url"] = str(data["ollama_cloud_base_url"]).strip().rstrip("/") or "https://ollama.com"
    if "ollama_runtime_mode" in data and data["ollama_runtime_mode"] is not None:
        runtime_mode = str(data["ollama_runtime_mode"]).strip().lower()
        if runtime_mode not in {"auto", "local", "cloud"}:
            return JsonResponse({"success": False, "error": "Invalid ollama_runtime_mode"}, status=400)
        data["ollama_runtime_mode"] = runtime_mode
    if "ollama_think_mode" in data and data["ollama_think_mode"] is not None:
        think_mode = str(data["ollama_think_mode"]).strip().lower()
        if think_mode not in {"", "off", "on", "low", "medium", "high"}:
            return JsonResponse({"success": False, "error": "Invalid ollama_think_mode"}, status=400)
        data["ollama_think_mode"] = think_mode
    return None


def _enable_selected_providers(data: dict) -> None:
    for provider_key in (
        "chat_llm_provider",
        "agent_llm_provider",
        "orchestrator_llm_provider",
        "internal_llm_provider",
    ):
        provider = data.get(provider_key)
        if provider in ("gemini", "grok", "openai", "claude", "ollama"):
            data[f"{provider}_enabled"] = True


def _save_delegate_ui_preference(user, delegate_ui: str) -> None:
    from tasks.models import UserDelegatePreference

    UserDelegatePreference.objects.update_or_create(
        user=user,
        defaults={"delegate_ui": delegate_ui},
    )


@login_required
@require_http_methods(["GET", "POST"])
def api_settings(request):
    """GET full settings config or POST settings updates."""
    if not user_can_feature(request.user, "settings"):
        return JsonResponse({"error": "Forbidden"}, status=403)
    if request.method == "GET":
        try:
            model_manager.load_config()
            config = model_manager.config
            from app.core.provider_registry import get_provider_registry

            registry = get_provider_registry()
            return JsonResponse(
                {
                    "success": True,
                    "config": _settings_config_payload(config, _load_delegate_ui_preference(request.user)),
                    "api_keys": _api_key_status(config),
                    "providers": registry.get_all_providers(),
                }
            )
        except Exception as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=500)

    try:
        data = json.loads(request.body)
        audit_keys = _audit_logging_keys()
        requested_audit_keys = sorted(key for key in data if key in audit_keys)
        if requested_audit_keys and not request.user.is_staff:
            return JsonResponse(
                {"success": False, "error": "Only admins can update audit logging settings"},
                status=403,
            )
        validation_error = _normalize_settings_update(data)
        if validation_error is not None:
            return validation_error
        _enable_selected_providers(data)

        allowed = _allowed_settings_keys()
        for key, value in data.items():
            if key in allowed and value is not None:
                model_manager.update_config(**{key: value})
        model_manager.save_config()

        if "delegate_ui" in data and data["delegate_ui"] in ("chat", "task_form"):
            _save_delegate_ui_preference(request.user, data["delegate_ui"])

        changed_keys = sorted([key for key, value in data.items() if key in allowed and value is not None])
        if "delegate_ui" in data and data.get("delegate_ui") in ("chat", "task_form"):
            changed_keys.append("delegate_ui")
        log_user_activity(
            user=request.user,
            request=request,
            category="settings",
            action="settings_update",
            status=UserActivityLog.STATUS_SUCCESS,
            description="Updated settings",
            entity_type="settings",
            metadata={"changed_keys": changed_keys},
        )
        return JsonResponse({"success": True, "message": "Settings updated"})
    except Exception as exc:
        log_user_activity(
            user=request.user,
            request=request,
            category="settings",
            action="settings_update",
            status=UserActivityLog.STATUS_ERROR,
            description=f"Settings update failed: {exc}",
            entity_type="settings",
        )
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_GET
def api_settings_check(request):
    """Return whether required API keys are configured."""
    if not user_can_feature(request.user, "settings"):
        return JsonResponse({"configured": False, "missing": ["gemini_key", "grok_key"]}, status=403)
    try:
        gemini_ok = bool((os.getenv("GEMINI_API_KEY") or "").strip())
        grok_ok = bool((os.getenv("GROK_API_KEY") or "").strip())
        missing = []
        if not gemini_ok:
            missing.append("gemini_key")
        if not grok_ok:
            missing.append("grok_key")
        return JsonResponse(
            {
                "configured": len(missing) == 0,
                "missing": missing,
            }
        )
    except Exception as exc:
        logger.exception("api_settings_check error: %s", exc)
        return JsonResponse({"configured": False, "missing": ["gemini_key", "grok_key"]}, status=500)
