"""
Tool and model discovery endpoints.
"""

import asyncio
import json
import os

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from app.core.model_config import model_manager
from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from core_ui.managed_secrets import has_llm_api_key
from core_ui.views.runtime import get_unified_orchestrator


def _has_llm_api_key(provider: str, *env_names: str) -> bool:
    if any((os.getenv(env_name) or "").strip() for env_name in env_names):
        return True
    try:
        return has_llm_api_key(provider)
    except Exception as exc:
        logger.debug("Failed to read managed LLM API key status for %s: %s", provider, exc)
        return False


@login_required
@require_feature("orchestrator")
def api_tools_list(request):
    """Get list of available tools via UnifiedOrchestrator."""
    try:
        orchestrator = async_to_sync(get_unified_orchestrator)()
        tools = orchestrator.get_available_tools()
        return JsonResponse({"tools": tools, "count": len(tools)})
    except Exception as exc:
        logger.error(f"Error loading tools: {exc}")
        return internal_error_response(request, exc)


@login_required
def api_models_list(request):
    """Get list of available models for dropdowns."""
    try:
        gemini_models = model_manager.get_available_models("gemini")
        grok_models = model_manager.get_available_models("grok")
        openai_models = model_manager.get_available_models("openai")
        claude_models = model_manager.get_available_models("claude")
        ollama_models = model_manager.get_available_models("ollama")
        ollama_local_models = getattr(model_manager, "available_ollama_local_models", []) or []
        ollama_cloud_models = getattr(model_manager, "available_ollama_cloud_models", []) or []
        config = model_manager.config
        return JsonResponse(
            {
                "gemini": gemini_models,
                "grok": grok_models,
                "openai": openai_models,
                "claude": claude_models,
                "ollama": ollama_models,
                "ollama_local": ollama_local_models,
                "ollama_cloud": ollama_cloud_models,
                "rag_defaults": [
                    "models/text-embedding-004",
                    "models/text-embedding-005",
                    "models/embedding-001",
                ],
                "current": {
                    "chat_gemini": config.chat_model_gemini,
                    "chat_grok": config.chat_model_grok,
                    "chat_openai": getattr(config, "chat_model_openai", "gpt-5-mini"),
                    "chat_claude": getattr(config, "chat_model_claude", "claude-sonnet-4-6"),
                    "chat_ollama": getattr(config, "chat_model_ollama", "") or "",
                    "rag_model": config.rag_model,
                    "agent_model_gemini": config.agent_model_gemini,
                    "agent_model_grok": config.agent_model_grok,
                    "agent_model_openai": getattr(config, "agent_model_openai", "gpt-5-mini"),
                    "agent_model_ollama": getattr(config, "agent_model_ollama", "") or "",
                    "default_provider": config.default_provider,
                    "ollama_runtime_mode": getattr(config, "ollama_runtime_mode", "auto") or "auto",
                    "ollama_think_mode": getattr(config, "ollama_think_mode", "") or "",
                },
            }
        )
    except Exception as exc:
        return internal_error_response(request, exc)


@login_required
@require_feature("settings")
@require_http_methods(["POST"])
def api_models_refresh(request):
    """
    Fetch models from a provider API and return the refreshed list.

    Body: { "provider": "gemini|grok|openai|claude|ollama" }
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Only admins can refresh provider models"}, status=403)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    provider = (data.get("provider") or "").strip().lower()
    if provider not in {"gemini", "grok", "openai", "claude", "ollama"}:
        return JsonResponse({"error": "provider must be one of: gemini, grok, openai, claude, ollama"}, status=400)

    if provider == "gemini" and not _has_llm_api_key("gemini", "GEMINI_API_KEY"):
        return JsonResponse({"error": "GEMINI_API_KEY is not configured"}, status=400)
    if provider == "grok" and not _has_llm_api_key("grok", "GROK_API_KEY", "XAI_API_KEY"):
        return JsonResponse({"error": "GROK_API_KEY or XAI_API_KEY is not configured"}, status=400)
    if provider == "openai" and not _has_llm_api_key("openai", "OPENAI_API_KEY", "CODEX_API_KEY"):
        return JsonResponse({"error": "OPENAI_API_KEY or CODEX_API_KEY is not configured"}, status=400)
    if provider == "claude" and not _has_llm_api_key("claude", "ANTHROPIC_API_KEY"):
        return JsonResponse({"error": "ANTHROPIC_API_KEY is not configured"}, status=400)

    try:
        if provider == "gemini":
            models = asyncio.run(model_manager.fetch_available_gemini_models())
        elif provider == "grok":
            models = asyncio.run(model_manager.fetch_available_grok_models())
        elif provider == "claude":
            models = asyncio.run(model_manager.fetch_available_claude_models())
        elif provider == "ollama":
            models = asyncio.run(model_manager.fetch_available_ollama_models())
        else:
            models = asyncio.run(model_manager.fetch_available_openai_models())

        return JsonResponse(
            {
                "success": True,
                "provider": provider,
                "models": models,
                "count": len(models),
            }
        )
    except Exception as exc:
        logger.exception("api_models_refresh error: %s", exc)
        return internal_error_response(request, exc)
