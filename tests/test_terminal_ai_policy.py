"""Tests for servers.services.terminal_ai.policy (F2-6 + F2-8)."""
from __future__ import annotations

import pytest

from servers.services.terminal_ai.policy import (
    CommandPolicy,
    choose_exec_mode,
    decide_command_policy,
    match_patterns,
)

# ---------------------------------------------------------------------------
# match_patterns (F2-6)
# ---------------------------------------------------------------------------


class TestMatchPatterns:
    def test_empty_patterns_never_match(self):
        assert match_patterns("rm -rf /", []) is False
        assert match_patterns("rm -rf /", None) is False

    def test_substring_match(self):
        assert match_patterns("sudo apt install nginx", ["nginx"]) is True

    def test_case_insensitive(self):
        assert match_patterns("SHUTDOWN NOW", ["shutdown"]) is True

    def test_token_sequence_requires_contiguous_match(self):
        # "docker rm" should match "docker rm mycontainer" but NOT
        # "docker ps" + later "rm file" on separate tokens.
        assert match_patterns("docker rm mycontainer", ["docker rm"]) is True
        assert match_patterns("docker ps\nrm file", ["docker rm"]) is False

    def test_regex_pattern(self):
        assert match_patterns("rm -rf /opt/app", ["re:^rm\\s+-rf"]) is True
        assert match_patterns("rm file", ["re:^rm\\s+-rf"]) is False

    def test_malformed_regex_is_ignored_silently(self):
        # Broken regex must never raise or match
        assert match_patterns("rm file", ["re:[unclosed"]) is False

    def test_empty_prefix_stripped(self):
        assert match_patterns("cmd", ["  ", ""]) is False


# ---------------------------------------------------------------------------
# decide_command_policy (F2-6)
# ---------------------------------------------------------------------------


class TestDecideCommandPolicy:
    def test_empty_command_allowed_no_confirm(self):
        verdict = decide_command_policy("")
        assert verdict.allowed is True
        assert verdict.requires_confirm is False
        assert verdict.reason == ""

    def test_safe_command_auto_runs_in_agent_mode(self):
        verdict = decide_command_policy("ls -la", chat_mode="agent")
        assert verdict.allowed and not verdict.requires_confirm
        assert verdict.reason == ""
        assert verdict.risk.is_dangerous is False

    def test_dangerous_command_requires_confirm(self):
        verdict = decide_command_policy("rm -rf /opt", confirm_dangerous_commands=True)
        assert verdict.allowed is True
        assert verdict.requires_confirm is True
        assert verdict.reason == "dangerous"
        assert verdict.risk.is_dangerous is True
        assert verdict.risk_reasons  # non-empty human explanation

    def test_dangerous_confirm_disabled_still_allowed(self):
        verdict = decide_command_policy("rm -rf /opt", confirm_dangerous_commands=False)
        assert verdict.allowed is True
        assert verdict.requires_confirm is False
        # Reason: may fall through to "" or "ask_mode"; never "dangerous".
        assert verdict.reason in {"", "ask_mode"}

    def test_forbidden_pattern_blocks(self):
        verdict = decide_command_policy(
            "nginx reload",
            forbidden_patterns=["nginx"],
        )
        assert verdict.allowed is False
        assert verdict.reason == "forbidden"
        assert verdict.requires_confirm is False

    def test_forbidden_takes_precedence_over_dangerous(self):
        verdict = decide_command_policy(
            "rm -rf /opt",
            forbidden_patterns=["rm"],
        )
        assert verdict.allowed is False
        assert verdict.reason == "forbidden"

    def test_outside_allowlist_blocks(self):
        verdict = decide_command_policy(
            "apt install curl",
            allowlist_patterns=["ls", "pwd"],
        )
        assert verdict.allowed is False
        assert verdict.reason == "outside_allowlist"

    def test_allowlist_match_is_allowed(self):
        verdict = decide_command_policy(
            "ls -la",
            allowlist_patterns=["ls"],
        )
        assert verdict.allowed is True
        assert verdict.reason == ""

    def test_ask_mode_requires_confirm_on_safe_command(self):
        verdict = decide_command_policy("ls", chat_mode="ask")
        assert verdict.allowed is True
        assert verdict.requires_confirm is True
        assert verdict.reason == "ask_mode"

    def test_ask_mode_is_case_insensitive(self):
        verdict = decide_command_policy("ls", chat_mode="ASK")
        assert verdict.reason == "ask_mode"

    def test_verdict_is_frozen(self):
        verdict = decide_command_policy("ls")
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            verdict.allowed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# choose_exec_mode (F2-8)
# ---------------------------------------------------------------------------


class TestChooseExecMode:
    @pytest.mark.parametrize(
        "cmd",
        [
            "ls -la",
            "pwd",
            "whoami",
            "hostname",
            "uname -a",
            "df -h",
            "free -m",
            "id",
            "ps aux",
            "docker ps",
            "docker images",
            "kubectl get pods",
            "git status",
            "systemctl status nginx",
            "journalctl -n 100",
        ],
    )
    def test_safe_readonly_commands_are_direct(self, cmd: str):
        assert choose_exec_mode(cmd) == "direct", cmd

    @pytest.mark.parametrize(
        "cmd",
        [
            "vim /etc/nginx/nginx.conf",
            "nano config.txt",
            "less /var/log/syslog",
            "top",
            "htop",
            "tail -f /var/log/syslog",
            "watch -n 1 df -h",
            "sudo systemctl restart nginx",
            "mysql -u root",
            "python",
            "python -i",
            "journalctl -f",
            "docker exec -it mycontainer bash",
        ],
    )
    def test_interactive_commands_require_pty(self, cmd: str):
        assert choose_exec_mode(cmd) == "pty", cmd

    @pytest.mark.parametrize(
        "cmd",
        [
            "rm -rf /tmp/x",
            "reboot",
            "systemctl stop nginx",
            "iptables -F",
            "mkfs.ext4 /dev/sdb1",
        ],
    )
    def test_dangerous_commands_forced_pty(self, cmd: str):
        assert choose_exec_mode(cmd) == "pty", cmd

    @pytest.mark.parametrize(
        "cmd",
        [
            "ls | grep foo",
            "ls && pwd",
            "ls > /tmp/out",
            "echo $(whoami)",
            "ps aux | head",
        ],
    )
    def test_shell_metacharacters_force_pty(self, cmd: str):
        assert choose_exec_mode(cmd) == "pty", cmd

    def test_empty_string_defaults_pty(self):
        assert choose_exec_mode("") == "pty"
        assert choose_exec_mode("   ") == "pty"

    def test_sudo_with_n_flag_still_pty_conservative(self):
        # Even `sudo -n` is conservative — we keep it in PTY (v1).
        assert choose_exec_mode("sudo -n apt-get update") == "pty"

    def test_plan_item_integration(self):
        """decide_command_policy exposes exec_mode consistently."""
        verdict = decide_command_policy("ls -la")
        assert verdict.exec_mode == "direct"

        dangerous = decide_command_policy("rm -rf /opt")
        assert dangerous.exec_mode == "pty"

    def test_command_policy_is_immutable_and_has_all_fields(self):
        verdict = decide_command_policy("ls")
        assert isinstance(verdict, CommandPolicy)
        assert hasattr(verdict, "risk_categories")
        assert hasattr(verdict, "risk_reasons")
        assert hasattr(verdict, "exec_mode")
