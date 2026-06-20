from __future__ import annotations

from .docker_service_recovery_commands import (
    _build_container_snapshot_command,
    _build_container_verify_command,
)
from .docker_service_recovery_preapproval import build_preapproval_nodes
from .docker_service_recovery_recovery import build_recovery_loop_nodes


def build_docker_service_recovery_nodes(
    *,
    server_id: int,
    container_name: str,
    server_name: str,
) -> list[dict]:
    snapshot_command = _build_container_snapshot_command(container_name)
    verify_command = _build_container_verify_command(container_name)
    return [
        *build_preapproval_nodes(
            server_id=server_id,
            container_name=container_name,
            server_name=server_name,
            snapshot_command=snapshot_command,
        ),
        *build_recovery_loop_nodes(
            server_id=server_id,
            verify_command=verify_command,
        ),
    ]

def build_docker_service_recovery_edges() -> list[dict]:
    return [
        {"id": "e_monitoring_parallel", "source": "monitoring_start", "target": "entry_parallel", "sourceHandle": "out", "animated": True},
        {"id": "e_parallel_report", "source": "entry_parallel", "target": "incident_report", "sourceHandle": "out", "animated": True},
        {"id": "e_parallel_tg", "source": "entry_parallel", "target": "alert_telegram", "sourceHandle": "out", "animated": True},
        {"id": "e_parallel_snapshot", "source": "entry_parallel", "target": "snapshot_probe", "sourceHandle": "out", "animated": True},
        {"id": "e_report_ctx_ok", "source": "incident_report", "target": "investigation_context_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_report_ctx_err", "source": "incident_report", "target": "investigation_context_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_tg_ctx_ok", "source": "alert_telegram", "target": "investigation_context_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_tg_ctx_err", "source": "alert_telegram", "target": "investigation_context_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_snapshot_ctx_ok", "source": "snapshot_probe", "target": "investigation_context_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_snapshot_ctx_err", "source": "snapshot_probe", "target": "investigation_context_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_ctx_investigate", "source": "investigation_context_merge", "target": "investigate_agent", "sourceHandle": "out", "animated": True},
        {"id": "e_investigate_plan_ok", "source": "investigate_agent", "target": "plan_ready_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_investigate_plan_err", "source": "investigate_agent", "target": "plan_ready_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_plan_ready_llm", "source": "plan_ready_merge", "target": "plan_llm", "sourceHandle": "out", "animated": True},
        {"id": "e_plan_llm_result_ok", "source": "plan_llm", "target": "plan_result_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_plan_llm_result_err", "source": "plan_llm", "target": "plan_result_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_plan_result_report", "source": "plan_result_merge", "target": "plan_report", "sourceHandle": "out", "animated": True},
        {"id": "e_plan_report_approval", "source": "plan_report", "target": "approval_gate", "sourceHandle": "success", "animated": True},
        {"id": "e_approval_rejected_report", "source": "approval_gate", "target": "approval_rejected_report", "sourceHandle": "rejected", "animated": True},
        {"id": "e_approval_rejected_tg", "source": "approval_rejected_report", "target": "approval_rejected_telegram", "sourceHandle": "success", "animated": True},
        {"id": "e_approval_timeout_report", "source": "approval_gate", "target": "approval_timeout_report", "sourceHandle": "timeout", "animated": True},
        {"id": "e_approval_timeout_tg", "source": "approval_timeout_report", "target": "approval_timeout_telegram", "sourceHandle": "success", "animated": True},
        {"id": "e_approval_started_tg", "source": "approval_gate", "target": "recovery_started_telegram", "sourceHandle": "approved", "animated": True},
        {"id": "e_recovery_started_merge_ok", "source": "recovery_started_telegram", "target": "recovery_delivery_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_recovery_started_merge_err", "source": "recovery_started_telegram", "target": "recovery_delivery_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_recovery_delivery_agent", "source": "recovery_delivery_merge", "target": "recovery_agent", "sourceHandle": "out", "animated": True},
        {"id": "e_recovery_agent_merge_ok", "source": "recovery_agent", "target": "recovery_attempt_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_recovery_agent_merge_err", "source": "recovery_agent", "target": "recovery_attempt_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_recovery_attempt_verify", "source": "recovery_attempt_merge", "target": "verify_after_recovery", "sourceHandle": "out", "animated": True},
        {"id": "e_verify_recovery_success", "source": "verify_after_recovery", "target": "success_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_verify_recovery_operator_1", "source": "verify_after_recovery", "target": "operator_input_1", "sourceHandle": "error", "animated": True},
        {"id": "e_operator_1_guided", "source": "operator_input_1", "target": "guided_recovery_1", "sourceHandle": "received", "animated": True},
        {"id": "e_operator_1_failure", "source": "operator_input_1", "target": "failure_merge", "sourceHandle": "timeout", "animated": True},
        {"id": "e_guided_1_merge_ok", "source": "guided_recovery_1", "target": "guided_attempt_1_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_guided_1_merge_err", "source": "guided_recovery_1", "target": "guided_attempt_1_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_guided_1_verify", "source": "guided_attempt_1_merge", "target": "verify_after_guidance_1", "sourceHandle": "out", "animated": True},
        {"id": "e_verify_1_success", "source": "verify_after_guidance_1", "target": "success_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_verify_1_operator_2", "source": "verify_after_guidance_1", "target": "operator_input_2", "sourceHandle": "error", "animated": True},
        {"id": "e_operator_2_guided", "source": "operator_input_2", "target": "guided_recovery_2", "sourceHandle": "received", "animated": True},
        {"id": "e_operator_2_failure", "source": "operator_input_2", "target": "failure_merge", "sourceHandle": "timeout", "animated": True},
        {"id": "e_guided_2_merge_ok", "source": "guided_recovery_2", "target": "guided_attempt_2_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_guided_2_merge_err", "source": "guided_recovery_2", "target": "guided_attempt_2_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_guided_2_verify", "source": "guided_attempt_2_merge", "target": "verify_after_guidance_2", "sourceHandle": "out", "animated": True},
        {"id": "e_verify_2_success", "source": "verify_after_guidance_2", "target": "success_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_verify_2_failure", "source": "verify_after_guidance_2", "target": "failure_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_success_report", "source": "success_merge", "target": "success_report", "sourceHandle": "out", "animated": True},
        {"id": "e_success_tg", "source": "success_report", "target": "success_telegram", "sourceHandle": "success", "animated": True},
        {"id": "e_failure_report", "source": "failure_merge", "target": "final_failure_report", "sourceHandle": "out", "animated": True},
        {"id": "e_failure_tg", "source": "final_failure_report", "target": "final_failure_telegram", "sourceHandle": "success", "animated": True},
    ]


