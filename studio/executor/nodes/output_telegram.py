from __future__ import annotations

from typing import TYPE_CHECKING, Any

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.pipeline_notifications import (
    _global_tg_defaults,
    _load_notif_cfg,
    _send_telegram_message,
    httpx,
)
from studio.pipeline_redaction import (
    redact_pipeline_text as _redact_pipeline_text,
    redacted_execution_context as _redacted_context,
)

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


def _resolve_telegram_target(config: dict[str, Any], *, token_keys: tuple[str, ...], chat_keys: tuple[str, ...]) -> tuple[str, str]:
    global_token, global_chat = _global_tg_defaults()

    def _first_non_empty(keys: tuple[str, ...], fallback: str) -> str:
        for key in keys:
            value = str(config.get(key) or "").strip()
            if value:
                return value
        return str(fallback or "").strip()

    return _first_non_empty(token_keys, global_token), _first_non_empty(chat_keys, global_chat)


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
