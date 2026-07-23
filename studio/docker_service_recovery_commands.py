from __future__ import annotations

import shlex

RESTRICTED_AGENT_TOOLS = ["ssh_execute", "read_console", "send_ctrl_c"]


def _quote_shell_arg(value: str) -> str:
    return shlex.quote(str(value or "").strip())


def _build_container_snapshot_command(container_name: str) -> str:
    quoted = _quote_shell_arg(container_name)
    return (
        "echo '[incident-snapshot]'; "
        "date; "
        "hostname || uname -n; "
        f"docker ps -a --filter name={quoted} "
        "--format 'name={{.Names}} state={{.State}} status={{.Status}}'; "
        f"docker inspect -f 'status={{{{.State.Status}}}} running={{{{.State.Running}}}} "
        "exit_code={{{{.State.ExitCode}}}} "
        "health={{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}n/a{{{{end}}}} "
        "started={{{{.State.StartedAt}}}} finished={{{{.State.FinishedAt}}}}' "
        f"{quoted} 2>&1 || true; "
        f"docker logs --tail 40 {quoted} 2>&1 || true"
    )


def _build_container_verify_command(container_name: str) -> str:
    quoted = _quote_shell_arg(container_name)
    return (
        f"status=\"$(docker inspect -f '{{{{{{{{.State.Status}}}}}}}}' {quoted} 2>/dev/null || echo missing)\"; "
        f"health=\"$(docker inspect -f '{{{{{{{{if .State.Health}}}}}}}}{{{{{{{{.State.Health.Status}}}}}}}}{{{{{{{{else}}}}}}}}n/a{{{{{{{{end}}}}}}}}' {quoted} 2>/dev/null || echo missing)\"; "
        'echo "status=$status health=$health"; '
        '[ "$status" = "running" ] || exit 1; '
        '[ "$health" != "unhealthy" ] || exit 1'
    )
