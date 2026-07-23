from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

from app.core.model_catalog import (
    combine_ollama_models,
    extract_model_ids,
    extract_ollama_model_names,
    is_openai_text_model,
)
from app.core.redacted_logging import redacted_log_text


async def fetch_available_gemini_models(manager: Any) -> list[str]:
    key = (
        await manager._aget_managed_llm_api_key("gemini")
        or manager.gemini_api_key
        or (os.getenv("GEMINI_API_KEY") or "").strip()
    )
    if key:
        manager.gemini_api_key = key
    if not key:
        logger.warning("Gemini API key not set")
        return manager._get_default_gemini_models()

    try:
        models: list[str] = []
        page_token = ""

        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                params = {"key": key, "pageSize": 200}
                if page_token:
                    params["pageToken"] = page_token
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params=params,
                )
                if response.status_code != 200:
                    logger.error(
                        "Gemini API returned status {}: {}", response.status_code, redacted_log_text(response.text)
                    )
                    return manager._get_default_gemini_models()

                payload = response.json()
                for model in payload.get("models", []) or []:
                    name = model.get("name")
                    supported = model.get("supportedGenerationMethods") or []
                    if isinstance(name, str) and name and "generateContent" in supported:
                        models.append(name)

                page_token = (payload.get("nextPageToken") or "").strip()
                if not page_token:
                    break

        models = sorted(set(models))
        if not models:
            logger.warning("Gemini API returned empty models list; using defaults")
            return manager._get_default_gemini_models()

        manager.available_gemini_models = models
        logger.success(f"Fetched {len(models)} Gemini models")
        return models

    except Exception as exc:
        logger.error(f"Failed to fetch Gemini models: {exc}")
        return manager._get_default_gemini_models()


async def fetch_available_grok_models(manager: Any) -> list[str]:
    key = (
        await manager._aget_managed_llm_api_key("grok")
        or manager.grok_api_key
        or (os.getenv("GROK_API_KEY") or "").strip()
        or (os.getenv("XAI_API_KEY") or "").strip()
    )
    if key:
        manager.grok_api_key = key
    if not key:
        logger.warning("Grok API key not set")
        return manager._get_default_grok_models()

    try:
        async with httpx.AsyncClient() as client:
            for endpoint in ("https://api.x.ai/v1/language-models", "https://api.x.ai/v1/models"):
                response = await client.get(
                    endpoint,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10.0,
                )

                if response.status_code != 200:
                    logger.warning(
                        "Grok API returned status {} for {}: {}",
                        response.status_code,
                        endpoint,
                        redacted_log_text(response.text, limit=500),
                    )
                    continue

                data = response.json()
                models = sorted(set(extract_model_ids(data)))
                if not models:
                    continue

                manager.available_grok_models = models
                logger.success(f"Fetched {len(models)} Grok models from {endpoint}")
                return models

            logger.error("Grok API returned no model data from supported endpoints")
            return manager._get_default_grok_models()

    except Exception as exc:
        logger.error(f"Failed to fetch Grok models: {exc}")
        return manager._get_default_grok_models()


async def fetch_available_claude_models(manager: Any) -> list[str]:
    key = (
        await manager._aget_managed_llm_api_key("claude")
        or manager.anthropic_api_key
        or (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    )
    if key:
        manager.anthropic_api_key = key
    if not key:
        logger.warning("Anthropic API key not set")
        return manager._get_default_claude_models()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if response.status_code != 200:
                logger.error(
                    "Anthropic API returned status {}: {}", response.status_code, redacted_log_text(response.text)
                )
                return manager._get_default_claude_models()

            payload = response.json()
            models = sorted({item.get("id", "") for item in (payload.get("data") or []) if item.get("id")})

            if not models:
                logger.warning("Anthropic API returned empty model list; using defaults")
                return manager._get_default_claude_models()

            manager.available_claude_models = models
            logger.success(f"Fetched {len(models)} Claude models")
            return models
    except Exception as exc:
        logger.error(f"Failed to fetch Claude models: {exc}")
        return manager._get_default_claude_models()


async def fetch_available_openai_models(manager: Any) -> list[str]:
    key = (
        await manager._aget_managed_llm_api_key("openai")
        or manager.openai_api_key
        or (os.getenv("OPENAI_API_KEY") or "").strip()
        or (os.getenv("CODEX_API_KEY") or "").strip()
    )
    if key:
        manager.openai_api_key = key
    if not key:
        logger.warning("OpenAI API key not set")
        return manager._get_default_openai_models()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )

            if response.status_code != 200:
                logger.error(
                    "OpenAI API returned status {}: {}", response.status_code, redacted_log_text(response.text)
                )
                return manager._get_default_openai_models()

            payload = response.json()
            models = sorted({model_id for model_id in extract_model_ids(payload) if is_openai_text_model(model_id)})

            if not models:
                logger.warning("OpenAI API returned empty text model list; using defaults")
                return manager._get_default_openai_models()

            manager.available_openai_models = models
            logger.success(f"Fetched {len(models)} OpenAI models")
            return models
    except Exception as exc:
        logger.error(f"Failed to fetch OpenAI models: {exc}")
        return manager._get_default_openai_models()


async def fetch_available_ollama_models(manager: Any) -> list[str]:
    local_models: list[str] = []
    cloud_models: list[str] = []
    errors: list[str] = []

    for base_url in manager._get_ollama_base_urls():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/api/tags")

            if response.status_code != 200:
                errors.append(f"local {base_url} -> HTTP {response.status_code}")
                continue

            local_models = extract_ollama_model_names(response.json())
            manager.available_ollama_local_models = local_models
            if base_url != manager.config.ollama_base_url:
                logger.warning(
                    f"Ollama base URL fallback: configured={manager.config.ollama_base_url or 'unset'} -> using {base_url}"
                )
            manager.config.ollama_base_url = base_url
            logger.success(f"Fetched {len(local_models)} local Ollama models from {base_url}")
            break
        except Exception as exc:
            errors.append(f"local {base_url} -> {exc}")

    if not local_models:
        manager.available_ollama_local_models = []

    if manager.config.ollama_cloud_enabled:
        managed_ollama_key = await manager._aget_managed_llm_api_key("ollama")
        if managed_ollama_key:
            manager.ollama_api_key = managed_ollama_key
        api_key = manager._get_ollama_api_key()
        if not api_key:
            errors.append("cloud https://ollama.com -> OLLAMA_API_KEY is not configured")
        else:
            cloud_base_url = manager._get_ollama_cloud_base_url()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{cloud_base_url}/api/tags",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )

                if response.status_code != 200:
                    errors.append(f"cloud {cloud_base_url} -> HTTP {response.status_code}")
                else:
                    cloud_models = extract_ollama_model_names(response.json(), cloud=True)
                    manager.available_ollama_cloud_models = cloud_models
                    logger.success(f"Fetched {len(cloud_models)} Ollama cloud models from {cloud_base_url}")
            except Exception as exc:
                errors.append(f"cloud {cloud_base_url} -> {exc}")
    else:
        manager.available_ollama_cloud_models = []

    combined_models = combine_ollama_models(
        local_models,
        cloud_models,
        prefer_cloud=manager._get_ollama_runtime_mode() == "cloud",
    )
    manager.available_ollama_models = combined_models
    if combined_models:
        return combined_models

    logger.error(f"Failed to fetch Ollama models. Tried: {'; '.join(errors)}")
    return manager._get_default_ollama_models()
