"""Present Operator turn results as Telegram messages (text + confirm keyboards)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from studio.pipeline.pipeline_telegram import _redact_telegram_text
from telegram_hub.client import TELEGRAM_SAFE_CHUNK


@dataclass
class OutgoingTelegramMessage:
    text: str
    parse_mode: str | None = "HTML"
    reply_markup: dict[str, Any] | None = None


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_YAML_KEYS = {"yaml", "source_yaml", "content", "playbook_yaml", "body"}


def escape_telegram_html(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def markdown_to_telegram_html(text: str) -> str:
    """Convert a small Markdown subset to Telegram HTML. Unknown markup is escaped."""
    raw = str(text or "")
    if not raw.strip():
        return ""

    # Fenced code blocks first
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"```(?:\w+)?\n?(.*?)```", raw, flags=re.S):
        parts.append(_inline_md_to_html(raw[cursor : match.start()]))
        parts.append(f"<pre><code>{escape_telegram_html(match.group(1).rstrip())}</code></pre>")
        cursor = match.end()
    parts.append(_inline_md_to_html(raw[cursor:]))
    return "".join(parts).strip()


def _inline_md_to_html(chunk: str) -> str:
    if not chunk:
        return ""

    placeholders: list[str] = []

    def _store(value: str) -> str:
        placeholders.append(value)
        return f"\x00PH{len(placeholders) - 1}\x00"

    work = chunk
    work = _LINK_RE.sub(
        lambda m: _store(f'<a href="{escape_telegram_html(m.group(2))}">{escape_telegram_html(m.group(1))}</a>'),
        work,
    )
    work = _CODE_RE.sub(lambda m: _store(f"<code>{escape_telegram_html(m.group(1))}</code>"), work)
    work = _BOLD_RE.sub(lambda m: _store(f"<b>{escape_telegram_html(m.group(1))}</b>"), work)
    work = _ITALIC_RE.sub(lambda m: _store(f"<i>{escape_telegram_html(m.group(1))}</i>"), work)
    work = escape_telegram_html(work)
    for index, value in enumerate(placeholders):
        work = work.replace(f"\x00PH{index}\x00", value)
    return work


def chunk_telegram_text(text: str, *, limit: int = TELEGRAM_SAFE_CHUNK) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    if len(raw) <= limit:
        return [raw]
    chunks: list[str] = []
    remaining = raw
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, limit)
        if cut < limit // 3:
            cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 3:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return [c for c in chunks if c]


def _strip_memory_from_description(text: str) -> str:
    cleaned = str(text or "")
    if "⚠ Memory:" in cleaned:
        cleaned = cleaned.split("⚠ Memory:", 1)[0]
    if "Memory:" in cleaned and "Canonical" in cleaned:
        lines = []
        for line in cleaned.splitlines():
            if "Canonical" in line and "Memory" in line:
                continue
            lines.append(line)
        cleaned = "\n".join(lines)
    return cleaned.strip()


def _human_preview_lines(preview: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if not isinstance(preview, dict):
        return lines
    playbook_id = preview.get("playbook_id")
    if playbook_id is not None:
        lines.append(f"Playbook id: {playbook_id}")
    name = preview.get("name") or preview.get("title")
    if name:
        lines.append(f"Имя: {str(name)[:120]}")
    server_ids = preview.get("server_ids")
    if isinstance(server_ids, list) and server_ids:
        lines.append("Серверы: " + ", ".join(str(item) for item in server_ids[:12]))
    for key in ("server_id", "command", "check_mode"):
        if key in preview and preview[key] not in (None, "", [], {}):
            lines.append(f"{key}: {preview[key]}")
    extra_vars = preview.get("extra_vars")
    if isinstance(extra_vars, dict) and extra_vars:
        keys = ", ".join(str(k) for k in list(extra_vars.keys())[:12])
        lines.append(f"extra_vars: {keys}")
    yaml_keys_present = [key for key in _YAML_KEYS if preview.get(key)]
    if yaml_keys_present:
        sample = preview.get(yaml_keys_present[0])
        lines.append(f"YAML: ~{len(str(sample or ''))} символов (полный текст в веб-чате)")
    steps = preview.get("steps") or preview.get("tasks")
    if isinstance(steps, list) and steps:
        lines.append(f"Шагов: {len(steps)}")
    return lines


def action_card_text(action) -> str:
    preview = action.safe_preview if isinstance(getattr(action, "safe_preview", None), dict) else {}
    parts = [
        f"⚡ {getattr(action, 'title', None) or getattr(action, 'action_type', 'action')}",
        f"Риск: {getattr(action, 'risk', '')}",
    ]
    description = _strip_memory_from_description(getattr(action, "description", "") or "")
    if description:
        parts.append(description[:400])
    parts.extend(_human_preview_lines(preview))
    from core_ui.models import AssistantAction

    if getattr(action, "risk", None) == AssistantAction.RISK_DANGEROUS:
        parts.append("Для опасного действия ответьте reply текстом подтверждения из веб-чата.")
    return _redact_telegram_text("\n".join(parts), limit=3500)


def inline_keyboard_for_action(*, action, telegram_user_id: int, bot_id: int) -> dict[str, Any] | None:
    from core_ui.models import AssistantAction
    from telegram_hub.services.linking import build_action_callback_data

    if getattr(action, "risk", None) == AssistantAction.RISK_DANGEROUS:
        return None
    try:
        confirm = build_action_callback_data(
            decision="confirm",
            action_id=action.pk,
            telegram_user_id=telegram_user_id,
            bot_id=bot_id,
        )
        cancel = build_action_callback_data(
            decision="cancel",
            action_id=action.pk,
            telegram_user_id=telegram_user_id,
            bot_id=bot_id,
        )
    except ValueError:
        return None
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Подтвердить", "callback_data": confirm},
                {"text": "❌ Отменить", "callback_data": cancel},
            ]
        ]
    }


def present_assistant_reply(
    *,
    content: str,
    metadata: dict[str, Any] | None = None,
    actions: list[Any] | None = None,
    telegram_user_id: int | None = None,
    bot_id: int | None = None,
    use_html: bool = True,
    user_message: str = "",
) -> list[OutgoingTelegramMessage]:
    """Build outbound Telegram messages from Operator assistant content + confirm actions."""
    from core_ui.models import AssistantAction
    from core_ui.services.operator_channel import finalize_telegram_assistant_text

    pending = [
        action
        for action in list(actions or [])
        if getattr(action, "status", None) == AssistantAction.STATUS_REQUIRES_CONFIRMATION
    ]
    text = finalize_telegram_assistant_text(
        content,
        metadata,
        user_message=user_message,
        awaiting_confirm=bool(pending),
    )
    text = _redact_telegram_text(text, limit=12000)
    outgoing: list[OutgoingTelegramMessage] = []

    if text.strip():
        body = markdown_to_telegram_html(text) if use_html else text
        parse_mode = "HTML" if use_html else None
        chunks = chunk_telegram_text(body)
        for chunk in chunks:
            outgoing.append(OutgoingTelegramMessage(text=chunk, parse_mode=parse_mode))

    for action in pending:
        markup = None
        if telegram_user_id is not None and bot_id is not None:
            markup = inline_keyboard_for_action(
                action=action,
                telegram_user_id=int(telegram_user_id),
                bot_id=int(bot_id),
            )
        card = action_card_text(action)
        card_html = markdown_to_telegram_html(card) if use_html else card
        outgoing.append(
            OutgoingTelegramMessage(
                text=card_html,
                parse_mode="HTML" if use_html else None,
                reply_markup=markup,
            )
        )
    return outgoing


async def send_presented_messages(
    client,
    *,
    chat_id: str | int,
    messages: list[OutgoingTelegramMessage],
) -> None:
    """Send presenter output; fall back to plain text if HTML parse_mode is rejected."""
    from telegram_hub.client import TelegramAPIError

    for item in messages:
        text = item.text
        parse_mode = item.parse_mode
        try:
            await client.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=item.reply_markup,
            )
        except TelegramAPIError:
            if parse_mode:
                # Strip tags roughly for plain fallback
                plain = re.sub(r"<[^>]+>", "", text)
                await client.send_message(
                    chat_id=chat_id,
                    text=plain or text,
                    parse_mode=None,
                    reply_markup=item.reply_markup,
                )
            else:
                raise
