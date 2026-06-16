from __future__ import annotations

import re
from dataclasses import dataclass

from app.agent_kernel.domain.specs import PermissionDecision, ToolSpec
from app.agent_kernel.sudo_policy import (
    SUDO_POLICY_DISABLED,
    evaluate_sudo_command,
    normalize_sudo_policy,
)
from app.execution_policy import build_execution_policy_audit_metadata
from app.agent_kernel.permissions.modes import MODE_AUTO_GUARDED, MODE_PLAN, MODE_SAFE, MUTATION_SANDBOX
from app.tools.safety import evaluate_command_safety

_MUTATING_PATTERNS: tuple[tuple[re.Pattern[str], str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        re.compile(r"\bdocker\s+compose\s+(up|down|restart|pull)\b", re.IGNORECASE),
        "docker_mutation",
        ("docker_preflight",),
        ("docker_verification",),
    ),
    (
        re.compile(r"\bsystemctl\s+(restart|reload|start|stop)\b", re.IGNORECASE),
        "service_mutation",
        ("service_preflight",),
        ("service_verification",),
    ),
    (
        re.compile(r"\bnginx\s+(-s\s+reload|reload)\b", re.IGNORECASE),
        "nginx_mutation",
        ("nginx_preflight",),
        ("nginx_verification",),
    ),
    (
        re.compile(r"\b(apt|apt-get|yum|dnf)\s+(install|upgrade|remove)\b", re.IGNORECASE),
        "package_mutation",
        ("system_preflight",),
        ("system_verification",),
    ),
    (
        re.compile(r"(?:^|\s)(?:tee|sed\s+-i|cp|mv|chmod|chown)\b", re.IGNORECASE),
        "config_mutation",
        ("config_preflight",),
        ("config_verification",),
    ),
)

_PREFLIGHT_MARKERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bdocker\s+compose\s+config\b|\bdocker\s+ps\b", re.IGNORECASE), "docker_preflight"),
    (re.compile(r"\bsystemctl\s+status\b|\bservice\s+\S+\s+status\b", re.IGNORECASE), "service_preflight"),
    (re.compile(r"\bnginx\s+-t\b", re.IGNORECASE), "nginx_preflight"),
    (re.compile(r"\b(df\s+-h|free\s+-m|uptime)\b", re.IGNORECASE), "system_preflight"),
    (re.compile(r"\b(ls|cat|grep|find)\b", re.IGNORECASE), "config_preflight"),
)

_VERIFICATION_MARKERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bdocker\s+ps\b|\bdocker\s+compose\s+ps\b|\bcurl\b", re.IGNORECASE), "docker_verification"),
    (re.compile(r"\bsystemctl\s+status\b|\bjournalctl\b|\bcurl\b", re.IGNORECASE), "service_verification"),
    (re.compile(r"\bnginx\s+-t\b|\bcurl\b", re.IGNORECASE), "nginx_verification"),
    (re.compile(r"\b(df\s+-h|free\s+-m|uptime)\b|\bcurl\b", re.IGNORECASE), "system_verification"),
    (re.compile(r"\b(cat|grep|ls|curl)\b", re.IGNORECASE), "config_verification"),
)

_READ_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(ls|cat|grep|find|head|tail|less|more|pwd|whoami|env|printenv|ps|top|ss|netstat|ip\b|hostname)\b", re.IGNORECASE),
    re.compile(r"\b(df\s+-h|free\s+-m|uptime|du\s+-sh)\b", re.IGNORECASE),
    re.compile(r"\bsystemctl\s+status\b|\bservice\s+\S+\s+status\b|\bjournalctl\b", re.IGNORECASE),
    re.compile(r"\bdocker\s+(ps|inspect|logs)\b|\bdocker\s+compose\s+(ps|config)\b", re.IGNORECASE),
    re.compile(r"\bnginx\s+-t\b", re.IGNORECASE),
    re.compile(r"\bcurl\b", re.IGNORECASE),
)

_UNKNOWN_MUTATION_PATTERN = re.compile(
    r"\b("
    r"start|stop|restart|reload|enable|disable|mask|unmask|"
    r"install|upgrade|remove|purge|"
    r"mkdir|touch|rm|mv|cp|chmod|chown|useradd|userdel|groupadd|groupdel|"
    r"iptables|ufw|firewall-cmd|kubectl|helm|tee"
    r")\b|>>?|sed\s+-i",
    re.IGNORECASE,
)

_SAFE_ADMIN_TOOL_NAME = re.compile(r"(get|list|read|search|describe|status|current|whoami|test|preview)", re.IGNORECASE)


@dataclass
class PermissionEngine:
    mode: str = MODE_SAFE
    sudo_policy: str = SUDO_POLICY_DISABLED

    def __post_init__(self):
        self.observed_markers: set[str] = set()
        self.pending_verifications: set[str] = set()
        self.sudo_policy = normalize_sudo_policy(self.sudo_policy)

    def evaluate(self, spec: ToolSpec, args: dict) -> PermissionDecision:
        command = str(args.get("command") or "")
        command_risk = evaluate_command_safety(command)

        if command and command_risk.is_dangerous:
            return self._decision(
                spec,
                args,
                allowed=False,
                reason="Команда классифицирована как опасная и заблокирована политикой безопасности.",
                requires_approval=True,
                risk_categories=command_risk.categories,
                matched_patterns=command_risk.matched_patterns,
            )

        if spec.name in {"ssh_execute", "server_execute"}:
            sudo_decision = evaluate_sudo_command(command, self.sudo_policy)
            if not sudo_decision.allowed:
                return self._decision(
                    spec,
                    args,
                    allowed=False,
                    reason=sudo_decision.reason,
                    requires_approval=sudo_decision.requires_approval,
                    risk_categories=("privilege_escalation",),
                    matched_patterns=sudo_decision.matched_patterns,
                    extra_audit={"sudo_policy": sudo_decision.policy},
                )

        if self.mode == MODE_PLAN and (spec.mutates_state or spec.risk in {"write", "admin"} or self._is_mutating_command(command)):
            return self._decision(
                spec,
                args,
                allowed=False,
                reason="PLAN mode: разрешены только исследование, чтение и построение плана.",
                requires_approval=True,
                risk_categories=self._risk_categories(spec, command),
            )

        if spec.name.startswith("mcp_") and self.mode == MODE_SAFE:
            return self._decision(
                spec,
                args,
                allowed=True,
                notes=("MCP вызов разрешен в SAFE mode, но агент должен явно подтвердить цель и последствия.",),
                risk_categories=("mcp_call",),
            )

        if spec.name == "ssh_execute":
            mutation = self._match_mutation(command)
            if mutation:
                _kind, preflights, _verifications = mutation
                missing = [marker for marker in preflights if marker not in self.observed_markers]
                if missing:
                    return self._decision(
                        spec,
                        args,
                        allowed=False,
                        reason="Сначала собери preflight факты перед изменением: " + ", ".join(missing),
                        requires_approval=True,
                        risk_categories=(_kind,),
                    )
                return self._decision(
                    spec,
                    args,
                    allowed=True,
                    sandbox_profile="ops_mutation",
                risk_categories=(_kind,),
                notes=(
                    *self._sudo_notes(command),
                    "После изменения обязательно выполни post-change verification.",
                ),
            )

        if self.mode == MODE_SAFE and spec.risk == "admin":
            return self._decision(
                spec,
                args,
                allowed=False,
                reason="SAFE mode блокирует административные изменения до явного плана.",
                requires_approval=True,
                risk_categories=("admin",),
            )

        if self.mode == MODE_AUTO_GUARDED:
            if spec.risk == "admin" and not _SAFE_ADMIN_TOOL_NAME.search(spec.name):
                return self._decision(
                    spec,
                    args,
                    allowed=False,
                    reason="AUTO_GUARDED блокирует административные операции без явной allowlisted semantics.",
                    requires_approval=True,
                    risk_categories=("admin",),
                )

            if spec.name == "ssh_execute":
                if command and self._is_read_only_command(command):
                    return self._decision(
                        spec,
                        args,
                        allowed=True,
                        sandbox_profile="ops_read",
                        risk_categories=("read_only",),
                        notes=(
                            *self._sudo_notes(command),
                            "Команда классифицирована как read-only и разрешена в AUTO_GUARDED.",
                        ),
                    )

                mutation = self._match_mutation(command)
                if mutation:
                    _kind, preflights, _verifications = mutation
                    missing = [marker for marker in preflights if marker not in self.observed_markers]
                    if missing:
                        return self._decision(
                            spec,
                            args,
                            allowed=False,
                            reason="AUTO_GUARDED требует preflight перед изменением: " + ", ".join(missing),
                            requires_approval=True,
                            risk_categories=(_kind,),
                        )
                    return self._decision(
                        spec,
                        args,
                        allowed=True,
                        sandbox_profile="ops_mutation",
                        risk_categories=(_kind,),
                        notes=(
                            *self._sudo_notes(command),
                            "Изменение разрешено в AUTO_GUARDED после preflight; post-change verification обязательно.",
                        ),
                    )

                if command and _UNKNOWN_MUTATION_PATTERN.search(command):
                    return self._decision(
                        spec,
                        args,
                        allowed=False,
                        reason="AUTO_GUARDED блокирует неклассифицированную потенциально мутирующую команду.",
                        requires_approval=True,
                        risk_categories=("unknown_mutation",),
                    )

        return self._decision(spec, args, allowed=True, notes=self._sudo_notes(command))

    def record_success(self, spec: ToolSpec, args: dict, _result_text: str):
        if spec.name != "ssh_execute":
            return

        command = str(args.get("command") or "")
        if not command:
            return

        for pattern, marker in _PREFLIGHT_MARKERS:
            if pattern.search(command):
                self.observed_markers.add(marker)

        for pattern, marker in _VERIFICATION_MARKERS:
            if pattern.search(command):
                self.observed_markers.add(marker)
                self.pending_verifications.discard(marker)

        mutation = self._match_mutation(command)
        if mutation:
            _kind, _preflights, verifications = mutation
            for marker in verifications:
                self.pending_verifications.add(marker)

    def verification_summary(self) -> str:
        if not self.pending_verifications:
            return "Все обязательные post-change verification markers закрыты."
        return "Остались непроверенные изменения: " + ", ".join(sorted(self.pending_verifications))

    @staticmethod
    def _is_mutating_command(command: str) -> bool:
        return PermissionEngine._match_mutation(command) is not None

    @staticmethod
    def _match_mutation(command: str) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
        for pattern, kind, preflights, verifications in _MUTATING_PATTERNS:
            if pattern.search(command or ""):
                return kind, preflights, verifications
        return None

    @staticmethod
    def _is_read_only_command(command: str) -> bool:
        value = command or ""
        return any(pattern.search(value) for pattern in _READ_ONLY_PATTERNS)

    def _decision(
        self,
        spec: ToolSpec,
        args: dict,
        *,
        allowed: bool,
        sandbox_profile: str | None = None,
        reason: str = "",
        requires_approval: bool = False,
        notes: tuple[str, ...] = (),
        risk_categories: tuple[str, ...] = (),
        matched_patterns: tuple[str, ...] = (),
        extra_audit: dict | None = None,
    ) -> PermissionDecision:
        sandbox = sandbox_profile or MUTATION_SANDBOX.get(self.mode, "ops_read")
        audit_metadata = {
            "execution_policy": build_execution_policy_audit_metadata(
                tool_name=spec.name,
                args=args,
                mode=self.mode,
                allowed=allowed,
                sandbox_profile=sandbox,
                reason=reason,
                requires_approval=requires_approval,
                risk_categories=risk_categories,
                matched_patterns=matched_patterns,
                extra={
                    "tool_category": spec.category,
                    "tool_risk": spec.risk,
                    "mutates_state": spec.mutates_state,
                    "sudo_policy": self.sudo_policy,
                    **(extra_audit or {}),
                },
            )
        }
        return PermissionDecision(
            allowed=allowed,
            mode=self.mode,
            sandbox_profile=sandbox,
            reason=reason,
            requires_approval=requires_approval,
            notes=notes,
            audit_metadata=audit_metadata,
        )

    @staticmethod
    def _risk_categories(spec: ToolSpec, command: str) -> tuple[str, ...]:
        mutation = PermissionEngine._match_mutation(command)
        if mutation:
            return (mutation[0],)
        if spec.mutates_state:
            return ("mutation",)
        if spec.risk in {"write", "admin", "exec"}:
            return (spec.risk,)
        return ()

    def _sudo_notes(self, command: str) -> tuple[str, ...]:
        sudo_decision = evaluate_sudo_command(command, self.sudo_policy)
        return sudo_decision.notes if sudo_decision.allowed else ()
