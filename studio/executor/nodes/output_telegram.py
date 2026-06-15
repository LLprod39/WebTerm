from __future__ import annotations

import contextlib
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import httpx
from django.conf import settings

from app.agent_kernel.memory.redaction import sanitize_observation_text
from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


def _load_notif_cfg() -> dict[str, Any]:
    try:
        from studio.views import _load_notif_config

        cfg = _load_notif_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {
            "telegram_bot_token": getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "",
            "telegram_chat_id": getattr(settings, "TELEGRAM_CHAT_ID", "") or "",
        }


def _global_tg_defaults() -> tuple[str, str]:
    cfg = _load_notif_cfg()
    return str(cfg.get("telegram_bot_token") or ""), str(cfg.get("telegram_chat_id") or "")


def _resolve_telegram_target(config: dict[str, Any], *, token_keys: tuple[str, ...], chat_keys: tuple[str, ...]) -> tuple[str, str]:
    global_token, global_chat = _global_tg_defaults()

    def _first_non_empty(keys: tuple[str, ...], fallback: str) -> str:
        for key in keys:
            value = str(config.get(key) or "").strip()
            if value:
                return value
        return str(fallback or "").strip()

    return _first_non_empty(token_keys, global_token), _first_non_empty(chat_keys, global_chat)


def _redact_pipeline_text(value: Any, *, limit: int | None = None, preserve_values: list[str] | None = None) -> str:
    text = str(value or "")
    placeholders: dict[str, str] = {}
    for index, raw_value in enumerate(preserve_values or []):
        preserved = str(raw_value or "")
        if not preserved or preserved not in text:
            continue
        placeholder = f"__PIPELINE_REDACTION_PRESERVE_{index}__"
        placeholders[placeholder] = preserved
        text = text.replace(preserved, placeholder)

    redacted = sanitize_observation_text(text).text
    for placeholder, preserved in placeholders.items():
        redacted = redacted.replace(placeholder, preserved)
    if limit is not None:
        return redacted[: max(0, int(limit))]
    return redacted


def _redact_pipeline_value(value: Any, *, key: str = "", preserve_keys: set[str] | None = None) -> Any:
    if preserve_keys and key in preserve_keys:
        return value
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(child_key): _redact_pipeline_value(item, key=str(child_key), preserve_keys=preserve_keys) for child_key, item in value.items()}
    if isinstance(value, list):
        return [_redact_pipeline_value(item, preserve_keys=preserve_keys) for item in value]
    if isinstance(value, tuple):
        return [_redact_pipeline_value(item, preserve_keys=preserve_keys) for item in value]
    if isinstance(value, (int, float, bool)):
        return value
    return _redact_pipeline_text(value)


def _redacted_context(ctx: "ExecutionContext", *, preserve_keys: set[str] | None = None) -> defaultdict[str, Any]:
    raw_context = ctx.extra.get("context")
    if not isinstance(raw_context, dict):
        raw_context = {}
    return defaultdict(
        str,
        {
            str(key): _redact_pipeline_value(value, key=str(key), preserve_keys=preserve_keys)
            for key, value in raw_context.items()
        },
    )


async def _send_telegram_message(
    *,
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: str = "Markdown",
    reply_markup: dict[str, Any] | None = None,
    disable_web_page_preview: bool = False,
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = [message[i : i + 4000] for i in range(0, len(message), 4000)] or [""]
    sent = 0
    message_ids: list[int] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if disable_web_page_preview:
                payload["disable_web_page_preview"] = True
            if reply_markup and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup

            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                return {"status": "failed", "error": f"Telegram API error {resp.status_code}: {str(resp.text or '')[:200]}"}
            with contextlib.suppress(Exception):
                resp_payload = resp.json()
                message_id = int(((resp_payload.get("result") or {}) or {}).get("message_id"))
                message_ids.append(message_id)
            sent += 1

    return {
        "status": "completed",
        "output": f"Telegram message sent to {chat_id} ({sent} chunk(s))",
        "message_ids": message_ids,
        "last_message_id": message_ids[-1] if message_ids else None,
    }


@registry.register
class OutputTelegramNode(BaseNode):
    node_type = "output/telegram"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data if isinstance(self.node_data, dict) else {}
        bot_token, chat_id = _resolve_telegram_target(
            config,
            token_keys=("bot_token", "tg_bot_token", "telegram_bot_token"),
            chat_keys=("chat_id", "tg_chat_id", "telegram_chat_id"),
        )
        if not chat_id:
            chat_id = str(ctx.get_variable("tg_chat_id") or ctx.get_variable("chat_id") or "").strip()

        if not bot_token:
            return NodeResult(error="bot_token not configured. Set TELEGRAM_BOT_TOKEN in .env or fill in the node.")
        if not chat_id:
            return NodeResult(error="chat_id not configured. Set TELEGRAM_CHAT_ID in .env or fill in the node.")

        message_template = str(config.get("message") or "")
        if not message_template:
            lines = [f"Pipeline: {getattr(ctx.pipeline, 'name', '') or f'#{ctx.run_id}'}\n"]
            for node_id, state in ctx.node_outputs.items():
                out = _redact_pipeline_text((state.get("output") or "").strip())
                if out:
                    lines.append(f"[{node_id}]\n{out[:800]}")
            message_template = "\n\n".join(lines) or f"Pipeline {getattr(ctx.pipeline, 'name', '') or ctx.run_id} status update."

        preserve_context_keys = {str(item) for item in config.get("_redaction_preserve_context_keys", []) if str(item or "")}
        subs = _redacted_context(ctx, preserve_keys=preserve_context_keys)
        runtime = ctx.extra.get("runtime") if isinstance(ctx.extra.get("runtime"), dict) else {}
        subs["pipeline_name"] = str(getattr(ctx.pipeline, "name", "") or "")
        subs["run_id"] = str(ctx.run_id)
        subs["entry_node_id"] = str(runtime.get("entry_node_id") or "")
        subs["trigger_type"] = str(runtime.get("trigger_type") or "")
        subs["trigger_name"] = str(runtime.get("trigger_name") or "")
        subs["all_outputs"] = "\n\n".join(
            f"[{node_id}]: {_redact_pipeline_text(state.get('output') or '', limit=500)}"
            for node_id, state in ctx.node_outputs.items()
            if state.get("output")
        )

        try:
            message = message_template.format_map(subs)
        except (KeyError, ValueError):
            message = message_template
        preserve_values = [str(item) for item in config.get("_redaction_preserve_values", []) if str(item or "")]
        message = _redact_pipeline_text(message, preserve_values=preserve_values)

        try:
            result = await _send_telegram_message(
                bot_token=bot_token,
                chat_id=chat_id,
                message=message,
                parse_mode=str(config.get("parse_mode") or "Markdown"),
                reply_markup=config.get("reply_markup") if isinstance(config.get("reply_markup"), dict) else None,
                disable_web_page_preview=bool(config.get("disable_web_page_preview", False)),
            )
        except Exception as exc:
            return NodeResult(error=f"Telegram send error: {exc}")

        status = str(result.get("status") or "failed")
        if status == "completed":
            return NodeResult(output=result)
        return NodeResult(error=str(result.get("error") or "Telegram send failed"), output=result)
