"""
Helpers for terminal agent target context.

These functions keep ORM access-control lookups and agent-target shaping out
of ``SSHTerminalConsumer`` while preserving the same ownership/share/group ACL
used by the terminal flow.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from loguru import logger

from servers.services.pilot_destination_policy import validate_pilot_ssh_destination


def normalize_extra_target_server_ids(raw_value: Any, *, limit: int = 5) -> list[int]:
    """Normalize user-provided extra target ids and cap them for SSH fan-out."""
    ids: list[int] = []
    for item in raw_value or []:
        try:
            server_id = int(item)
        except (TypeError, ValueError):
            continue
        if server_id:
            ids.append(server_id)
        if len(ids) >= limit:
            break
    return ids[:limit]


def list_user_accessible_servers_sync(*, user_id: int, server_ids: list[int]) -> list[dict]:
    """Return server metadata for ids the user can access."""
    from servers.models import Server, ServerShare

    own_ids = set(Server.objects.filter(user_id=user_id, id__in=server_ids).values_list("id", flat=True))
    shared_ids = set(
        ServerShare.objects.filter(
            user_id=user_id,
            server_id__in=server_ids,
            is_revoked=False,
        ).values_list("server_id", flat=True)
    )
    group_server_ids = set(
        Server.objects.filter(
            id__in=server_ids,
            group__memberships__user_id=user_id,
        ).values_list("id", flat=True)
    )
    allowed = own_ids | shared_ids | group_server_ids
    rows = list(
        Server.objects.filter(id__in=allowed).values(
            "id",
            "name",
            "host",
            "ai_read_only",
            "sudo_auth_mode",
            "notes",
        )
    )
    for row in rows:
        row["description"] = str(row.pop("notes", "") or "")
    return rows


list_user_accessible_servers = database_sync_to_async(list_user_accessible_servers_sync)


def load_user_accessible_server_sync(*, user_id: int, server_id: int) -> Any | None:
    """Fetch a server model the user is authorised to access."""
    from servers.models import Server, ServerShare

    own = Server.objects.filter(user_id=user_id, id=server_id).first()
    if own:
        return own
    if ServerShare.objects.filter(user_id=user_id, server_id=server_id, is_revoked=False).exists():
        return Server.objects.filter(id=server_id).first()
    return Server.objects.filter(
        id=server_id,
        group__memberships__user_id=user_id,
    ).first()


load_user_accessible_server = database_sync_to_async(load_user_accessible_server_sync)


async def build_agent_extra_targets(
    *,
    ai_settings: dict[str, Any] | None,
    user_id: int | None,
    primary_server_id: int | None = None,
    automation_allowed: bool = False,
    list_servers: Callable[..., Awaitable[list[dict]]] = list_user_accessible_servers,
) -> dict[str, Any]:
    """Return opt-in extra targets for a terminal-agent session."""
    from servers.services.terminal_ai.agent.tools import ServerTarget

    extras: dict[str, Any] = {}
    ids = normalize_extra_target_server_ids((ai_settings or {}).get("extra_target_server_ids"))
    if not ids or not user_id:
        return extras

    try:
        servers_allowed = await list_servers(user_id=user_id, server_ids=ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent extras lookup failed: %s", exc)
        return extras

    for row in servers_allowed:
        server_id = int(row["id"])
        if primary_server_id is not None and server_id == int(primary_server_id):
            continue
        name = f"srv-{server_id}"
        extras[name] = ServerTarget(
            name=name,
            server_id=server_id,
            display_name=str(row.get("name") or ""),
            host=str(row.get("host") or ""),
            read_only=bool(row.get("ai_read_only")) or not automation_allowed,
            sudo_auth_mode=str(row.get("sudo_auth_mode") or "none"),
            is_primary=False,
            description=str(row.get("description") or ""),
        )
    return extras


async def build_agent_memory_context(server_ids: list[int]) -> str:
    """Render layered server memory context for authorised agent targets."""
    ids = [int(server_id) for server_id in server_ids if server_id]
    if not ids:
        return ""
    try:
        from app.agent_kernel.memory.server_cards import render_server_cards_prompt
        from servers.adapters.memory_store import DjangoServerMemoryStore

        store = DjangoServerMemoryStore()
        cards = await sync_to_async(store._get_server_cards_batch_sync, thread_sensitive=True)(ids)
        cards_by_id = {int(getattr(card, "server_id", 0) or 0): card for card in cards}
        ordered = [cards_by_id[server_id] for server_id in ids if server_id in cards_by_id]
        if not ordered:
            return ""
        return render_server_cards_prompt(ordered, max_cards=3, max_records=6)
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent memory context load failed: %s", exc)
        return ""


async def open_agent_target_connection(
    *,
    user_id: int | None,
    server_id: int,
    get_master_password: Callable[[], Awaitable[str | None]],
    resolve_server_secret: Callable[..., Awaitable[str]],
    load_server: Callable[..., Awaitable[Any | None]] = load_user_accessible_server,
    build_connect_kwargs: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    connect: Callable[..., Awaitable[Any]] | None = None,
) -> Any | None:
    """Open an asyncssh connection to an authorised terminal-agent target.

    The helper is best-effort by design: failures are logged and returned as
    ``None`` so the agent tool can surface an unavailable-target error without
    crashing the terminal session.
    """
    if not user_id:
        return None

    try:
        server = await load_server(user_id=int(user_id), server_id=server_id)
        if server is None:
            logger.warning("agent open_target: server %s not accessible", server_id)
            return None

        master_password = str(await get_master_password() or "").strip()
        secret = await resolve_server_secret(
            server_id=server.id,
            master_password=master_password or "",
            plain_password="",
        )

        if build_connect_kwargs is None:
            from servers.services.terminal_connection_options import build_terminal_connect_kwargs

            build_connect_kwargs = build_terminal_connect_kwargs
        if connect is None:
            import asyncssh

            connect = asyncssh.connect

        validate_pilot_ssh_destination(server.host, server.port)
        connect_kwargs = await build_connect_kwargs(server, secret=secret or "")
        return await connect(**connect_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent open_target(server_id=%s) failed: %s", server_id, exc)
        return None
