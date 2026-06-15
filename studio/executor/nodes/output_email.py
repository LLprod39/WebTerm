from __future__ import annotations

import asyncio
import smtplib
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any

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
            "notify_email": getattr(settings, "PIPELINE_NOTIFY_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", "") or "",
            "smtp_host": getattr(settings, "EMAIL_HOST", "") or "",
            "smtp_user": getattr(settings, "EMAIL_HOST_USER", "") or "",
            "smtp_password": getattr(settings, "EMAIL_HOST_PASSWORD", "") or "",
            "from_email": getattr(settings, "DEFAULT_FROM_EMAIL", "") or "",
        }


def _global_email_defaults() -> tuple[str, str, str, str, str]:
    cfg = _load_notif_cfg()
    return (
        str(cfg.get("notify_email") or ""),
        str(cfg.get("smtp_host") or ""),
        str(cfg.get("smtp_user") or ""),
        str(cfg.get("smtp_password") or ""),
        str(cfg.get("from_email") or ""),
    )


def _resolve_from_email(from_email: str, smtp_user: str, smtp_host: str) -> str:
    if not from_email or "weuai.site" in from_email or "noreply@" in (from_email or "").lower():
        if not smtp_user:
            return from_email or "pipeline@noreply.local"
        user = (smtp_user or "").strip()
        if "@" in user:
            return user
        host = (smtp_host or "").lower()
        if "yandex" in host:
            return f"{user}@yandex.ru"
        if "gmail" in host:
            return f"{user}@gmail.com"
        return user
    return from_email


def _normalize_email_recipient(to_email: str, smtp_host: str) -> str:
    to_email = (to_email or "").strip()
    if not to_email or "@" in to_email:
        return to_email
    host = (smtp_host or "").lower()
    if "yandex" in host:
        return f"{to_email}@yandex.ru"
    if "gmail" in host:
        return f"{to_email}@gmail.com"
    return to_email


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


def _coerce_smtp_port(value: Any) -> int:
    try:
        return int(value or getattr(settings, "EMAIL_PORT", 587) or 587)
    except (TypeError, ValueError):
        return 587


@registry.register
class OutputEmailNode(BaseNode):
    node_type = "output/email"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data if isinstance(self.node_data, dict) else {}
        g_to, g_host, g_user, g_pass, g_from = _global_email_defaults()

        to_email = str(config.get("to_email") or g_to or "").strip()
        to_email = _normalize_email_recipient(to_email, str(config.get("smtp_host") or "").strip() or g_host)
        if not to_email:
            return NodeResult(error="No recipient email. Set PIPELINE_NOTIFY_EMAIL in .env or fill in the node.")

        pipeline_name = str(getattr(ctx.pipeline, "name", "") or f"#{ctx.run_id}")
        subject_template = str(config.get("subject") or f"Pipeline Report: {pipeline_name}")
        body_template = str(config.get("body") or "")
        preserve_values = [str(item) for item in config.get("_redaction_preserve_values", []) if str(item or "")]
        preserve_context_keys = {str(item) for item in config.get("_redaction_preserve_context_keys", []) if str(item or "")}
        subs = _redacted_context(ctx, preserve_keys=preserve_context_keys)

        try:
            subject = subject_template.format_map(subs)
        except (KeyError, ValueError):
            subject = subject_template
        subject = _redact_pipeline_text(subject, preserve_values=preserve_values)

        if body_template:
            try:
                body = body_template.format_map(subs)
            except (KeyError, ValueError):
                body = body_template
        else:
            runtime = ctx.extra.get("runtime") if isinstance(ctx.extra.get("runtime"), dict) else {}
            lines = [f"# Pipeline Run Report: {pipeline_name}", f"Status: {runtime.get('run_status', '')}", ""]
            for node_id, state in ctx.node_outputs.items():
                if state.get("output"):
                    lines.append(f"## [{node_id}]")
                    lines.append(_redact_pipeline_text(state["output"], limit=2000))
                    lines.append("")
            body = "\n".join(lines)
        body = _redact_pipeline_text(body, preserve_values=preserve_values)

        smtp_host = str(config.get("smtp_host") or "").strip() or g_host or getattr(settings, "EMAIL_HOST", "smtp.gmail.com")
        smtp_port = _coerce_smtp_port(config.get("smtp_port"))
        smtp_user = str(config.get("smtp_user") or "").strip() or g_user or getattr(settings, "EMAIL_HOST_USER", "")
        smtp_password = str(config.get("smtp_password") or "").strip() or g_pass or getattr(settings, "EMAIL_HOST_PASSWORD", "")
        from_email = str(config.get("from_email") or "").strip() or g_from or smtp_user or "pipeline@noreply.local"
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
            return NodeResult(output={"status": "completed", "output": f"Email sent to {to_email} | Subject: {subject}"})
        except Exception as exc:
            return NodeResult(error=f"SMTP error: {exc}")
