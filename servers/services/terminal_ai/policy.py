"""
Terminal AI command policy layer (F2-6 + F2-8).

Single source of truth for "can this command run / needs confirm / what's
the execution mode?". Replaces the scattered inline logic in the SSH
consumer (``_compute_confirm_reason`` + ad-hoc ask-mode checks + future
exec-mode decisions).

Public API:
- :class:`CommandPolicy` — frozen verdict for a single command.
- :func:`match_patterns` — re: / token-sequence / substring pattern matcher.
- :func:`decide_command_policy` — combines forbidden, allowlist, dangerous
  and chat-mode rules into one verdict.
- :func:`choose_exec_mode` (F2-8) — hybrid executor hint: ``"pty"`` for
  interactive/stateful/write-heavy commands, ``"direct"`` for safe read-only.

All functions are pure Python — no Django, no WebSocket, no SSH — so they
are trivially unit-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.tools.safety import CommandRisk, evaluate_command_safety


@dataclass(frozen=True)
class CommandPolicy:
    """Verdict for a single candidate command.

    Attributes:
        allowed: ``False`` iff ``reason in {"forbidden", "outside_allowlist"}``.
        requires_confirm: ``True`` iff the client must display a confirm prompt.
        reason: Canonical short reason code — one of
            ``"forbidden" | "outside_allowlist" | "dangerous" | "ask_mode" | ""``.
        risk: :class:`CommandRisk` verdict from :mod:`app.tools.safety`.
        exec_mode: ``"pty"`` (default, stateful shell) or ``"direct"``
            (stateless one-off exec). F2-8 — for now consumed as a hint only.
    """

    allowed: bool
    requires_confirm: bool
    reason: str
    risk: CommandRisk
    exec_mode: str = "pty"
    # F2-5: human-readable reasons from safety evaluator, for UI tooltips.
    risk_categories: tuple[str, ...] = field(default_factory=tuple)
    risk_reasons: tuple[str, ...] = field(default_factory=tuple)


# Compiled identifier-tokenizer used by match_patterns. Shared to avoid
# re-compiling on every call.
_TOKEN_RE = re.compile(r"[a-z0-9_./:-]+")


def match_patterns(command: str, patterns: list[str] | None) -> bool:
    """Return True if the command matches any pattern in ``patterns``.

    Pattern DSL:
    - ``"re:<regex>"``: case-insensitive regex search; malformed regex is
      skipped silently (never blocks the user).
    - bare string: tokenized on ``[a-z0-9_./:-]+`` and compared as a
      contiguous token sub-sequence; also falls back to case-insensitive
      substring match.

    This is the *exact* same matching algorithm that lived inline in
    ``SSHTerminalConsumer._matches_patterns`` — extracted verbatim so
    existing forbidden/allowlist patterns keep behaving identically.
    """
    cmd_l = (command or "").lower()
    for raw in patterns or []:
        pat = str(raw or "").strip()
        if not pat:
            continue
        pl = pat.lower()
        if pl.startswith("re:"):
            expr = pat[3:].strip()
            if not expr:
                continue
            try:
                if re.search(expr, command, flags=re.IGNORECASE):
                    return True
            except re.error:
                # Malformed user regex — ignore, don't block.
                continue
            continue

        pat_tokens = _TOKEN_RE.findall(pl)
        cmd_tokens = _TOKEN_RE.findall(cmd_l)
        if pat_tokens and cmd_tokens:
            plen = len(pat_tokens)
            for i in range(0, len(cmd_tokens) - plen + 1):
                if cmd_tokens[i : i + plen] == pat_tokens:
                    return True

        if pl in cmd_l:
            return True
    return False


# ---------------------------------------------------------------------------
# F2-8: hybrid executor mode selection
# ---------------------------------------------------------------------------

# Commands that are known-safe, read-only, and short-running are eligible
# for ``exec_mode="direct"`` — they can be executed via a non-PTY one-off
# ``asyncssh.SSHClientConnection.run()`` without touching the interactive
# shell state. Anything matching ``_PTY_REQUIRED_RE`` must stay in PTY so
# it inherits the user's shell cwd / env / aliases.
_DIRECT_SAFE_PREFIXES: tuple[str, ...] = (
    "ls",
    "pwd",
    "whoami",
    "hostname",
    "uptime",
    "uname",
    "date",
    "df",
    "du",
    "free",
    "cat /etc/os-release",
    "cat /proc/cpuinfo",
    "cat /proc/meminfo",
    "id",
    "groups",
    "which",
    "command -v",
    "ps",
    "ss",
    "netstat",
    "ip a",
    "ip addr",
    "ip route",
    "ip r",
    "systemctl status",
    "systemctl is-active",
    "journalctl -n",
    "docker ps",
    "docker images",
    "docker info",
    "docker version",
    "kubectl get",
    "git status",
    "git log",
    "git branch",
    "curl -I",
    "curl --head",
    "nproc",
    "arch",
    "lsb_release",
)

# Commands that MUST stay in PTY: interactive editors/pagers, sudo prompts,
# commands that depend on shell state (cd-less navigation), long-running
# streams (tail -f, journalctl -f, watch, top, htop), anything touching
# stdin interactively.
_PTY_REQUIRED_RE = re.compile(
    r"""
    (^|[\s;&|`$()])                    # command boundary
    (
        sudo(?!\s+-n)                  # sudo (except non-interactive -n)
        | su\b
        | ssh\b
        | nano | vim | vi | emacs
        | less | more | man
        | top | htop | btop | atop
        | watch | tail\s+-[fF] | journalctl\s+[^|]*-f\b
        | mysql\b(?!\s+-e) | psql\b(?!\s+-c)
        | python3?\s*$ | python3?\s+(?:-i\b|-c\s*$)
        | node\s*$ | irb\b | ipython\b
        | docker\s+exec\s+-.*it | docker\s+run\s+-.*it
        | kubectl\s+exec\b.*-.*t
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def choose_exec_mode(command: str, risk: CommandRisk | None = None) -> str:
    """Return ``"direct"`` or ``"pty"`` for the given command (F2-8).

    Policy:
    - Dangerous commands → ``"pty"`` (safer: visible live output, interruptible).
    - Commands matching :data:`_PTY_REQUIRED_RE` → ``"pty"``.
    - Commands whose leading word/phrase matches :data:`_DIRECT_SAFE_PREFIXES`
      and contain no shell control metacharacters → ``"direct"``.
    - Everything else → ``"pty"`` (conservative default).

    The v1 implementation uses this as an *informational hint* — the
    consumer still executes everything through the PTY. A future change
    may route ``exec_mode == "direct"`` through a separate non-PTY path.
    """
    text = (command or "").strip()
    if not text:
        return "pty"

    verdict = risk if risk is not None else evaluate_command_safety(text)
    if verdict.is_dangerous:
        return "pty"

    if _PTY_REQUIRED_RE.search(text):
        return "pty"

    # Reject commands with shell metacharacters beyond basic argv —
    # pipes / redirects / backgrounding need a real shell.
    if any(ch in text for ch in ("|", "&&", "||", ";", "`", "$(", ">", "<")):
        return "pty"

    lowered = text.lower()
    for prefix in _DIRECT_SAFE_PREFIXES:
        if lowered == prefix or lowered.startswith(prefix + " ") or lowered.startswith(prefix + "\t"):
            return "direct"

    return "pty"


# ---------------------------------------------------------------------------
# Top-level policy decision
# ---------------------------------------------------------------------------


def decide_command_policy(
    command: str,
    *,
    forbidden_patterns: list[str] | None = None,
    allowlist_patterns: list[str] | None = None,
    chat_mode: str = "agent",
    confirm_dangerous_commands: bool = True,
) -> CommandPolicy:
    """Decide whether a command is allowed / needs confirm / which exec mode.

    Precedence (high → low):
    1. ``forbidden_patterns`` match → ``reason="forbidden"``, not allowed.
    2. ``allowlist_patterns`` provided and command does not match →
       ``reason="outside_allowlist"``, not allowed.
    3. ``confirm_dangerous_commands`` and :func:`evaluate_command_safety`
       returned dangerous → ``reason="dangerous"``, requires confirm.
    4. ``chat_mode == "ask"`` on any non-blocked command → ``reason="ask_mode"``,
       requires confirm.
    5. Otherwise auto-run.

    Empty command returns an "allowed, no confirm, no reason" verdict.
    """
    text = (command or "").strip()
    risk = evaluate_command_safety(text)

    def _verdict(
        *,
        allowed: bool,
        requires_confirm: bool,
        reason: str,
    ) -> CommandPolicy:
        return CommandPolicy(
            allowed=allowed,
            requires_confirm=requires_confirm,
            reason=reason,
            risk=risk,
            exec_mode=choose_exec_mode(text, risk),
            risk_categories=risk.categories,
            risk_reasons=risk.reasons,
        )

    if not text:
        return _verdict(allowed=True, requires_confirm=False, reason="")

    if match_patterns(text, forbidden_patterns):
        return _verdict(allowed=False, requires_confirm=False, reason="forbidden")

    if allowlist_patterns and not match_patterns(text, allowlist_patterns):
        return _verdict(allowed=False, requires_confirm=False, reason="outside_allowlist")

    if confirm_dangerous_commands and risk.is_dangerous:
        return _verdict(allowed=True, requires_confirm=True, reason="dangerous")

    if (chat_mode or "").lower() == "ask":
        return _verdict(allowed=True, requires_confirm=True, reason="ask_mode")

    return _verdict(allowed=True, requires_confirm=False, reason="")
