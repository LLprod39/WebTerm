from __future__ import annotations

from kubernetes_ops.models import K8sActionRequest, K8sWorkloadRef
from kubernetes_ops.services.action_errors import ActionRequestValidationError
from kubernetes_ops.services.action_requests import (
    approve_external_action_request,
    block_kubernetes_action_execution,
    create_kubernetes_action_request,
    record_external_action_verification,
)


def _terminal_execute_rejected(action_request: K8sActionRequest, user) -> bool:
    try:
        block_kubernetes_action_execution(action_request=action_request, user=user)
    except ActionRequestValidationError as exc:
        return exc.code == "action_request_not_pending"
    return False


def _blocked_execution_request(user, workload: K8sWorkloadRef) -> K8sActionRequest:
    request = create_kubernetes_action_request(
        user=user,
        data={
            "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
            "reason": "release evidence execution block smoke",
            "target": {"workload_id": f"workload_{workload.id}"},
        },
    )
    request = approve_external_action_request(
        action_request=request,
        user=user,
        data={
            "approval_ref": "CHG-RELEASE-EVIDENCE-BLOCK",
            "summary": "release evidence blocked execution approval smoke",
        },
    )
    return block_kubernetes_action_execution(action_request=request, user=user)


def _terminal_verify_rejected(action_request: K8sActionRequest, user) -> bool:
    try:
        record_external_action_verification(
            action_request=action_request,
            user=user,
            data={"outcome": "succeeded", "summary": "terminal rewrite smoke"},
        )
    except ActionRequestValidationError as exc:
        return exc.code == "action_request_not_pending"
    return False
