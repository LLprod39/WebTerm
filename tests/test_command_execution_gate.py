from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.command_execution_gate import evaluate_command_execution_gate
from servers.agent_tools import tool_ssh_execute
from servers.operator_mutate_exec import _execute_on_server


@pytest.mark.parametrize(
    "command",
    [
        "mv /etc /tmp/gone",
        "crontab -r",
        "kubectl delete ns production",
        "docker rm -f $(docker ps -aq)",
        "sed -i 's/no/yes/' /etc/ssh/sshd_config",
        "r'm' -rf /var",
        "R=rm; $R -rf /var",
        "python3 -c \"import shutil; shutil.rmtree('/var')\"",
        "perl -e 'unlink q{/etc/passwd}'",
        'node --eval \'require("fs").rmSync("/var", {recursive:true})\'',
        "uptime && id $(touch /tmp/probe)",
        "cat /etc/hosts > /tmp/hosts",
    ],
)
def test_bypass_corpus_never_auto_runs(command):
    verdict = evaluate_command_execution_gate(command)

    assert verdict.auto_run_allowed is False
    assert verdict.requires_approval is True


@pytest.mark.parametrize(
    "command",
    [
        "uptime",
        "cat /etc/os-release && id",
        "docker ps",
        "kubectl get pods -A",
        "systemctl status nginx",
        "git status",
        "echo INC-55",
    ],
)
def test_builtin_read_only_allowlist_auto_runs(command):
    verdict = evaluate_command_execution_gate(command)

    assert verdict.auto_run_allowed is True
    assert verdict.requires_approval is False


class _AgentSessionStub:
    def __init__(self, reply: str | None):
        self.command_timeout = 30
        self.event_callback = self._event_callback
        self.user_reply_future = None
        self.reply = reply
        self.executed: list[str] = []
        self.execution_approval_granted = False
        self.allowed_servers = {1: SimpleNamespace(ai_read_only=False)}

    def resolve_server(self, _server: str) -> int:
        return 1

    def get_forbidden_patterns(self, _server_id: int) -> list[str]:
        return []

    async def _event_callback(self, event: str, _payload: dict):
        if event == "agent_question" and self.reply is not None:
            asyncio.get_running_loop().call_soon(lambda: self.user_reply_future.set_result(self.reply))

    async def execute(self, _server_id: int, command: str) -> dict:
        self.executed.append(command)
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1}


@pytest.mark.asyncio
async def test_agent_tool_executes_mutation_only_after_one_time_approval():
    session = _AgentSessionStub("allow_once")

    result = await tool_ssh_execute(session, server="prod", command="mv /tmp/a /tmp/b")

    assert result.success is True
    assert session.executed == ["mv /tmp/a /tmp/b"]


@pytest.mark.asyncio
async def test_agent_tool_fails_closed_when_approval_channel_is_unavailable():
    session = _AgentSessionStub(None)
    session.event_callback = None

    result = await tool_ssh_execute(session, server="prod", command="mv /tmp/a /tmp/b")

    assert result.success is False
    assert session.executed == []


@pytest.mark.asyncio
async def test_agent_tool_accepts_preapproved_pipeline_scope_without_second_prompt():
    session = _AgentSessionStub(None)
    session.event_callback = None
    session.execution_approval_granted = True

    result = await tool_ssh_execute(session, server="prod", command="mv /tmp/a /tmp/b")

    assert result.success is True
    assert session.executed == ["mv /tmp/a /tmp/b"]


@pytest.mark.asyncio
async def test_agent_tool_read_only_boundary_cannot_be_overridden_by_preapproval():
    session = _AgentSessionStub(None)
    session.event_callback = None
    session.execution_approval_granted = True
    session.allowed_servers[1].ai_read_only = True

    result = await tool_ssh_execute(session, server="prod", command="mv /tmp/a /tmp/b")

    assert result.success is False
    assert session.executed == []


def test_operator_read_only_boundary_rejects_denylist_bypass():
    server = SimpleNamespace(id=1, name="prod", ai_read_only=True)

    result = _execute_on_server(None, server, "R=mv; $R /etc /tmp/gone", allow_destructive=True)

    assert result["blocked"] is True
    assert "ai_read_only" in result["error"]
