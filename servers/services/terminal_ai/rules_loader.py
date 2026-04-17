"""
Terminal AI rules + knowledge context loader (F2-4).

Extracted from ``SSHTerminalConsumer._get_ai_rules_and_forbidden`` (originally
~140 lines of ORM logic inside the WebSocket consumer — violated R-002/CONSTRAINT-03).

Loads, for a given (user, server) pair:
- forbidden command patterns (global + group)
- rules context text (global + group + server network + cumulative knowledge)
- required preflight checks
- merged environment variables (global < group < server)

Stays under the ORM boundary via the ``@database_sync_to_async`` decorator so
it can be called from async consumer code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from channels.db import database_sync_to_async
from django.db.models import Q
from django.utils import timezone


@dataclass(frozen=True)
class TerminalRulesContext:
    """Immutable snapshot of rules/context for one terminal AI turn.

    Consumers should treat this as read-only; all fields are already
    deduplicated/cleaned.
    """

    forbidden_patterns: list[str] = field(default_factory=list)
    rules_context: str = ""
    required_checks: list[str] = field(default_factory=list)
    environment_vars: dict[str, Any] = field(default_factory=dict)

    def as_tuple(
        self,
    ) -> tuple[list[str], str, list[str], dict[str, Any]]:
        """Backward-compat tuple shape used by the legacy consumer method."""
        return (
            list(self.forbidden_patterns),
            self.rules_context,
            list(self.required_checks),
            dict(self.environment_vars),
        )


_EMPTY = TerminalRulesContext()


def _dedup_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _load_terminal_rules_sync(*, user_id: int, server_id: int) -> TerminalRulesContext:
    """Sync body for :func:`load_terminal_rules`.

    Exposed separately so unit tests can call the DB-touching logic
    synchronously via ``pytest.mark.django_db`` without hitting the
    ``database_sync_to_async`` thread-pool boundary (which clashes with
    psycopg test-transaction semantics on Windows).
    """
    from servers.models import (
        GlobalServerRules,
        Server,
        ServerGroupKnowledge,
        ServerKnowledge,
        ServerShare,
    )

    now = timezone.now()
    server = (
        Server.objects.select_related("group", "user")
        .filter(id=server_id, is_active=True)
        .filter(
            Q(user_id=user_id)
            | (
                Q(shares__user_id=user_id, shares__is_revoked=False)
                & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
            )
        )
        .distinct()
        .first()
    )
    if not server:
        return _EMPTY

    share = None
    if server.user_id != user_id:
        share = (
            ServerShare.objects.filter(server_id=server_id, user_id=user_id, is_revoked=False)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .first()
        )
    share_context_enabled = bool(share.share_context) if share else True

    global_rules = GlobalServerRules.objects.filter(user_id=server.user_id).first()

    forbidden: list[str] = []
    parts: list[str] = []
    required_checks: list[str] = []
    env_vars: dict[str, Any] = {}

    if global_rules:
        if share_context_enabled:
            ctx = global_rules.get_context_for_ai()
            if ctx:
                parts.append(ctx)
            required_checks.extend(
                str(x) for x in (global_rules.required_checks or []) if str(x).strip()
            )
            env_vars.update(global_rules.environment_vars or {})
        if global_rules.forbidden_commands:
            forbidden.extend(str(x) for x in global_rules.forbidden_commands if x)

    if server.group:
        if share_context_enabled:
            gctx = server.group.get_context_for_ai()
            if gctx:
                parts.append(gctx)
            env_vars.update(server.group.environment_vars or {})
        if server.group.forbidden_commands:
            forbidden.extend(str(x) for x in server.group.forbidden_commands if x)

    if share_context_enabled:
        try:
            server_ctx = server.get_network_context_summary()
            if server_ctx:
                parts.append("=== КОНТЕКСТ СЕРВЕРА ===\n" + server_ctx)
        except Exception:
            pass

        # Compact knowledge context so AI continuity between runs works.
        try:
            knowledge_rows = list(
                ServerKnowledge.objects.filter(server_id=server.id, is_active=True)
                .order_by("-updated_at")
                .values_list("category", "title", "content")[:12]
            )
            if knowledge_rows:
                k_lines = []
                for category, title, content in knowledge_rows:
                    t = str(title or "").strip()
                    c = str(content or "").strip().replace("\n", " ")
                    if t or c:
                        k_lines.append(f"- [{category}] {t}: {c[:220]}")
                if k_lines:
                    parts.append("=== НАКОПЛЕННЫЕ ЗНАНИЯ О СЕРВЕРЕ ===\n" + "\n".join(k_lines))
        except Exception:
            pass

        if server.group_id:
            try:
                gk_rows = list(
                    ServerGroupKnowledge.objects.filter(group_id=server.group_id, is_active=True)
                    .order_by("-updated_at")
                    .values_list("category", "title", "content")[:8]
                )
                if gk_rows:
                    gk_lines = []
                    for category, title, content in gk_rows:
                        t = str(title or "").strip()
                        c = str(content or "").strip().replace("\n", " ")
                        if t or c:
                            gk_lines.append(f"- [{category}] {t}: {c[:220]}")
                    if gk_lines:
                        parts.append("=== ГРУППОВЫЕ ЗНАНИЯ ===\n" + "\n".join(gk_lines))
            except Exception:
                pass

        # Server-level env vars from network_config have highest priority.
        if isinstance(server.network_config, dict):
            env_vars.update(server.network_config.get("env_vars") or {})
            env_vars.update(server.network_config.get("environment") or {})

    return TerminalRulesContext(
        forbidden_patterns=_dedup_preserve_order(forbidden),
        rules_context="\n\n".join(p for p in parts if p).strip(),
        required_checks=_dedup_preserve_order(required_checks),
        environment_vars=env_vars,
    )


# Async wrapper used by the WebSocket consumer.
load_terminal_rules = database_sync_to_async(_load_terminal_rules_sync)


def _load_effective_environment_vars_sync(*, user_id: int, server_id: int) -> dict[str, Any]:
    """Sync body for :func:`load_effective_environment_vars`.

    Priority: global < group < server network_config (env_vars / environment).
    """
    from servers.models import GlobalServerRules, Server, ServerShare

    now = timezone.now()
    server = (
        Server.objects.select_related("group", "user")
        .filter(id=server_id, is_active=True)
        .filter(
            Q(user_id=user_id)
            | (
                Q(shares__user_id=user_id, shares__is_revoked=False)
                & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
            )
        )
        .distinct()
        .first()
    )
    if not server:
        return {}

    share = None
    if server.user_id != user_id:
        share = (
            ServerShare.objects.filter(server_id=server_id, user_id=user_id, is_revoked=False)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .first()
        )
    share_context_enabled = bool(share.share_context) if share else True

    env_vars: dict[str, Any] = {}
    if share_context_enabled:
        global_rules = GlobalServerRules.objects.filter(user_id=server.user_id).first()
        if global_rules:
            env_vars.update(global_rules.environment_vars or {})
        if server.group:
            env_vars.update(server.group.environment_vars or {})

    if isinstance(server.network_config, dict):
        env_vars.update(server.network_config.get("env_vars") or {})
        env_vars.update(server.network_config.get("environment") or {})

    return env_vars


# Async wrapper used by the WebSocket consumer.
load_effective_environment_vars = database_sync_to_async(_load_effective_environment_vars_sync)
