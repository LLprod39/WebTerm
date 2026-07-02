from __future__ import annotations

from core_ui.access import feature_allowed_for_user
from studio.models import MCPServerPool
from studio.skill_registry import SkillNotFoundError, get_skill
from studio.views.mcp_views import _mcp_read_queryset_for_user

STUDIO_FEATURE_PIPELINES = "studio_pipelines"
STUDIO_FEATURE_MCP = "studio_mcp"
KUBERNETES_SAFETY_SKILL = "kubernetes-safety"


def user_has_studio_feature(user, feature: str) -> bool:
    return feature_allowed_for_user(user, feature)


def owned_kubernetes_mcp_server(user) -> MCPServerPool | None:
    if not user_has_studio_feature(user, STUDIO_FEATURE_MCP):
        return None
    matches = []
    for mcp in _mcp_read_queryset_for_user(user):
        if mcp.owner_id != getattr(user, "id", None):
            continue
        haystack = " ".join(
            [
                str(mcp.name or ""),
                str(mcp.description or ""),
                str(mcp.transport or ""),
                str(mcp.command or ""),
                str(mcp.args or ""),
                str(mcp.url or ""),
            ]
        ).lower()
        if any(term in haystack for term in ("kubernetes", "k8s", "kubectl")):
            matches.append(mcp)
    healthy = [mcp for mcp in matches if mcp.last_test_ok is not False]
    return (healthy or matches or [None])[0]


def kubernetes_safety_skill_ready() -> bool:
    try:
        skill = get_skill(KUBERNETES_SAFETY_SKILL)
    except SkillNotFoundError:
        return False
    return bool(skill.runtime_policy)
