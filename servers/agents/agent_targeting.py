"""Server-scope rules shared by the Agents API and launch path."""

from __future__ import annotations

from app.agent_kernel import skill_provider_registry

SERVER_DEPENDENT_TOOLS = {
    "open_connection",
    "close_connection",
    "ssh_execute",
    "read_console",
    "wait_for_output",
}


def server_requirement_reasons(*, mode: str, commands, tools_config, sudo_policy: str, skill_slugs) -> list[str]:
    reasons: list[str] = []
    if mode == "mini" or any(str(command).strip() for command in (commands or [])):
        reasons.append("commands")
    if sudo_policy != "disabled":
        reasons.append("sudo")
    if any(bool((tools_config or {}).get(name)) for name in SERVER_DEPENDENT_TOOLS):
        reasons.append("server_tools")
    skills, _errors = skill_provider_registry.resolve_skills(list(skill_slugs or []))
    for skill in skills:
        detail = skill.to_detail_dict() if hasattr(skill, "to_detail_dict") else {}
        if SERVER_DEPENDENT_TOOLS.intersection(detail.get("recommended_tools") or []):
            reasons.append("server_skills")
            break
    return reasons


def agent_server_requirement_reasons(agent) -> list[str]:
    return server_requirement_reasons(
        mode=agent.mode,
        commands=agent.commands,
        tools_config=agent.tools_config,
        sudo_policy=agent.sudo_policy,
        skill_slugs=agent.skill_slugs,
    )
