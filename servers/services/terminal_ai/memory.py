"""
Terminal AI memory-writing helpers (F2-3 partial).

Extracts the pure/ORM-bound pieces of "save concise server memory snapshot"
flow out of the SSH consumer, so they are unit-testable and can be reused
by a future orchestrator (F2-2).

Public API:
- ``sanitize_memory_line(text)``: redact+truncate a single memory line.
- ``select_memory_candidate_commands(rows)``: filter command history rows
  eligible for memory snapshot (noise / trivial commands dropped).
- ``save_server_profile_sync(...)``: synchronous Django-ORM writer.
- ``save_server_profile``: async wrapper via ``database_sync_to_async``.

The LLM prompt + pydantic parsing for extraction itself live in
:mod:`servers.services.terminal_ai.prompts.build_memory_extraction_prompt`
and :mod:`servers.services.terminal_ai.schemas.MemoryExtraction`.
"""
from __future__ import annotations

from typing import Any

from channels.db import database_sync_to_async


def sanitize_memory_line(text: str) -> str:
    """Strip newlines and truncate a single fact/issue/summary line."""
    line = str(text or "").replace("\n", " ").replace("\r", " ").strip()
    return line[:400]


def _dedup_clean_list(items: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items or []:
        line = sanitize_memory_line(str(item or ""))
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= limit:
            break
    return out


def select_memory_candidate_commands(commands_with_output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter command rows eligible for AI memory snapshot.

    Applies ``servers.memory_heuristics.should_capture_command_history_memory``
    and ``normalize_memory_command_text`` so we never feed noise commands
    (``ls``, ``pwd`` etc.) into the LLM memory extractor.
    """
    from servers.memory_heuristics import (
        normalize_memory_command_text,
        should_capture_command_history_memory,
    )

    candidates: list[dict[str, Any]] = []
    for row in commands_with_output or []:
        command = normalize_memory_command_text(str(row.get("cmd") or ""))
        if not command:
            continue
        output = str(row.get("output") or "").strip()
        exit_code = row.get("exit_code")
        if not should_capture_command_history_memory(
            command=command,
            output=output,
            exit_code=exit_code,
            actor_kind="agent",
            source_kind="agent",
        ):
            continue
        candidates.append({**row, "cmd": command, "output": output})
    return candidates


_DURABLE_COMMAND_HINTS = (
    # Package management
    "apt", "apt-get", "apt-cache", "dpkg", "yum", "dnf", "zypper", "apk",
    "pip", "pip3", "npm", "yarn", "pnpm", "brew",
    # Service / daemon control
    "systemctl", "service", "rc-service",
    # User / permissions
    "useradd", "usermod", "userdel", "groupadd", "passwd", "chown", "chmod", "chgrp",
    # Config writes / edits
    "sed", "tee", "install",
    # Container / orchestration
    "docker", "podman", "kubectl", "helm", "docker-compose",
    # Firewall / networking state-changers
    "iptables", "nft", "ufw", "firewall-cmd",
    # Filesystem layout
    "mkfs", "mount", "umount", "fdisk", "parted",
)

_NOISE_COMMAND_HINTS = (
    "ls", "pwd", "whoami", "id", "date", "uptime", "hostname", "uname",
    "echo", "cat", "head", "tail", "clear", "history", "which", "type",
    "df", "du", "free", "ps", "top", "htop",
)


def _cmd_root(cmd: str) -> str:
    """Return the first token of ``cmd`` without path prefix.

    Tolerates ``sudo``, pipes, redirects — we only need an approximate
    classification, false-positives merely cost us an extra extraction
    call, they never drop legitimate signal.
    """
    text = str(cmd or "").strip()
    if not text:
        return ""
    # Peel leading ``sudo`` / ``nice`` / ``time`` wrappers.
    tokens = text.split()
    while tokens and tokens[0] in {"sudo", "nice", "time", "env"}:
        tokens = tokens[1:]
    if not tokens:
        return ""
    first = tokens[0]
    # Strip VAR=value style env assignments (``FOO=bar ls``).
    if "=" in first and not first.startswith("/"):
        # Whole token looks like env assignment — use next token.
        if len(tokens) > 1:
            first = tokens[1]
        else:
            return ""
    return first.split("/")[-1].lower()


def should_extract_memory(done_items: list[dict[str, Any]] | None) -> bool:
    """Return True when a memory-extraction LLM call is worthwhile (A2).

    Cheap-to-skip cases (~30% of runs in practice):

    * ``len < 2`` — a single command rarely yields a durable multi-fact insight
      worth the extraction cost.
    * Every command succeeded AND every command root is in the noise list
      (``ls``, ``pwd``, ``df`` …) — these are diagnostic peeks, not ops state
      changes.

    In all other cases we keep extracting:
      * non-zero exit somewhere → worth learning *why* it failed;
      * any durable hint (``apt``, ``systemctl``, ``docker``…) → likely
        changed server state and must be remembered.
    """
    items = list(done_items or [])
    if len(items) < 2:
        return False

    # If anything failed, extract.
    for it in items:
        exit_code = it.get("exit_code")
        if exit_code not in (None, 0, 130):
            return True

    # All succeeded — only extract when there's a durable signal.
    has_durable = False
    for it in items:
        root = _cmd_root(str(it.get("cmd", "")))
        if not root:
            continue
        if root in _DURABLE_COMMAND_HINTS:
            has_durable = True
            break

    if has_durable:
        return True

    # Otherwise, if EVERY root is noise, skip.
    all_noise = all(
        _cmd_root(str(it.get("cmd", ""))) in _NOISE_COMMAND_HINTS
        for it in items
    )
    # Mixed case: no durable hint, some non-noise — keep extraction (safer).
    return not all_noise


def _bridge_to_layered_memory(
    *,
    server_id: int,
    cleaned_summary: str,
    cleaned_facts: list[str],
    cleaned_issues: list[str],
) -> dict[str, int]:
    """Feed the same terminal-AI signals into the layered agent_kernel memory
    store (F2-7). Runs AFTER the legacy ``ServerKnowledge`` write so the UI
    keeps working even if layered ingestion fails.

    Facts → ``upsert_server_fact`` (triggers dedup + conflict detection).
    Issues → ``record_incident`` (opens a revalidation note under ``risks``).

    Errors are swallowed — the layered memory is a best-effort bonus; if it's
    not configured (e.g. policy disabled), the terminal AI must not break.
    """
    try:
        from servers.adapters.memory_store import DjangoServerMemoryStore
    except Exception:  # pragma: no cover — extension point missing
        return {"facts": 0, "incidents": 0}

    store = DjangoServerMemoryStore()
    source_ref = f"terminal-ai:{server_id}"

    facts_written = 0
    for fact_text in cleaned_facts:
        title = fact_text[:120] or "Факт из терминала"
        try:
            store._upsert_server_fact_sync(  # noqa: SLF001 — intentional sync entry point
                server_id,
                {
                    "title": title,
                    "content": fact_text,
                    "category": "profile",
                    "confidence": 0.78,
                    "verified": False,
                },
                source_ref=source_ref,
                session_id=source_ref,
            )
            facts_written += 1
        except Exception:  # pragma: no cover — defensive
            continue

    incidents_written = 0
    for issue_text in cleaned_issues:
        title = issue_text[:120] or "Риск из терминала"
        try:
            store._record_incident_sync(  # noqa: SLF001 — intentional sync entry point
                server_id,
                {
                    "title": title,
                    "content": issue_text,
                    "category": "issues",
                    "confidence": 0.80,
                },
                source_ref=source_ref,
                session_id=source_ref,
            )
            incidents_written += 1
        except Exception:  # pragma: no cover — defensive
            continue

    return {"facts": facts_written, "incidents": incidents_written}


def save_server_profile_sync(
    *,
    user_id: int,
    server_id: int,
    summary: str,
    facts: list[str],
    issues: list[str],
    bridge_to_layered_memory: bool = True,
) -> dict[str, Any]:
    """Persist a concise server profile + issues snapshot to ``ServerKnowledge``
    and (F2-7) also feed the same signals into the layered agent_kernel
    memory store for dedup / conflict detection / revalidation.

    Skips write entirely when neither facts nor issues contain durable signals
    (``should_persist_ai_memory``). Returns a dict describing what was written
    so the orchestrator can decide whether to notify the user. The dict also
    includes ``layered``: ``{"facts": n, "incidents": m}`` on success.
    """
    from django.contrib.auth.models import User
    from django.utils import timezone

    from servers.knowledge_service import ServerKnowledgeService
    from servers.memory_heuristics import should_persist_ai_memory
    from servers.models import Server

    user = User.objects.filter(id=user_id).first()
    server = Server.objects.filter(id=server_id).first()
    if not server:
        return {"saved": 0, "titles": [], "layered": {"facts": 0, "incidents": 0}}

    cleaned_summary = sanitize_memory_line(summary)
    cleaned_facts = _dedup_clean_list(list(facts or []), limit=16)
    cleaned_issues = _dedup_clean_list(list(issues or []), limit=8)

    if not should_persist_ai_memory(facts=cleaned_facts, issues=cleaned_issues):
        return {"saved": 0, "titles": [], "layered": {"facts": 0, "incidents": 0}}

    saved = 0
    titles: list[str] = []
    now_str = timezone.now().strftime("%Y-%m-%d %H:%M")

    if cleaned_summary or cleaned_facts:
        profile_parts = [f"Обновлено: {now_str}"]
        if cleaned_summary:
            profile_parts.append(f"Кратко: {cleaned_summary}")
        if cleaned_facts:
            profile_parts.append("Факты:")
            profile_parts.extend([f"- {x}" for x in cleaned_facts[:10]])
        profile_content = "\n".join(profile_parts)[:3500]
        ServerKnowledgeService.save_ai_knowledge(
            server=server,
            title="Профиль сервера (авто)",
            content=profile_content,
            category="system",
            user=user,
            confidence=0.88,
        )
        saved += 1
        titles.append("Профиль сервера (авто)")

    if cleaned_issues:
        issues_parts = [f"Обновлено: {now_str}", "Риски/замечания:"]
        issues_parts.extend([f"- {x}" for x in cleaned_issues[:8]])
        issues_content = "\n".join(issues_parts)[:2500]
        ServerKnowledgeService.save_ai_knowledge(
            server=server,
            title="Текущие риски (авто)",
            content=issues_content,
            category="issues",
            user=user,
            confidence=0.8,
        )
        saved += 1
        titles.append("Текущие риски (авто)")

    # F2-7: additionally ingest into the layered memory store. Best-effort —
    # a failure here must not lose the ServerKnowledge write above.
    layered = {"facts": 0, "incidents": 0}
    if bridge_to_layered_memory:
        layered = _bridge_to_layered_memory(
            server_id=server_id,
            cleaned_summary=cleaned_summary,
            cleaned_facts=cleaned_facts,
            cleaned_issues=cleaned_issues,
        )

    return {"saved": saved, "titles": titles, "layered": layered}


# Async wrapper used by the WebSocket consumer / background task.
save_server_profile = database_sync_to_async(save_server_profile_sync)
