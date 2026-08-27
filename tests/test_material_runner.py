import asyncio
import json

import pytest
from django.test import override_settings

from app.agent_kernel.sandbox.material_runner import (
    MaterialRunnerError,
    build_material_runner_docker_command,
    execute_isolated_material,
    material_runner_image_is_immutable,
)

IMAGE = "sha256:" + "a" * 64


def test_material_runner_requires_enabled_immutable_image():
    assert material_runner_image_is_immutable(IMAGE)
    assert not material_runner_image_is_immutable("webterm-material:latest")
    with (
        override_settings(AGENT_MATERIAL_RUNNER_ENABLED=False, AGENT_MATERIAL_RUNNER_IMAGE=IMAGE),
        pytest.raises(MaterialRunnerError, match="disabled"),
    ):
        build_material_runner_docker_command()


@override_settings(AGENT_MATERIAL_RUNNER_ENABLED=True, AGENT_MATERIAL_RUNNER_IMAGE=IMAGE)
def test_material_runner_docker_contract_has_no_network_mounts_or_privileges():
    command = build_material_runner_docker_command(runner_id="b" * 32)
    joined = " ".join(command)
    assert "--network bridge" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges:true" in command
    assert "--user 10001:10001" in joined
    assert "--tmpfs /work:" in joined
    assert "--mount" not in command
    assert "/var/run/docker.sock" not in joined


@override_settings(
    AGENT_MATERIAL_RUNNER_ENABLED=True, AGENT_MATERIAL_RUNNER_IMAGE=IMAGE, AGENT_MATERIAL_RUNNER_DOCKER_NETWORK="host"
)
def test_material_runner_never_allows_host_network():
    with pytest.raises(MaterialRunnerError, match="cannot use host"):
        build_material_runner_docker_command()


@pytest.mark.asyncio
@override_settings(AGENT_MATERIAL_RUNNER_ENABLED=True, AGENT_MATERIAL_RUNNER_IMAGE=IMAGE)
async def test_material_runner_validates_response(monkeypatch):
    class Process:
        returncode = 0

        async def communicate(self, payload):
            request = json.loads(payload)
            assert request["content"] == "echo ok"
            return json.dumps(
                {
                    "schema": "webterm.material-result.v1",
                    "stdout": "ok\n",
                    "stderr": "",
                    "exit_status": 0,
                    "duration_ms": 3,
                }
            ).encode(), b""

    async def fake_exec(*_args, **_kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await execute_isolated_material(content="echo ok", args=[], language="bash")
    assert result.stdout == "ok\n"
    assert result.runtime == "docker"
