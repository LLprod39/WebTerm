from __future__ import annotations

from app.agent_kernel.domain.specs import ServerMemoryCard
from app.agent_kernel.memory.server_cards import build_server_memory_card


def get_server_card(server_id: int) -> ServerMemoryCard:
    from servers.models import (
        AgentRun,
        GlobalServerRules,
        Server,
        ServerAlert,
        ServerGroupKnowledge,
        ServerHealthCheck,
        ServerKnowledge,
        ServerMemoryEpisode,
        ServerMemoryRevalidation,
        ServerMemorySnapshot,
    )

    server = Server.objects.select_related("group", "user").get(pk=server_id)
    global_rules = GlobalServerRules.objects.filter(user=server.user).first()
    group_knowledge = []
    if server.group_id:
        group_knowledge = list(
            ServerGroupKnowledge.objects.filter(group=server.group, is_active=True).order_by("-updated_at")[:6]
        )
    snapshots = list(
        ServerMemorySnapshot.objects.filter(server=server, is_active=True, layer=ServerMemorySnapshot.LAYER_CANONICAL)
        .order_by("memory_key", "-version", "-updated_at")
    )
    episodes = list(
        ServerMemoryEpisode.objects.filter(server=server, is_active=True).order_by("-last_event_at", "-updated_at")[:8]
    )
    revalidations = list(
        ServerMemoryRevalidation.objects.filter(server=server, status=ServerMemoryRevalidation.STATUS_OPEN).order_by("-updated_at")[:6]
    )
    latest_health = ServerHealthCheck.objects.filter(server=server).order_by("-checked_at").first()
    active_alerts = list(ServerAlert.objects.filter(server=server, is_resolved=False).order_by("-created_at")[:5])
    recent_runs = list(AgentRun.objects.filter(server=server).select_related("agent").order_by("-started_at")[:4])
    legacy_knowledge = list(ServerKnowledge.objects.filter(server=server, is_active=True).order_by("-updated_at")[:8])
    return build_server_memory_card(
        server,
        global_rules=global_rules,
        group_knowledge=group_knowledge,
        snapshots=snapshots,
        episodes=episodes,
        revalidations=revalidations,
        latest_health=latest_health,
        active_alerts=active_alerts,
        recent_runs=recent_runs,
        legacy_knowledge=legacy_knowledge,
    )


def get_server_cards_batch(server_ids: list[int]) -> list[ServerMemoryCard]:
    """Load multiple server cards with batched queries."""
    if not server_ids:
        return []
    from servers.models import (
        AgentRun,
        GlobalServerRules,
        Server,
        ServerAlert,
        ServerGroupKnowledge,
        ServerHealthCheck,
        ServerKnowledge,
        ServerMemoryEpisode,
        ServerMemoryRevalidation,
        ServerMemorySnapshot,
    )

    servers = {s.id: s for s in Server.objects.select_related("group", "user").filter(pk__in=server_ids)}
    if not servers:
        return []

    user_ids = {s.user_id for s in servers.values() if s.user_id}
    group_ids = {s.group_id for s in servers.values() if s.group_id}

    global_rules_by_user = {}
    for gr in GlobalServerRules.objects.filter(user_id__in=user_ids):
        global_rules_by_user[gr.user_id] = gr

    group_knowledge_by_group: dict[int, list] = {}
    if group_ids:
        for gk in ServerGroupKnowledge.objects.filter(group_id__in=group_ids, is_active=True).order_by("-updated_at"):
            group_knowledge_by_group.setdefault(gk.group_id, []).append(gk)

    snapshots_by_server: dict[int, list] = {}
    for s in ServerMemorySnapshot.objects.filter(
        server_id__in=server_ids, is_active=True, layer=ServerMemorySnapshot.LAYER_CANONICAL
    ).order_by("memory_key", "-version", "-updated_at"):
        snapshots_by_server.setdefault(s.server_id, []).append(s)

    episodes_by_server: dict[int, list] = {}
    for e in ServerMemoryEpisode.objects.filter(server_id__in=server_ids, is_active=True).order_by("-last_event_at", "-updated_at")[
        : len(server_ids) * 8
    ]:
        episodes_by_server.setdefault(e.server_id, []).append(e)

    revalidations_by_server: dict[int, list] = {}
    for r in ServerMemoryRevalidation.objects.filter(
        server_id__in=server_ids, status=ServerMemoryRevalidation.STATUS_OPEN
    ).order_by("-updated_at")[: len(server_ids) * 6]:
        revalidations_by_server.setdefault(r.server_id, []).append(r)

    latest_health_by_server: dict[int, ServerHealthCheck | None] = {}
    for hc in ServerHealthCheck.objects.filter(server_id__in=server_ids).order_by("server_id", "-checked_at"):
        if hc.server_id not in latest_health_by_server:
            latest_health_by_server[hc.server_id] = hc

    alerts_by_server: dict[int, list] = {}
    for a in ServerAlert.objects.filter(server_id__in=server_ids, is_resolved=False).order_by("-created_at"):
        alerts_by_server.setdefault(a.server_id, []).append(a)

    runs_by_server: dict[int, list] = {}
    for r in AgentRun.objects.filter(server_id__in=server_ids).select_related("agent").order_by("-started_at")[: len(server_ids) * 4]:
        runs_by_server.setdefault(r.server_id, []).append(r)

    knowledge_by_server: dict[int, list] = {}
    for k in ServerKnowledge.objects.filter(server_id__in=server_ids, is_active=True).order_by("-updated_at"):
        knowledge_by_server.setdefault(k.server_id, []).append(k)

    cards = []
    for sid in server_ids:
        server = servers.get(sid)
        if not server:
            continue
        cards.append(
            build_server_memory_card(
                server,
                global_rules=global_rules_by_user.get(server.user_id),
                group_knowledge=group_knowledge_by_group.get(server.group_id, [])[:6],
                snapshots=snapshots_by_server.get(sid, []),
                episodes=episodes_by_server.get(sid, [])[:8],
                revalidations=revalidations_by_server.get(sid, [])[:6],
                latest_health=latest_health_by_server.get(sid),
                active_alerts=alerts_by_server.get(sid, [])[:5],
                recent_runs=runs_by_server.get(sid, [])[:4],
                legacy_knowledge=knowledge_by_server.get(sid, [])[:8],
            )
        )
    return cards
