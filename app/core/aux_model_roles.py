"""Auxiliary/utility model roles: intent, verifier, summarizer, safety hint.

Uses a dedicated short-timeout JSON completion against the configured aux
model (Ollama / OpenAI-compatible / existing API providers). On any failure
falls back to deterministic/heuristic behaviour so Operator turns never hang.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from asgiref.sync import sync_to_async
from loguru import logger

IntentKind = Literal["chitchat", "host_task", "metrics", "inventory", "unknown"]
VerifyDecision = Literal["continue", "finish"]
SafetyKind = Literal["read_only", "mutating", "unknown"]

DEFAULT_AUX_TIMEOUT_SEC = 8
MIN_AUX_TIMEOUT_SEC = 2
MAX_AUX_TIMEOUT_SEC = 30

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


@dataclass(frozen=True)
class IntentResult:
    kind: IntentKind
    needs_ssh: bool
    source: str  # aux | heuristic | fallback
    reason: str = ""


@dataclass(frozen=True)
class VerifyResult:
    decision: VerifyDecision
    reason: str
    source: str  # aux | fallback


@dataclass(frozen=True)
class SafetyHint:
    kind: SafetyKind
    source: str  # aux | fallback
    reason: str = ""


def _config():
    from app.core.model_config import model_manager

    model_manager.load_config()
    return model_manager.config


def aux_timeout_seconds(config=None) -> float:
    cfg = config or _config()
    raw = int(getattr(cfg, "aux_llm_timeout_seconds", DEFAULT_AUX_TIMEOUT_SEC) or DEFAULT_AUX_TIMEOUT_SEC)
    return float(max(MIN_AUX_TIMEOUT_SEC, min(MAX_AUX_TIMEOUT_SEC, raw)))


def aux_is_ready(config=None) -> bool:
    cfg = config or _config()
    if not bool(getattr(cfg, "aux_llm_enabled", False)):
        return False
    provider = str(getattr(cfg, "aux_llm_provider", "") or "").strip().lower()
    model = str(getattr(cfg, "aux_llm_model", "") or "").strip()
    if not provider or not model:
        return False
    if provider in {"ollama", "openai_compatible"}:
        base = str(getattr(cfg, "aux_llm_base_url", "") or "").strip()
        if provider == "openai_compatible" and not base:
            return False
        # ollama may inherit ollama_base_url
        if provider == "ollama" and not base and not str(getattr(cfg, "ollama_base_url", "") or "").strip():
            return False
    return True


def role_enabled(role: str, config=None) -> bool:
    cfg = config or _config()
    field = {
        "verifier": "aux_role_verifier_enabled",
        "intent": "aux_role_intent_enabled",
        "summarizer": "aux_role_summarizer_enabled",
        "safety": "aux_role_safety_enabled",
    }.get(role)
    if not field:
        return False
    return bool(getattr(cfg, field, False))


def _resolve_aux_endpoint(config) -> tuple[str, str, str, str]:
    """Return (provider, model, api_url, api_key)."""
    provider = str(getattr(config, "aux_llm_provider", "") or "").strip().lower()
    model = str(getattr(config, "aux_llm_model", "") or "").strip()
    base = str(getattr(config, "aux_llm_base_url", "") or "").strip().rstrip("/")

    from app.core.docker_host_routing import route_loopback_url
    from app.core.llm_secrets import get_managed_llm_api_key

    if provider == "ollama":
        if not base:
            base = str(getattr(config, "ollama_base_url", "") or "http://127.0.0.1:11434").rstrip("/")
        base = route_loopback_url(base, purpose="aux model")
        api_url = f"{base}/v1/chat/completions"
        api_key = (get_managed_llm_api_key("ollama") or "").strip()
        return provider, model, api_url, api_key

    if provider == "openai_compatible":
        if not base:
            raise ValueError("aux_llm_base_url required for openai_compatible")
        base = route_loopback_url(base, purpose="aux model")
        api_url = f"{base}/v1/chat/completions" if not base.endswith("/chat/completions") else base
        if not api_url.endswith("/chat/completions"):
            api_url = f"{base}/v1/chat/completions"
        api_key = (get_managed_llm_api_key("openai_compatible") or get_managed_llm_api_key("openai") or "").strip()
        return provider, model, api_url, api_key

    known = {
        "openai": ("https://api.openai.com/v1/chat/completions", "openai"),
        "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openrouter"),
        "grok": ("https://api.x.ai/v1/chat/completions", "grok"),
    }
    if provider in known:
        api_url, key_name = known[provider]
        return provider, model, api_url, (get_managed_llm_api_key(key_name) or "").strip()

    # claude/gemini — handled via stream_chat collect path
    return provider, model, "", (get_managed_llm_api_key(provider if provider != "claude" else "claude") or "").strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = _JSON_FENCE_RE.search(raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None


async def _complete_openai_compatible_json(
    *,
    api_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: float,
    disable_reasoning: bool = False,
) -> str:
    import aiohttp

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    if disable_reasoning:
        # Ollama thinking models (qwen3.x etc.) otherwise reason for 15-20s per call.
        payload["reasoning_effort"] = "none"
    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    async with (
        aiohttp.ClientSession(timeout=timeout_cfg) as session,
        session.post(api_url, headers=headers, json=payload) as resp,
    ):
        body = await resp.text()
        if resp.status >= 400:
            raise RuntimeError(f"aux HTTP {resp.status}: {body[:300]}")
        data = json.loads(body)
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("aux response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    return str(content or "")


async def _complete_via_stream_chat(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: float,
) -> str:
    from app.core.llm import get_provider

    llm = get_provider()
    chunks: list[str] = []

    async def _collect() -> str:
        async for chunk in llm.stream_chat(
            prompt=user_prompt,
            model=provider,
            specific_model=model,
            purpose="aux",
            system_prompt=system_prompt,
            json_mode=True,
            execution_context=None,
        ):
            if chunk:
                chunks.append(str(chunk))
        return "".join(chunks)

    return await asyncio.wait_for(_collect(), timeout=timeout)


async def _call_aux_json(
    *,
    role: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[dict[str, Any] | None, str]:
    """Returns (parsed_json_or_None, source_label)."""
    cfg = _config()
    if not aux_is_ready(cfg) or not role_enabled(role, cfg):
        return None, "fallback"
    timeout = aux_timeout_seconds(cfg)
    try:
        provider, model, api_url, api_key = await sync_to_async(_resolve_aux_endpoint, thread_sensitive=True)(cfg)
    except Exception as exc:  # noqa: BLE001
        logger.info("aux_role role={} source=fallback reason=resolve_error err={}", role, exc)
        return None, "fallback"

    try:
        if api_url:
            text = await asyncio.wait_for(
                _complete_openai_compatible_json(
                    api_url=api_url,
                    disable_reasoning=provider == "ollama",
                    api_key=api_key,
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    timeout=timeout,
                ),
                timeout=timeout + 0.5,
            )
        else:
            text = await _complete_via_stream_chat(
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout=timeout,
            )
        parsed = _parse_json_object(text)
        if parsed is None:
            logger.info(
                "aux_role role={} provider={} model={} source=fallback reason=json_parse",
                role,
                provider,
                model,
            )
            return None, "fallback"
        logger.info(
            "aux_role role={} provider={} model={} source=aux ok=1",
            role,
            provider,
            model,
        )
        return parsed, "aux"
    except TimeoutError:
        logger.info(
            "aux_role role={} provider={} model={} source=fallback reason=timeout timeout_s={}",
            role,
            provider,
            model,
            timeout,
        )
        return None, "fallback"
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "aux_role role={} provider={} model={} source=fallback reason=error err={}",
            role,
            provider,
            model,
            str(exc)[:200],
        )
        return None, "fallback"


def heuristic_intent(text: str) -> IntentResult:
    from core_ui.services.operator_loop_prompt import (
        messages_have_host_mention,
        user_message_needs_ssh_actions,
    )

    lowered = str(text or "").lower()
    if not lowered.strip():
        return IntentResult(kind="unknown", needs_ssh=False, source="heuristic")
    if any(w in lowered for w in ("привет", "здравствуй", "hello", "hi ", "что умеешь", "помощь")) and (
        not messages_have_host_mention(text) and not user_message_needs_ssh_actions(text)
    ):
        return IntentResult(kind="chitchat", needs_ssh=False, source="heuristic")
    if re.search(r"(?:метрик|metrics|forecast|прогноз)", lowered) and not re.search(
        r"(?:лог|ssh|крутится|journalctl|docker)", lowered
    ):
        return IntentResult(kind="metrics", needs_ssh=False, source="heuristic")
    if any(w in lowered for w in ("список сервер", "list servers", "inventory", "флот")) and (
        not user_message_needs_ssh_actions(text)
    ):
        return IntentResult(kind="inventory", needs_ssh=False, source="heuristic")
    needs = user_message_needs_ssh_actions(text) or messages_have_host_mention(text)
    if needs:
        return IntentResult(kind="host_task", needs_ssh=True, source="heuristic")
    return IntentResult(kind="unknown", needs_ssh=False, source="heuristic")


async def classify_intent(text: str) -> IntentResult:
    heuristic = heuristic_intent(text)
    data, source = await _call_aux_json(
        role="intent",
        system_prompt=(
            "Classify the operator chat message. Reply JSON only: "
            '{"kind":"chitchat|host_task|metrics|inventory|unknown","needs_ssh":bool,"reason":"short"}.'
        ),
        user_prompt=f"Message:\n{str(text or '')[:2000]}",
    )
    if not data:
        return heuristic
    kind_raw = str(data.get("kind") or "unknown").strip().lower()
    allowed_kinds = {"chitchat", "host_task", "metrics", "inventory", "unknown"}
    kind: IntentKind = kind_raw if kind_raw in allowed_kinds else "unknown"  # type: ignore[assignment]
    needs_ssh = bool(data.get("needs_ssh"))
    # Never drop a heuristic host-ops signal — aux may only add/affirm.
    if heuristic.needs_ssh:
        needs_ssh = True
        if kind == "unknown":
            kind = "host_task"
    return IntentResult(
        kind=kind,
        needs_ssh=needs_ssh,
        source=source,
        reason=str(data.get("reason") or "")[:300],
    )


async def verify_goal(
    *,
    goal: str,
    assistant_so_far: str,
    tools_executed: bool,
    has_task_evidence: bool,
    inventory_only: bool,
) -> VerifyResult:
    """Decide whether the turn should continue gathering evidence or finish."""
    data, source = await _call_aux_json(
        role="verifier",
        system_prompt=(
            "You verify whether an ops assistant finished the user goal. "
            'Reply JSON only: {"decision":"continue|finish","reason":"short"}. '
            "Use continue if host evidence (SSH/logs/processes) is still missing for a host task. "
            "Use finish for greetings, answered questions, or when enough evidence exists."
        ),
        user_prompt=(
            f"Goal: {str(goal or '')[:1500]}\n"
            f"tools_executed={tools_executed} has_task_evidence={has_task_evidence} "
            f"inventory_only={inventory_only}\n"
            f"Assistant so far:\n{str(assistant_so_far or '')[:2500]}"
        ),
    )
    if not data:
        # Fallback: continue when tools ran without evidence / inventory-only.
        if tools_executed and not has_task_evidence and inventory_only:
            return VerifyResult(decision="continue", reason="fallback_inventory_only", source="fallback")
        if tools_executed and not has_task_evidence:
            return VerifyResult(decision="continue", reason="fallback_no_evidence", source="fallback")
        return VerifyResult(decision="finish", reason="fallback_default_finish", source="fallback")

    decision_raw = str(data.get("decision") or "").strip().lower()
    decision: VerifyDecision = "continue" if decision_raw == "continue" else "finish"
    return VerifyResult(
        decision=decision,
        reason=str(data.get("reason") or "")[:300],
        source=source,
    )


async def summarize(text: str, *, max_chars: int = 1200) -> str:
    blob = str(text or "")
    if len(blob) <= max_chars:
        return blob
    data, source = await _call_aux_json(
        role="summarizer",
        system_prompt=(
            "Compress the conversation/tool transcript for context. "
            f'Reply JSON only: {{"summary":"..."}} under {max_chars} characters. Keep facts, hosts, errors.'
        ),
        user_prompt=blob[:12000],
    )
    if data and isinstance(data.get("summary"), str) and data["summary"].strip():
        return str(data["summary"]).strip()[:max_chars]
    logger.info("aux_role role=summarizer source={} truncate_fallback", source)
    return blob[:max_chars]


async def classify_command_safety(command: str) -> SafetyHint:
    """HINT ONLY — never bypass Confirm / deterministic read-only rules."""
    data, source = await _call_aux_json(
        role="safety",
        system_prompt=(
            "Classify a shell command as read_only or mutating. "
            'Reply JSON only: {"kind":"read_only|mutating|unknown","reason":"short"}.'
        ),
        user_prompt=str(command or "")[:2000],
    )
    if not data:
        return SafetyHint(kind="unknown", source="fallback")
    kind_raw = str(data.get("kind") or "unknown").strip().lower()
    kind: SafetyKind = kind_raw if kind_raw in {"read_only", "mutating", "unknown"} else "unknown"  # type: ignore[assignment]
    return SafetyHint(kind=kind, source=source, reason=str(data.get("reason") or "")[:300])


async def test_aux_connection() -> dict[str, Any]:
    """Ping the configured aux model with a tiny JSON completion."""
    cfg = _config()
    if not bool(getattr(cfg, "aux_llm_enabled", False)):
        return {"ok": False, "error": "aux_llm_disabled"}
    if not aux_is_ready(cfg):
        return {"ok": False, "error": "aux_llm_not_configured"}
    timeout = aux_timeout_seconds(cfg)
    provider, model, api_url, api_key = await sync_to_async(_resolve_aux_endpoint, thread_sensitive=True)(cfg)
    try:
        if api_url:
            text = await asyncio.wait_for(
                _complete_openai_compatible_json(
                    api_url=api_url,
                    disable_reasoning=provider == "ollama",
                    api_key=api_key,
                    model=model,
                    system_prompt='Reply JSON only: {"ok":true}',
                    user_prompt="ping",
                    timeout=timeout,
                ),
                timeout=timeout + 0.5,
            )
        else:
            text = await _complete_via_stream_chat(
                provider=provider,
                model=model,
                system_prompt='Reply JSON only: {"ok":true}',
                user_prompt="ping",
                timeout=timeout,
            )
        parsed = _parse_json_object(text) or {}
        ok = bool(parsed.get("ok")) or '"ok"' in (text or "").lower()
        return {
            "ok": ok,
            "provider": provider,
            "model": model,
            "preview": (text or "")[:200],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "error": str(exc)[:400],
        }
