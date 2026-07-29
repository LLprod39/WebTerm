"""Regression tests for shell compound-command policy bypasses."""

from __future__ import annotations

import pytest

from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.permissions.engine import PermissionEngine
from servers.services.terminal_ai.policy import decide_command_policy


def _ssh_spec() -> ToolSpec:
    return ToolSpec(
        name="ssh_execute",
        category="ssh",
        risk="exec",
        description="Execute command",
        input_schema={},
        requires_verification=True,
    )


@pytest.mark.parametrize("mode", ["SAFE", "AUTO_GUARDED"])
@pytest.mark.parametrize(
    "command",
    [
        "touch /tmp/audit_probe",
        "cat /etc/os-release; touch /tmp/audit_probe",
        "uptime && useradd audit-probe",
        "bash -c 'uptime; touch /tmp/audit_probe'",
        "uptime && id $(touch /tmp/audit_probe)",
    ],
)
def test_agent_policy_blocks_unclassified_or_indirect_mutations(mode, command):
    decision = PermissionEngine(mode=mode).evaluate(_ssh_spec(), {"command": command})

    assert decision.allowed is False
    assert decision.requires_approval is True


def test_agent_policy_does_not_approve_compound_mutation_after_one_preflight():
    engine = PermissionEngine(mode="AUTO_GUARDED")
    spec = _ssh_spec()
    engine.record_success(spec, {"command": "systemctl status nginx"}, "active")

    decision = engine.evaluate(spec, {"command": "systemctl restart nginx; touch /tmp/audit_probe"})

    assert decision.allowed is False
    assert decision.requires_approval is True


@pytest.mark.parametrize("mode", ["SAFE", "AUTO_GUARDED"])
def test_agent_policy_preserves_compound_read_only_commands(mode):
    decision = PermissionEngine(mode=mode).evaluate(
        _ssh_spec(),
        {"command": "cat /etc/os-release && uptime"},
    )

    assert decision.allowed is True
    assert decision.sandbox_profile == "ops_read"


@pytest.mark.parametrize(
    "command",
    [
        "ss -K dst 192.0.2.1",
        "hostname new-name",
        "date --set tomorrow",
        "date 010100002030",
        "docker compose config --output /tmp/compose.yaml",
        "find /tmp -fprintf /tmp/result '%p\\n'",
        "git log --output=/tmp/history",
        "ip link set eth0 down",
        "journalctl --vacuum-time=1s",
        "less +!touch /tmp/audit_probe /etc/hosts",
    ],
)
def test_agent_policy_rejects_mutating_options_on_read_like_commands(command):
    decision = PermissionEngine(mode="AUTO_GUARDED").evaluate(_ssh_spec(), {"command": command})

    assert decision.allowed is False
    assert decision.requires_approval is True


def test_preflight_marker_requires_the_command_to_be_executed():
    engine = PermissionEngine(mode="AUTO_GUARDED")
    spec = _ssh_spec()
    engine.record_success(spec, {"command": "echo systemctl status nginx"}, "systemctl status nginx")

    decision = engine.evaluate(spec, {"command": "systemctl restart nginx"})

    assert decision.allowed is False
    assert "preflight" in decision.reason


def test_read_only_output_can_name_a_mutating_command_without_executing_it():
    decision = PermissionEngine(mode="AUTO_GUARDED").evaluate(
        _ssh_spec(),
        {"command": "echo systemctl restart nginx"},
    )

    assert decision.allowed is True
    assert decision.sandbox_profile == "ops_read"


@pytest.mark.parametrize("command", ["date +%s", "ip link show", "command -v systemctl"])
def test_agent_policy_preserves_constrained_read_only_variants(command):
    decision = PermissionEngine(mode="AUTO_GUARDED").evaluate(_ssh_spec(), {"command": command})

    assert decision.allowed is True
    assert decision.sandbox_profile == "ops_read"


@pytest.mark.parametrize(
    "command",
    [
        "uptime; touch /tmp/audit_probe",
        "touch /tmp/audit_probe; uptime",
        "uptime && id",
        "uptime | sh",
        "bash -c 'uptime; touch /tmp/audit_probe'",
        "uptime && id $(touch /tmp/audit_probe)",
    ],
)
def test_terminal_allowlist_must_cover_every_executed_fragment(command):
    verdict = decide_command_policy(command, allowlist_patterns=["uptime"])

    assert verdict.allowed is True
    assert verdict.requires_confirm is True
    assert verdict.reason in {"outside_allowlist", "dangerous", "unclassifiable"}


def test_terminal_allowlist_allows_each_explicit_read_fragment():
    verdict = decide_command_policy(
        "uptime && id",
        allowlist_patterns=["uptime", "id"],
    )

    assert verdict.allowed is True


def test_terminal_allowlist_ignores_quoted_separator_text():
    verdict = decide_command_policy(
        "printf 'healthy; still data'",
        allowlist_patterns=["printf"],
    )

    assert verdict.allowed is True


def test_terminal_regex_allowlist_requires_the_whole_fragment():
    allowed = decide_command_policy("uptime -p", allowlist_patterns=[r"re:^uptime(?:\s+-p)?$"])
    denied = decide_command_policy("echo uptime -p", allowlist_patterns=[r"re:^uptime(?:\s+-p)?$"])

    assert allowed.allowed is True
    assert denied.allowed is True
    assert denied.requires_confirm is True
