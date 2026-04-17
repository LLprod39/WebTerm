"""Tests for servers.services.terminal_ai.rules_loader (F2-4).

We exercise the ``_*_sync`` implementations directly — the async wrappers
call into them through ``database_sync_to_async`` which does not cooperate
with ``pytest.mark.django_db`` transaction semantics on Windows.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.models import GlobalServerRules, Server, ServerGroup, ServerShare
from servers.services.terminal_ai.rules_loader import (
    TerminalRulesContext,
    _load_effective_environment_vars_sync,
    _load_terminal_rules_sync,
)


def _make_server(user: User, **overrides) -> Server:
    return Server.objects.create(
        user=user,
        name=overrides.pop("name", "srv-rules"),
        host=overrides.pop("host", "10.0.0.42"),
        username=overrides.pop("username", "root"),
        auth_method=overrides.pop("auth_method", "password"),
        **overrides,
    )


@pytest.mark.django_db
def test_load_rules_empty_when_server_missing():
    user = User.objects.create_user(username="rules-none", password="x")
    ctx = _load_terminal_rules_sync(user_id=user.id, server_id=999_999)
    assert isinstance(ctx, TerminalRulesContext)
    assert ctx.forbidden_patterns == []
    assert ctx.rules_context == ""
    assert ctx.required_checks == []
    assert ctx.environment_vars == {}


@pytest.mark.django_db
def test_load_rules_merges_global_group_and_server_sources():
    owner = User.objects.create_user(username="rules-owner", password="x")
    group = ServerGroup.objects.create(
        user=owner,
        name="prod-cluster",
        environment_vars={"GROUP_ENV": "prod"},
        forbidden_commands=["rm -rf /etc", "drop database"],
    )
    GlobalServerRules.objects.create(
        user=owner,
        rules="Глобальное правило: не трогать /opt/legacy",
        forbidden_commands=["shutdown now", "iptables -F"],
        required_checks=["uptime", "df -h"],
        environment_vars={"GLOBAL_ENV": "yes"},
    )
    server = _make_server(
        owner,
        group=group,
        network_config={"env_vars": {"SERVER_ENV": "override"}},
    )

    ctx = _load_terminal_rules_sync(user_id=owner.id, server_id=server.id)

    # forbidden patterns from global + group, deduplicated
    assert "rm -rf /etc" in ctx.forbidden_patterns
    assert "shutdown now" in ctx.forbidden_patterns
    assert "iptables -F" in ctx.forbidden_patterns
    assert "drop database" in ctx.forbidden_patterns

    # required checks dedup + order preserved
    assert ctx.required_checks == ["uptime", "df -h"]

    # env vars: server > group > global
    assert ctx.environment_vars.get("GLOBAL_ENV") == "yes"
    assert ctx.environment_vars.get("GROUP_ENV") == "prod"
    assert ctx.environment_vars.get("SERVER_ENV") == "override"

    # rules_context text contains the global rule
    assert "/opt/legacy" in ctx.rules_context


@pytest.mark.django_db
def test_forbidden_patterns_deduplicated_case_insensitively():
    owner = User.objects.create_user(username="rules-dedup", password="x")
    group = ServerGroup.objects.create(
        user=owner,
        name="dedup-group",
        forbidden_commands=["Shutdown Now", "iptables -F"],
    )
    GlobalServerRules.objects.create(
        user=owner,
        forbidden_commands=["shutdown now", "IPTABLES -F"],
    )
    server = _make_server(owner, name="dedup-srv", group=group)

    ctx = _load_terminal_rules_sync(user_id=owner.id, server_id=server.id)

    # global is processed before group → original casing kept from first seen
    lowered = [p.lower() for p in ctx.forbidden_patterns]
    assert lowered.count("shutdown now") == 1
    assert lowered.count("iptables -f") == 1


@pytest.mark.django_db
def test_share_context_disabled_hides_knowledge_but_keeps_forbidden():
    owner = User.objects.create_user(username="rules-share-owner", password="x")
    viewer = User.objects.create_user(username="rules-share-viewer", password="x")
    GlobalServerRules.objects.create(
        user=owner,
        rules="Только для владельца: все сервера production",
        forbidden_commands=["shutdown now"],
    )
    server = _make_server(owner, name="share-srv")
    ServerShare.objects.create(
        server=server,
        user=viewer,
        shared_by=owner,
        is_revoked=False,
        share_context=False,  # viewer must NOT see knowledge/rules text
    )

    ctx = _load_terminal_rules_sync(user_id=viewer.id, server_id=server.id)

    # share_context=False → rules_context suppressed
    assert "production" not in ctx.rules_context
    # forbidden patterns are safety-critical and always applied
    assert "shutdown now" in ctx.forbidden_patterns


@pytest.mark.django_db
def test_viewer_without_share_cannot_load_anything():
    owner = User.objects.create_user(username="rules-noshare-owner", password="x")
    outsider = User.objects.create_user(username="rules-outsider", password="x")
    GlobalServerRules.objects.create(user=owner, forbidden_commands=["rm -rf /"])
    server = _make_server(owner, name="noshare-srv")

    ctx = _load_terminal_rules_sync(user_id=outsider.id, server_id=server.id)

    assert ctx == TerminalRulesContext()


@pytest.mark.django_db
def test_load_effective_environment_vars_merges_priority():
    owner = User.objects.create_user(username="env-owner", password="x")
    group = ServerGroup.objects.create(
        user=owner,
        name="env-group",
        environment_vars={"FOO": "group", "BAR": "group-bar"},
    )
    GlobalServerRules.objects.create(
        user=owner,
        environment_vars={"FOO": "global", "BAZ": "only-global"},
    )
    server = _make_server(
        owner,
        name="env-srv",
        group=group,
        network_config={"env_vars": {"FOO": "server"}},
    )

    env = _load_effective_environment_vars_sync(user_id=owner.id, server_id=server.id)

    # server > group > global
    assert env["FOO"] == "server"
    assert env["BAR"] == "group-bar"
    assert env["BAZ"] == "only-global"


@pytest.mark.django_db
def test_rules_context_as_tuple_shape_matches_legacy_consumer_contract():
    """Guard: consumer-side forwarder relies on TerminalRulesContext.as_tuple()."""
    user = User.objects.create_user(username="rules-shape", password="x")
    server = _make_server(user, name="shape-srv")
    ctx = _load_terminal_rules_sync(user_id=user.id, server_id=server.id)

    forbidden, rules_text, checks, env = ctx.as_tuple()
    assert isinstance(forbidden, list)
    assert isinstance(rules_text, str)
    assert isinstance(checks, list)
    assert isinstance(env, dict)
