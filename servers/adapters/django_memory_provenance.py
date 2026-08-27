"""Redacted provenance helpers for LLM-assisted server memory generation."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from django.utils import timezone


def sha256_text(value: str) -> str:
    return sha256((value or "").encode("utf-8")).hexdigest()


def start_generation_log(
    *,
    server_id: int,
    generation_kind: str,
    model_alias: str,
    prompt_template_key: str,
    prompt_template_version: str,
    prompt: str,
):
    from servers.models import ServerMemoryGenerationLog

    prompt_hash = sha256_text(prompt)
    return ServerMemoryGenerationLog.objects.create(
        server_id=server_id,
        generation_kind=generation_kind,
        model_alias=str(model_alias or "")[:80],
        prompt_template_key=str(prompt_template_key or "")[:80],
        prompt_template_version=str(prompt_template_version or "")[:32],
        prompt_sha256=prompt_hash,
        prompt_redacted_ref=(
            f"template:{str(prompt_template_key or '')[:80]}:"
            f"{str(prompt_template_version or '')[:32]};sha256:{prompt_hash[:16]}"
        )[:255],
    )


def finish_generation_log(
    generation_log,
    *,
    status: str,
    output: str = "",
    execution_context: Any | None = None,
    error_code: str = "",
    error_type: str = "",
):
    """Finalize a log with hashes and internal refs, never raw prompt/output/errors."""
    from core_ui.models.ai_providers import AIProviderInvocation

    output_hash = sha256_text(output) if output else ""
    generation_log.status = status
    generation_log.output_sha256 = output_hash
    generation_log.output_redacted_ref = f"sha256:{output_hash[:16]}" if output_hash else ""
    generation_log.error_code = str(error_code or "")[:80]
    generation_log.error_redacted_ref = (f"error-type:{str(error_type or 'unknown')[:80]}" if error_code else "")[:255]
    generation_log.completed_at = timezone.now()

    if execution_context is not None:
        invocation = (
            AIProviderInvocation.objects.filter(
                user_id=execution_context.actor_user_id,
                project_id=execution_context.project_id,
                source_kind=execution_context.source_kind,
                source_id=str(execution_context.source_id),
                purpose=execution_context.purpose,
                idempotency_key=execution_context.idempotency_key,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        generation_log.invocation = invocation

    generation_log.save(
        update_fields=[
            "status",
            "output_sha256",
            "output_redacted_ref",
            "error_code",
            "error_redacted_ref",
            "completed_at",
            "invocation",
        ]
    )
    return generation_log
