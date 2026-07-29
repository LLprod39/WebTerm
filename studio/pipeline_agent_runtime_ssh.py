from __future__ import annotations

import contextlib
from typing import Any

from app.shell_commands import is_read_only_command
from app.sudo_policy import prepare_sudo_command, resolve_sudo_policy

from .models import PipelineRun
from .pipeline_agent_runtime_helpers import (
    _coerce_optional_int,
    _resolve_context_value,
    _s2a_fn,
)
from .pipeline_context import (
    build_pipeline_tool_spec,
    pipeline_permission_mode,
    render_template_value,
)
from .services import get_owned_server


async def execute_agent_ssh_cmd(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute a direct SSH command without LLM."""
    import asyncssh

    # Resolve through the facade so existing monkeypatches on pipeline_agent_runtime keep working.
    from studio import pipeline_agent_runtime as runtime

    config = node.get("data", {})
    raw_server_id = _resolve_context_value(config, context, "server_id", "server_id")
    server_id = _coerce_optional_int(raw_server_id)
    command = config.get("command", "")
    preflight_commands = list(config.get("preflight_commands") or [])
    verification_commands = list(config.get("verification_commands") or [])

    with contextlib.suppress(KeyError, ValueError):
        command = command.format(**context)

    if not server_id:
        if raw_server_id not in (None, ""):
            return {
                "status": "failed",
                "error": f"Invalid server_id for this SSH node: {raw_server_id!r}.",
                "output": "",
            }
        return {
            "status": "failed",
            "error": "No server configured for this SSH node. Select a Server or provide server_id in runtime context.",
            "output": "",
        }
    if not command:
        if config.get("agent_config_id") or config.get("goal"):
            patched_node = dict(node)
            patched_data = dict(config)
            if server_id and not patched_data.get("server_ids"):
                patched_data["server_ids"] = [server_id]
            patched_node["data"] = patched_data
            return await runtime.execute_agent_react(patched_node, context, run)
        return {
            "status": "failed",
            "error": "Команда не задана. Откройте узел в редакторе и введите команду в поле «Command», "
            "или смените тип узла на «ReAct Agent» если нужен ИИ-агент.",
        }

    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    server = await _s2a_fn(get_owned_server)(owner, server_id)
    if server is None:
        return {"status": "failed", "error": f"Server not found: {server_id}"}
    commands_to_check = [command, *preflight_commands, *verification_commands]
    if getattr(server, "ai_read_only", False) and any(
        not is_read_only_command(str(candidate or "")) for candidate in commands_to_check if str(candidate or "").strip()
    ):
        return {
            "status": "failed",
            "error": "Server is in AI read-only mode; changing or unclassified SSH commands are blocked.",
            "output": "",
        }

    permission_engine = runtime.PermissionEngine(
        mode=pipeline_permission_mode(config),
        sudo_policy=resolve_sudo_policy(config.get("sudo_policy")),
    )
    sandbox_manager = runtime.SandboxManager()
    hook_manager = runtime.HookManager()
    spec = build_pipeline_tool_spec("ssh_execute", command=command)
    decision = permission_engine.evaluate(spec, {"command": command})
    if not decision.allowed and not preflight_commands:
        return {
            "status": "failed",
            "error": decision.reason,
            "output": "",
        }

    try:
        connect_kwargs = await runtime.get_server_connect_kwargs(server, connect_timeout=30)
        sudo_password = await _s2a_fn(runtime.get_server_sudo_password, thread_sensitive=True)(server)

        async with asyncssh.connect(**connect_kwargs) as conn:
            combined_outputs: list[str] = []

            async def _run_remote_command(command_text: str, *, stage: str) -> tuple[int, str]:
                stage_spec = build_pipeline_tool_spec("ssh_execute", command=command_text)
                stage_decision = permission_engine.evaluate(stage_spec, {"command": command_text})
                if not stage_decision.allowed:
                    raise RuntimeError(stage_decision.reason)
                prepared_sudo = prepare_sudo_command(
                    command_text,
                    permission_engine.sudo_policy,
                    sudo_auth_mode=getattr(server, "sudo_auth_mode", "none"),
                    sudo_password=sudo_password,
                )
                executable_command = prepared_sudo.command
                sudo_notes = prepared_sudo.notes
                stage_profile = stage_decision.sandbox_profile if stage == "command" else "ops_read"
                sandbox_decision = sandbox_manager.validate(stage_spec, {"command": executable_command}, stage_profile)
                if not sandbox_decision.allowed:
                    raise RuntimeError(sandbox_decision.reason)
                run_kwargs: dict[str, Any] = {"timeout": 120}
                if prepared_sudo.input_text is not None:
                    run_kwargs["input"] = prepared_sudo.input_text
                remote_result = await conn.run(executable_command, **run_kwargs)
                remote_output = remote_result.stdout + (("\n" + remote_result.stderr) if remote_result.stderr else "")
                if sudo_notes:
                    remote_output = "\n".join(sudo_notes) + "\n" + remote_output
                compacted_output = await hook_manager.post_tool_use("ssh_execute", remote_output)
                permission_engine.record_success(stage_spec, {"command": executable_command}, compacted_output)
                await runtime._log_pipeline_ssh_command(
                    run=run,
                    server=server,
                    node_id=str(node.get("id") or ""),
                    command=f"[{stage}] {executable_command}",
                    exit_code=remote_result.exit_status,
                    output=compacted_output,
                )
                combined_outputs.append(f"## {stage}\n{compacted_output}")
                return remote_result.exit_status, compacted_output

            for preflight_command in preflight_commands:
                rendered = render_template_value(preflight_command, context)
                exit_code, _ = await _run_remote_command(str(rendered), stage="preflight")
                if exit_code != 0:
                    return {
                        "status": "failed",
                        "error": f"Preflight command failed: {rendered}",
                        "output": "\n\n".join(combined_outputs),
                    }

            decision = permission_engine.evaluate(spec, {"command": command})
            if not decision.allowed:
                return {"status": "failed", "error": decision.reason, "output": "\n\n".join(combined_outputs)}

            exit_code, output = await _run_remote_command(command, stage="command")
            verification_summary = permission_engine.verification_summary()
            if verification_commands:
                for verify_command in verification_commands:
                    rendered = render_template_value(verify_command, context)
                    verify_exit_code, _ = await _run_remote_command(str(rendered), stage="verification")
                    if verify_exit_code != 0:
                        return {
                            "status": "failed",
                            "error": f"Verification command failed: {rendered}",
                            "output": "\n\n".join(combined_outputs),
                        }
                verification_summary = permission_engine.verification_summary()
                combined_outputs.append(f"## verification_summary\n{verification_summary}")

            full_output = "\n\n".join(combined_outputs) if combined_outputs else output
            return {
                "status": "completed" if exit_code == 0 else "failed",
                "output": full_output,
                "exit_code": exit_code,
                "verification_summary": verification_summary,
                "error": "" if exit_code == 0 else output,
            }
    except Exception as exc:
        error_text = f"{exc} (server: {server.name} [{server.username}@{server.host}])"
        await runtime._log_pipeline_ssh_command(
            run=run,
            server=server,
            node_id=str(node.get("id") or ""),
            command=command,
            exit_code=-1,
            error=error_text,
        )
        return {
            "status": "failed",
            "error": error_text,
        }
