from __future__ import annotations

import ast
from dataclasses import is_dataclass
from pathlib import Path

from servers.services.terminal_ai.state import TerminalAiState
from servers.services.terminal_manual_command_state import ManualCommandState

ROOT = Path(__file__).resolve().parents[1]
CONSUMER_DIR = ROOT / "servers" / "consumers"

LEGACY_SHARED_STATE = {
    "_agent_extra_conns",
    "_ai_active_cmd_id",
    "_ai_active_output",
    "_ai_allowlist_patterns",
    "_ai_audit_context",
    "_ai_background_tasks",
    "_ai_error_retries",
    "_ai_execution_mode",
    "_ai_exit_futures",
    "_ai_forbidden_patterns",
    "_ai_history",
    "_ai_last_done_items",
    "_ai_last_report",
    "_ai_lock",
    "_ai_marker_token",
    "_ai_next_id",
    "_ai_plan",
    "_ai_plan_index",
    "_ai_run",
    "_ai_run_id",
    "_ai_session",
    "_ai_settings",
    "_ai_step_extra_count",
    "_ai_stop_requested",
    "_ai_user_message",
    "_input_capture_suppress",
    "_manual_active_cmd_id",
    "_manual_active_output",
    "_manual_input_buffer",
    "_manual_next_cmd_id",
    "_manual_pending_commands",
    "_unavailable_cmds",
}


def _self_attributes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    }


def test_terminal_state_is_explicit_and_legacy_shared_attrs_are_not_used() -> None:
    assert is_dataclass(TerminalAiState)
    assert is_dataclass(ManualCommandState)

    offenders: dict[str, list[str]] = {}
    for path in CONSUMER_DIR.glob("ssh_terminal*.py"):
        used = sorted(_self_attributes(path) & LEGACY_SHARED_STATE)
        if used:
            offenders[path.name] = used

    assert offenders == {}


def test_terminal_consumer_declares_fewer_than_twenty_state_fields() -> None:
    path = CONSUMER_DIR / "ssh_terminal.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    consumer = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SSHTerminalConsumer"
    )
    declared_fields = {
        node.target.id
        for node in consumer.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }

    assert len(declared_fields) < 20, sorted(declared_fields)
