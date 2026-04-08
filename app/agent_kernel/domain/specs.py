from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ToolCategory = Literal["ssh", "file", "docker", "service", "nginx", "keycloak", "monitoring", "mcp", "general"]
ToolRisk = Literal["read", "write", "exec", "network", "admin"]
PermissionMode = Literal["PLAN", "SAFE", "ASSISTED", "AUTONOMOUS", "AUTO_GUARDED"]
AgentPhase = Literal[
    "planning",
    "awaiting_policy",
    "awaiting_approval",
    "executing",
    "verifying",
    "waiting_user",
    "paused",
    "completed",
    "failed",
    "stopped",
]
ToolCategoryName = Literal["ssh", "file", "docker", "service", "nginx", "keycloak", "monitoring", "mcp", "general"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    category: ToolCategory
    risk: ToolRisk
    description: str
    input_schema: dict[str, Any]
    mutates_state: bool = False
    requires_preflight: tuple[str, ...] = ()
    requires_verification: bool = False
    output_compactor: str | None = None
    runner: str = "agent"

    def prompt_line(self) -> str:
        traits = [self.category, self.risk]
        if self.mutates_state:
            traits.append("mutates")
        if self.requires_verification:
            traits.append("verify")
        return f"- {self.name}: {self.description} [{' / '.join(traits)}]"


@dataclass(frozen=True)
class MemoryRecord:
    domain: str
    title: str
    content: str
    confidence: float = 0.8
    freshness_score: float = 1.0
    last_verified_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ServerMemoryCard:
    server_id: int
    identity: dict[str, Any]
    topology_tags: list[str] = field(default_factory=list)
    stable_facts: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    known_risks: list[str] = field(default_factory=list)
    recent_incidents: list[str] = field(default_factory=list)
    operational_playbooks: list[str] = field(default_factory=list)
    verified_at: str | None = None
    confidence: float = 0.8
    records: list[MemoryRecord] = field(default_factory=list)

    def as_prompt_block(self, *, max_records: int = 6) -> str:
        parts = [
            f"Сервер: {self.identity.get('name', self.server_id)} ({self.identity.get('host', 'unknown')})",
            f"Тип: {self.identity.get('server_type', 'ssh')}; пользователь: {self.identity.get('username', 'unknown')}",
        ]
        if self.identity.get("group"):
            parts.append(f"Группа: {self.identity['group']}")
        if self.topology_tags:
            parts.append("Теги/топология: " + ", ".join(self.topology_tags[:8]))
        if self.stable_facts:
            parts.append("Стабильные факты:\n" + "\n".join(f"- {item}" for item in self.stable_facts[:6]))
        if self.known_risks:
            parts.append("Известные риски:\n" + "\n".join(f"- {item}" for item in self.known_risks[:5]))
        if self.recent_incidents:
            parts.append("Недавние инциденты:\n" + "\n".join(f"- {item}" for item in self.recent_incidents[:4]))
        if self.recent_changes:
            parts.append("Недавние изменения:\n" + "\n".join(f"- {item}" for item in self.recent_changes[:4]))
        if self.operational_playbooks:
            parts.append("Operational playbooks:\n" + "\n".join(f"- {item}" for item in self.operational_playbooks[:4]))
        if self.records:
            parts.append(
                "Релевантная память:\n"
                + "\n".join(
                    f"- [{record.domain}] {record.title}: {record.content}"
                    for record in self.records[:max_records]
                )
            )
        if self.verified_at:
            parts.append(f"Последняя верификация памяти: {self.verified_at}")
        parts.append(f"Уверенность в памяти: {self.confidence:.2f}")
        return "\n".join(parts)


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    mode: PermissionMode
    sandbox_profile: str
    reason: str = ""
    requires_approval: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunEvent:
    event_type: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentState:
    run_id: str
    session_id: str
    objective: str
    role: str
    phase: AgentPhase
    permission_mode: PermissionMode
    target_servers: list[int]
    active_hypotheses: list[str] = field(default_factory=list)
    recent_summaries: list[str] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    current_plan: list[dict[str, Any]] = field(default_factory=list)
    token_budget_remaining: int = 0
    checkpoint_id: str | None = None


@dataclass(frozen=True)
class SubagentSpec:
    role: str
    title: str
    permission_mode: PermissionMode
    tool_names: tuple[str, ...] = ()
    allowed_categories: tuple[ToolCategoryName, ...] = ()
    max_iterations: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
