"""
Safety helpers for tool execution.

Public API
----------
- ``is_dangerous_command(cmd) -> bool``: backward-compatible boolean gate used
  by SSH tools, agent engines and terminal AI.
- ``evaluate_command_safety(cmd) -> CommandRisk``: richer verdict with
  matched categories and pattern labels for UI/logging/policy layers.

The pattern catalogue is categorised to enable policy-level decisions
(e.g. "require confirm for destructive_fs, block remote_exec entirely").
Adding a new pattern only requires appending to ``_DANGEROUS_PATTERNS``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Risk categories
# ---------------------------------------------------------------------------

CATEGORY_DESTRUCTIVE_FS = "destructive_fs"
CATEGORY_DESTRUCTIVE_PROC = "destructive_proc"
CATEGORY_DESTRUCTIVE_NETWORK = "destructive_network"
CATEGORY_REMOTE_EXEC = "remote_exec"
CATEGORY_PRIVILEGE_ESCALATION = "privilege_escalation"
CATEGORY_CREDENTIAL = "credential"
CATEGORY_SYSTEM_CONTROL = "system_control"
CATEGORY_DISK = "disk"
CATEGORY_SECURITY_DISABLE = "security_disable"

# ---------------------------------------------------------------------------
# Pattern catalogue: (label, category, compiled regex)
# Patterns are checked with re.IGNORECASE so that "RM -RF /" is caught too.
# ---------------------------------------------------------------------------

_P = lambda pattern: re.compile(pattern, re.IGNORECASE)  # noqa: E731

_DANGEROUS_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    # ── destructive filesystem ────────────────────────────────────────────
    ("rm_recursive_force", CATEGORY_DESTRUCTIVE_FS, _P(r"\brm\s+(?:-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r|-rf|-fr)\b")),
    ("rm_recursive", CATEGORY_DESTRUCTIVE_FS, _P(r"\brm\s+(?:-[a-z]*r|-r)\b")),
    ("rm_root", CATEGORY_DESTRUCTIVE_FS, _P(r"\brm\s+(?:-[a-z]+\s+)?/\s*(?:\*|$)")),
    ("find_delete", CATEGORY_DESTRUCTIVE_FS, _P(r"\bfind\s+[^|]*?-delete\b")),
    ("find_exec_rm", CATEGORY_DESTRUCTIVE_FS, _P(r"\bfind\s+[^|]*?-exec\s+rm\b")),
    ("truncate_zero", CATEGORY_DESTRUCTIVE_FS, _P(r"\btruncate\s+-s\s*0?\b")),
    ("shred", CATEGORY_DESTRUCTIVE_FS, _P(r"\bshred\s+(?:-[a-z]+\s+)*(?:/|\w)")),
    ("chmod_recursive_world", CATEGORY_DESTRUCTIVE_FS, _P(r"\bchmod\s+(?:-R\s+)?[0-7]*7[0-7]*7\s+(?:-R\s+)?(?:/|\.)")),
    ("chown_recursive_root", CATEGORY_DESTRUCTIVE_FS, _P(r"\bchown\s+(?:-R\s+)?\S+\s+/(?:\s|$)")),
    (
        "redirect_critical_file",
        CATEGORY_DESTRUCTIVE_FS,
        _P(r">\s*/etc/(?:passwd|shadow|sudoers|fstab|hosts|resolv\.conf|crontab)\b"),
    ),
    ("append_critical_file", CATEGORY_DESTRUCTIVE_FS, _P(r">>\s*/etc/(?:passwd|shadow|sudoers|fstab|hosts|crontab)\b")),
    # ── disk / partition operations ───────────────────────────────────────
    ("mkfs", CATEGORY_DISK, _P(r"\bmkfs(?:\.\w+)?\b")),
    ("dd_write", CATEGORY_DISK, _P(r"\bdd\s+[^|]*?\b(?:if=|of=/dev/)")),
    ("fdisk", CATEGORY_DISK, _P(r"\bfdisk\s+/dev/")),
    ("parted", CATEGORY_DISK, _P(r"\bparted\s+(?:-\w+\s+)*/dev/")),
    ("wipefs", CATEGORY_DISK, _P(r"\bwipefs\s+(?:-[a-z]+\s+)*/dev/")),
    ("blkdiscard", CATEGORY_DISK, _P(r"\bblkdiscard\s+/dev/")),
    # ── destructive process control ───────────────────────────────────────
    ("kill_pid1", CATEGORY_DESTRUCTIVE_PROC, _P(r"\bkill\s+(?:-(?:9|KILL|SIGKILL)\s+)?1\b")),
    ("pkill_init", CATEGORY_DESTRUCTIVE_PROC, _P(r"\b(?:pkill|killall)\s+(?:-\w+\s+)*(?:init|systemd)\b")),
    ("service_stop", CATEGORY_DESTRUCTIVE_PROC, _P(r"\bservice\s+\S+\s+stop\b")),
    ("systemctl_stop", CATEGORY_DESTRUCTIVE_PROC, _P(r"\bsystemctl\s+(?:stop|disable|mask|poweroff|halt|reboot)\b")),
    # ── system control (shutdown/reboot) ──────────────────────────────────
    ("shutdown", CATEGORY_SYSTEM_CONTROL, _P(r"\bshutdown\b")),
    ("reboot", CATEGORY_SYSTEM_CONTROL, _P(r"\breboot\b")),
    ("halt", CATEGORY_SYSTEM_CONTROL, _P(r"\bhalt\b")),
    ("poweroff", CATEGORY_SYSTEM_CONTROL, _P(r"\bpoweroff\b")),
    ("init_runlevel", CATEGORY_SYSTEM_CONTROL, _P(r"\binit\s+[016]\b")),
    ("telinit", CATEGORY_SYSTEM_CONTROL, _P(r"\btelinit\s+[016]\b")),
    # ── destructive network / firewall ────────────────────────────────────
    ("iptables_flush", CATEGORY_DESTRUCTIVE_NETWORK, _P(r"\biptables\s+(?:-[tFX]\s*)+")),
    ("iptables_drop_all", CATEGORY_DESTRUCTIVE_NETWORK, _P(r"\biptables\s+-P\s+(?:INPUT|FORWARD|OUTPUT)\s+DROP\b")),
    ("ip6tables_flush", CATEGORY_DESTRUCTIVE_NETWORK, _P(r"\bip6?tables\s+-F\b")),
    ("nft_flush", CATEGORY_DESTRUCTIVE_NETWORK, _P(r"\bnft\s+flush\b")),
    ("ufw_reset", CATEGORY_DESTRUCTIVE_NETWORK, _P(r"\bufw\s+(?:reset|--force\s+reset)\b")),
    # ── remote execution / arbitrary download-and-exec ────────────────────
    ("curl_pipe_shell", CATEGORY_REMOTE_EXEC, _P(r"\bcurl\s+[^|]*\|\s*(?:sh|bash|zsh|ash|dash|ksh)\b")),
    ("wget_pipe_shell", CATEGORY_REMOTE_EXEC, _P(r"\bwget\s+[^|]*\|\s*(?:sh|bash|zsh|ash|dash|ksh)\b")),
    ("fetch_pipe_shell", CATEGORY_REMOTE_EXEC, _P(r"\bfetch\s+[^|]*\|\s*(?:sh|bash)\b")),
    ("eval_subshell", CATEGORY_REMOTE_EXEC, _P(r"\beval\s+[\"'$`(]")),
    ("base64_pipe_shell", CATEGORY_REMOTE_EXEC, _P(r"\bbase64\s+(?:-d|--decode)\b[^|]*\|\s*(?:sh|bash)\b")),
    # ── privilege escalation / credential changes ─────────────────────────
    ("userdel", CATEGORY_PRIVILEGE_ESCALATION, _P(r"\buserdel\b")),
    ("usermod_lock", CATEGORY_PRIVILEGE_ESCALATION, _P(r"\busermod\s+(?:-[a-z]+\s+)*(?:-L|-U|--lock|--unlock)\b")),
    ("passwd_change", CATEGORY_CREDENTIAL, _P(r"\bpasswd\s+(?:\w+|-d|--delete)\b")),
    ("visudo", CATEGORY_PRIVILEGE_ESCALATION, _P(r"\bvisudo\b")),
    ("sudo_install", CATEGORY_PRIVILEGE_ESCALATION, _P(r"\b(?:echo|tee)\s+[^|]*>\s*/etc/sudoers(?:\.d/)?\b")),
    ("docker_privileged", CATEGORY_PRIVILEGE_ESCALATION, _P(r"\bdocker\s+run\b[^|]*--privileged\b")),
    # ── security disable ──────────────────────────────────────────────────
    ("setenforce_disable", CATEGORY_SECURITY_DISABLE, _P(r"\bsetenforce\s+0\b")),
    ("selinux_disable", CATEGORY_SECURITY_DISABLE, _P(r"\bsed\b[^|]*permissive[^|]*/etc/selinux")),
    ("apparmor_teardown", CATEGORY_SECURITY_DISABLE, _P(r"\baa-teardown\b|\bapparmor_parser\s+-R\b")),
    ("ufw_disable", CATEGORY_SECURITY_DISABLE, _P(r"\bufw\s+disable\b")),
    ("firewalld_stop", CATEGORY_SECURITY_DISABLE, _P(r"\bsystemctl\s+(?:stop|disable)\s+firewalld\b")),
)

# Legacy list kept exposed for callers that introspect dangerous patterns.
_DANGEROUS_CMD_PATTERNS: list[str] = [pat.pattern for _, _, pat in _DANGEROUS_PATTERNS]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandRisk:
    """Verdict produced by :func:`evaluate_command_safety`.

    ``level``:
        - ``"safe"`` — no dangerous pattern matched
        - ``"dangerous"`` — at least one match; orchestrator must confirm
    ``categories``: deduplicated tuple of risk category labels (e.g.
        ``("destructive_fs", "system_control")``) — meant for policy layers
        and audit logs.
    ``matched_patterns``: labels of matched pattern entries, preserving order.
    ``reasons``: human-readable per-match explanations, one per matched
        pattern, suitable for UI tooltips and activity-log metadata.
    """

    level: str
    categories: tuple[str, ...]
    matched_patterns: tuple[str, ...]
    reasons: tuple[str, ...] = ()

    @property
    def is_dangerous(self) -> bool:
        return self.level != "safe"

    def summary(self) -> str:
        """Short one-line human-readable summary for logs / tooltips."""
        if not self.is_dangerous:
            return "safe"
        cats = ", ".join(self.categories)
        return f"{self.level} ({cats})"


# Human-readable descriptions for each pattern label; surfaced via
# ``CommandRisk.reasons``. Keep phrases compact — they end up in UI tooltips.
_PATTERN_REASONS: dict[str, str] = {
    "rm_recursive_force": "рекурсивное удаление с force (rm -rf)",
    "rm_recursive": "рекурсивное удаление (rm -r)",
    "rm_root": "удаление в корне (/)",
    "find_delete": "find с -delete (массовое удаление)",
    "find_exec_rm": "find с -exec rm (массовое удаление)",
    "truncate_zero": "обнуление файлов (truncate -s 0)",
    "shred": "безвозвратная затирка данных (shred)",
    "chmod_recursive_world": "рекурсивная раздача прав 777",
    "chown_recursive_root": "рекурсивный chown в корне",
    "redirect_critical_file": "перезапись критичного /etc/ файла",
    "append_critical_file": "дозапись в критичный /etc/ файл",
    "mkfs": "форматирование ФС (mkfs)",
    "dd_write": "запись через dd в устройство",
    "fdisk": "редактирование таблицы разделов (fdisk)",
    "parted": "редактирование таблицы разделов (parted)",
    "wipefs": "очистка подписей ФС (wipefs)",
    "blkdiscard": "blkdiscard на блочном устройстве",
    "kill_pid1": "kill PID 1 (init/systemd)",
    "pkill_init": "pkill init/systemd",
    "service_stop": "остановка сервиса (service stop)",
    "systemctl_stop": "остановка/отключение сервиса (systemctl)",
    "shutdown": "выключение (shutdown)",
    "reboot": "перезагрузка (reboot)",
    "halt": "остановка системы (halt)",
    "poweroff": "выключение питания (poweroff)",
    "init_runlevel": "смена runlevel (init 0/1/6)",
    "telinit": "смена runlevel (telinit)",
    "iptables_flush": "сброс правил iptables (-F / -X)",
    "iptables_drop_all": "iptables -P ... DROP — блокировка трафика",
    "ip6tables_flush": "сброс ip6tables",
    "nft_flush": "nft flush — сброс правил nftables",
    "ufw_reset": "ufw reset — сброс firewall",
    "curl_pipe_shell": "curl | sh — удалённое исполнение кода",
    "wget_pipe_shell": "wget | sh — удалённое исполнение кода",
    "fetch_pipe_shell": "fetch | sh — удалённое исполнение кода",
    "eval_subshell": "eval с подстановкой — произвольный код",
    "base64_pipe_shell": "base64 -d | sh — обфусцированное исполнение",
    "userdel": "удаление пользователя (userdel)",
    "usermod_lock": "блокировка/разблокировка аккаунта (usermod -L/-U)",
    "passwd_change": "смена/удаление пароля (passwd)",
    "visudo": "редактирование sudoers (visudo)",
    "sudo_install": "запись в /etc/sudoers.d/",
    "docker_privileged": "docker run --privileged — выход из изоляции",
    "setenforce_disable": "отключение SELinux (setenforce 0)",
    "selinux_disable": "перевод SELinux в permissive",
    "apparmor_teardown": "снятие AppArmor-профилей",
    "ufw_disable": "отключение UFW firewall",
    "firewalld_stop": "остановка firewalld",
}


_SAFE = CommandRisk(level="safe", categories=(), matched_patterns=(), reasons=())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_command_safety(command: str) -> CommandRisk:
    """Evaluate a shell command against the dangerous-pattern catalogue."""
    if not command:
        return _SAFE
    text = str(command)
    matched: list[str] = []
    reasons: list[str] = []
    categories: list[str] = []
    seen_categories: set[str] = set()
    for label, category, regex in _DANGEROUS_PATTERNS:
        if regex.search(text):
            matched.append(label)
            reasons.append(_PATTERN_REASONS.get(label, label))
            if category not in seen_categories:
                seen_categories.add(category)
                categories.append(category)
    if not matched:
        return _SAFE
    return CommandRisk(
        level="dangerous",
        categories=tuple(categories),
        matched_patterns=tuple(matched),
        reasons=tuple(reasons),
    )


def is_dangerous_command(command: str) -> bool:
    """Backward-compatible boolean gate.

    Returns ``True`` if the command matches any pattern in the catalogue.
    Callers that need categories/labels should use
    :func:`evaluate_command_safety` instead.
    """
    return evaluate_command_safety(command).is_dangerous
