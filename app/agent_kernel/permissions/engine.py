from __future__ import annotations

import re
from dataclasses import dataclass

from app.agent_kernel.domain.specs import PermissionDecision, ToolSpec
from app.agent_kernel.permissions.modes import MODE_AUTO_GUARDED, MODE_PLAN, MODE_SAFE, MUTATION_SANDBOX
from app.tools.safety import is_dangerous_command

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

    def __post_init__(self):
        self.observed_markers: set[str] = set()
        self.pending_verifications: set[str] = set()

    def evaluate(self, spec: ToolSpec, args: dict) -> PermissionDecision:
        command = str(args.get("command") or "")

        if command and is_dangerous_command(command):
            return PermissionDecision(
                allowed=False,
                mode=self.mode,
                sandbox_profile=MUTATION_SANDBOX.get(self.mode, "ops_read"),
                reason="Команда классифицирована как опасная и заблокирована политикой безопасности.",
            )

        if self.mode == MODE_PLAN and (spec.mutates_state or spec.risk in {"write", "admin"} or self._is_mutating_command(command)):
            return PermissionDecision(
                allowed=False,
                mode=self.mode,
                sandbox_profile=MUTATION_SANDBOX[self.mode],
                reason="PLAN mode: разрешены только исследование, чтение и построение плана.",
            )

        if spec.name.startswith("mcp_") and self.mode == MODE_SAFE:
            return PermissionDecision(
                allowed=True,
                mode=self.mode,
                sandbox_profile=MUTATION_SANDBOX[self.mode],
                notes=("MCP вызов разрешен в SAFE mode, но агент должен явно подтвердить цель и последствия.",),
            )

        if spec.name == "ssh_execute":
            mutation = self._match_mutation(command)
            if mutation:
                _kind, preflights, _verifications = mutation
                missing = [marker for marker in preflights if marker not in self.observed_markers]
                if missing:
                    return PermissionDecision(
                        allowed=False,
                        mode=self.mode,
                        sandbox_profile=MUTATION_SANDBOX[self.mode],
                        reason="Сначала собери preflight факты перед изменением: " + ", ".join(missing),
                    )
                return PermissionDecision(
                    allowed=True,
                    mode=self.mode,
                    sandbox_profile="ops_mutation",
                    notes=("После изменения обязательно выполни post-change verification.",),
                )

        if self.mode == MODE_SAFE and spec.risk == "admin":
            return PermissionDecision(
                allowed=False,
                mode=self.mode,
                sandbox_profile=MUTATION_SANDBOX[self.mode],
                reason="SAFE mode блокирует административные изменения до явного плана.",
            )

        if self.mode == MODE_AUTO_GUARDED:
            if spec.risk == "admin" and not _SAFE_ADMIN_TOOL_NAME.search(spec.name):
                return PermissionDecision(
                    allowed=False,
                    mode=self.mode,
                    sandbox_profile=MUTATION_SANDBOX[self.mode],
                    reason="AUTO_GUARDED блокирует административные операции без явной allowlisted semantics.",
                )

            if spec.name == "ssh_execute":
                if command and self._is_read_only_command(command):
                    return PermissionDecision(
                        allowed=True,
                        mode=self.mode,
                        sandbox_profile="ops_read",
                        notes=("Команда классифицирована как read-only и разрешена в AUTO_GUARDED.",),
                    )

                mutation = self._match_mutation(command)
                if mutation:
                    _kind, preflights, _verifications = mutation
                    missing = [marker for marker in preflights if marker not in self.observed_markers]
                    if missing:
                        return PermissionDecision(
                            allowed=False,
                            mode=self.mode,
                            sandbox_profile=MUTATION_SANDBOX[self.mode],
                            reason="AUTO_GUARDED требует preflight перед изменением: " + ", ".join(missing),
                        )
                    return PermissionDecision(
                        allowed=True,
                        mode=self.mode,
                        sandbox_profile="ops_mutation",
                        notes=("Изменение разрешено в AUTO_GUARDED после preflight; post-change verification обязательно.",),
                    )

                if command and _UNKNOWN_MUTATION_PATTERN.search(command):
                    return PermissionDecision(
                        allowed=False,
                        mode=self.mode,
                        sandbox_profile=MUTATION_SANDBOX[self.mode],
                        reason="AUTO_GUARDED блокирует неклассифицированную потенциально мутирующую команду.",
                    )

        sandbox = MUTATION_SANDBOX.get(self.mode, "ops_read")
        return PermissionDecision(allowed=True, mode=self.mode, sandbox_profile=sandbox)

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
