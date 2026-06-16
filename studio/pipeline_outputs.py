from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx
from asgiref.sync import sync_to_async as _s2a
from django.conf import settings

from app.agent_kernel.memory.redaction import redact_payload

from .models import PipelineRun
from .pipeline_context import render_template_value
from .pipeline_notifications import (
    _global_email_defaults,
    _global_tg_defaults,
    _normalize_email_recipient,
    _resolve_from_email,
    _send_telegram_message,
)
from .pipeline_redaction import (
    redact_pipeline_text,
    redacted_mapping_context,
    redacted_node_outputs_payload,
)

logger = logging.getLogger(__name__)


def _resolve_telegram_target(
    config: dict[str, Any] | None,
    *,
    token_keys: tuple[str, ...],
    chat_keys: tuple[str, ...],
) -> tuple[str, str]:
    node_config = config if isinstance(config, dict) else {}
    global_token, global_chat = _global_tg_defaults()

    def _first_non_empty(keys: tuple[str, ...], fallback: str) -> str:
        for key in keys:
            value = str(node_config.get(key) or "").strip()
            if value:
                return value
        return str(fallback or "").strip()

    return (
        _first_non_empty(token_keys, global_token),
        _first_non_empty(chat_keys, global_chat),
    )


async def execute_output_email(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """
    Send an email report via SMTP.
    Uses Django EMAIL_* settings or per-node SMTP config.
    """
    config = node.get("data", {})
    g_to, g_host, g_user, g_pass, g_from = _global_email_defaults()

    to_email = (config.get("to_email") or g_to or "").strip()
    to_email = _normalize_email_recipient(to_email, (config.get("smtp_host") or "").strip() or g_host)
    if not to_email:
        return {
            "status": "failed",
            "error": "No recipient email. Set PIPELINE_NOTIFY_EMAIL in .env or fill in the node.",
        }

    subject_template = config.get("subject", f"Pipeline Report: {run.pipeline.name}")
    body_template = config.get("body", "")
    preserve_values = [str(item) for item in config.get("_redaction_preserve_values", []) if str(item or "")]
    preserve_context_keys = {str(item) for item in config.get("_redaction_preserve_context_keys", []) if str(item or "")}
    subs = redacted_mapping_context(context, preserve_keys=preserve_context_keys)

    try:
        subject = subject_template.format_map(subs)
    except (KeyError, ValueError):
        subject = subject_template
    subject = redact_pipeline_text(subject, preserve_values=preserve_values)

    if body_template:
        try:
            body = body_template.format_map(subs)
        except (KeyError, ValueError):
            body = body_template
    else:
        lines = [
            f"# Pipeline Run Report: {run.pipeline.name}",
            f"Status: {run.status}",
            "",
        ]
        for node_id, state in node_outputs.items():
            if state.get("output"):
                lines.append(f"## [{node_id}]")
                lines.append(redact_pipeline_text(state["output"], limit=2000))
                lines.append("")
        body = "\n".join(lines)
    body = redact_pipeline_text(body, preserve_values=preserve_values)

    smtp_host = (config.get("smtp_host") or "").strip() or g_host or getattr(settings, "EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int((config.get("smtp_port") or getattr(settings, "EMAIL_PORT", 587)) or 587)
    smtp_user = (config.get("smtp_user") or "").strip() or g_user or getattr(settings, "EMAIL_HOST_USER", "")
    smtp_password = (config.get("smtp_password") or "").strip() or g_pass or getattr(settings, "EMAIL_HOST_PASSWORD", "")
    from_email = (config.get("from_email") or "").strip() or g_from or smtp_user or "pipeline@noreply.local"
    from_email = _resolve_from_email(from_email, smtp_user, smtp_host)
    use_tls = smtp_port in (587, 465)

    def _send_sync() -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain", "utf-8"))
        try:
            import markdown

            html_body = markdown.markdown(body)
            msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html", "utf-8"))
        except ImportError:
            pass

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email.split(","), msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                if use_tls and smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email.split(","), msg.as_string())

    try:
        await asyncio.get_event_loop().run_in_executor(None, _send_sync)
        return {"status": "completed", "output": f"✉️ Email sent to {to_email} | Subject: {subject}"}
    except Exception as exc:
        logger.warning("output/email node %s failed: %s", node.get("id"), exc)
        return {"status": "failed", "error": f"SMTP error: {redact_pipeline_text(str(exc))}"}


async def execute_output_report(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """Compile a markdown report from all node outputs."""
    config = node.get("data", {})
    template = config.get("template", "")
    safe_context = redacted_mapping_context(context)

    if template:
        report = render_template_value(template, safe_context)
    else:
        lines = [f"# Pipeline Run Report: {run.pipeline.name}\n"]
        for node_id, state in node_outputs.items():
            lines.append(f"## Node `{node_id}`")
            lines.append(f"**Status:** {state.get('status', 'unknown')}")
            if state.get("output"):
                lines.append(f"```\n{redact_pipeline_text(state['output'], limit=2000)}\n```")
            if state.get("error"):
                lines.append(f"**Error:** {redact_pipeline_text(state['error'])}")
            lines.append("")
        report = "\n".join(lines)
    report = redact_pipeline_text(report)

    await _s2a(PipelineRun.objects.filter(pk=run.pk).update)(summary=report)
    return {"status": "completed", "output": report}


async def execute_output_webhook(node: dict, context: dict, node_outputs: dict[str, dict]) -> dict:
    """POST the pipeline results to an external webhook URL."""
    config = node.get("data", {})
    url = str(render_template_value(config.get("url", ""), context) or "").strip()
    if not url:
        return {"status": "failed", "error": "No URL configured"}

    safe_context = redacted_mapping_context(context)
    payload = {
        "context": dict(safe_context),
        "outputs": redacted_node_outputs_payload(node_outputs),
    }
    extra_payload = config.get("extra_payload", {})
    if isinstance(extra_payload, dict):
        payload.update(render_template_value(extra_payload, safe_context))
    payload, _redaction_report, _redaction_hashes = redact_payload(payload)
    headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
    rendered_headers = render_template_value(headers, safe_context) if isinstance(headers, dict) else {}
    try:
        timeout_seconds = max(1, min(int(config.get("timeout_seconds") or 30), 120))
    except (TypeError, ValueError):
        timeout_seconds = 30
    fail_on_non_2xx = bool(config.get("fail_on_non_2xx", False))

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=rendered_headers)
            if fail_on_non_2xx and not (200 <= response.status_code < 300):
                return {
                    "status": "failed",
                    "error": f"Webhook returned HTTP {response.status_code}",
                    "output": f"POST {redact_pipeline_text(url)} → {response.status_code}",
                    "http_status": response.status_code,
                }
            return {
                "status": "completed",
                "output": f"POST {redact_pipeline_text(url)} → {response.status_code}",
                "http_status": response.status_code,
            }
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


async def execute_output_telegram(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """Send a message via Telegram Bot API. Falls back to global Studio notification settings."""
    config = node.get("data", {})
    bot_token, chat_id = _resolve_telegram_target(
        config,
        token_keys=("bot_token", "tg_bot_token", "telegram_bot_token"),
        chat_keys=("chat_id", "tg_chat_id", "telegram_chat_id"),
    )
    if not chat_id:
        chat_id = str(context.get("tg_chat_id") or context.get("chat_id") or "").strip()

    if not bot_token:
        return {"status": "failed", "error": "bot_token not configured. Set TELEGRAM_BOT_TOKEN in .env or fill in the node."}
    if not chat_id:
        return {"status": "failed", "error": "chat_id not configured. Set TELEGRAM_CHAT_ID in .env or fill in the node."}

    message_template = config.get("message", "")
    if not message_template:
        lines = [f"📊 *Pipeline: {run.pipeline.name}*\n"]
        for node_id, state in node_outputs.items():
            out = redact_pipeline_text((state.get("output") or "").strip())
            if out:
                lines.append(f"*[{node_id}]*\n{out[:800]}")
        message_template = "\n\n".join(lines) or f"Pipeline {run.pipeline.name} status update."

    preserve_context_keys = {str(item) for item in config.get("_redaction_preserve_context_keys", []) if str(item or "")}
    subs = redacted_mapping_context(context, preserve_keys=preserve_context_keys)
    subs["pipeline_name"] = run.pipeline.name
    subs["run_id"] = str(run.pk)
    subs["entry_node_id"] = str(run.entry_node_id or "")
    subs["trigger_type"] = str(getattr(run.trigger, "trigger_type", "") or "")
    subs["trigger_name"] = str(getattr(run.trigger, "name", "") or "")
    subs["all_outputs"] = "\n\n".join(
        f"[{node_id}]: {redact_pipeline_text(value.get('output') or '', limit=500)}"
        for node_id, value in node_outputs.items()
        if value.get("output")
    )
    try:
        message = message_template.format_map(subs)
    except (KeyError, ValueError):
        message = message_template
    preserve_values = [str(item) for item in config.get("_redaction_preserve_values", []) if str(item or "")]
    message = redact_pipeline_text(message, preserve_values=preserve_values)

    parse_mode = config.get("parse_mode", "Markdown")
    reply_markup = config.get("reply_markup")
    disable_web_page_preview = bool(config.get("disable_web_page_preview", False))

    try:
        return await _send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            message=message,
            parse_mode=parse_mode,
            reply_markup=reply_markup if isinstance(reply_markup, dict) else None,
            disable_web_page_preview=disable_web_page_preview,
        )
    except Exception as exc:
        return {"status": "failed", "error": f"Telegram send error: {exc}"}
