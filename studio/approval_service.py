from __future__ import annotations

from datetime import datetime
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from studio.approval_models import ApprovalRequest
from studio.models import PipelineRun


class ApprovalAccessError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        return self.message


def _requester_ids(run: PipelineRun) -> set[int]:
    return {user_id for user_id in (run.pipeline.owner_id, run.triggered_by_id) if user_id}


def resolve_approval_approver(run: PipelineRun, config: dict[str, Any]) -> User:
    excluded_ids = _requester_ids(run)
    eligible = User.objects.filter(is_active=True).exclude(pk__in=excluded_ids)
    username = str(config.get("approver_username") or "").strip()
    delivery_email = str(config.get("to_email") or "").strip()

    if username:
        approver = eligible.filter(username=username).first()
        if approver is None:
            raise ApprovalAccessError(
                "Configured approval user is missing, inactive, or is the pipeline owner/requester."
            )
        return approver

    if delivery_email:
        matches = list(eligible.filter(email__iexact=delivery_email).order_by("id")[:2])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ApprovalAccessError("Approval email matches multiple active platform users; set approver_username.")

    staff_candidates = list(eligible.filter(is_staff=True).order_by("id")[:2])
    if len(staff_candidates) == 1:
        return staff_candidates[0]
    raise ApprovalAccessError(
        "Human approval requires one distinct active approver. Set approver_username or use an email matching one user."
    )


@transaction.atomic
def arm_approval_request(
    *,
    run: PipelineRun,
    node_id: str,
    approver: User,
    raw_token: str,
    expires_at: datetime,
) -> ApprovalRequest:
    requested_by = run.triggered_by or run.pipeline.owner
    approval, _created = ApprovalRequest.objects.select_for_update().update_or_create(
        run=run,
        node_id=node_id,
        defaults={
            "token_digest": ApprovalRequest.digest_token(raw_token),
            "approver": approver,
            "requested_by": requested_by,
            "status": ApprovalRequest.STATUS_PENDING,
            "response_text": "",
            "expires_at": expires_at,
            "decided_at": None,
            "decided_by": None,
        },
    )
    return approval


def _validate_access(approval: ApprovalRequest, *, user: User, raw_token: str) -> None:
    if not user.is_active:
        raise ApprovalAccessError("The assigned approval user is inactive.", 403)
    if approval.approver_id is None or approval.approver_id != user.id:
        raise ApprovalAccessError("This approval request is assigned to another user.", 403)
    if user.id in _requester_ids(approval.run):
        raise ApprovalAccessError("Pipeline owners and requesters cannot approve their own run.", 403)
    if not raw_token or not approval.token_matches(raw_token):
        raise ApprovalAccessError("Invalid or expired token.", 403)
    if approval.status == ApprovalRequest.STATUS_EXPIRED or approval.is_expired:
        if approval.status == ApprovalRequest.STATUS_PENDING:
            ApprovalRequest.objects.filter(pk=approval.pk, status=ApprovalRequest.STATUS_PENDING).update(
                status=ApprovalRequest.STATUS_EXPIRED
            )
            approval.status = ApprovalRequest.STATUS_EXPIRED
        raise ApprovalAccessError("Approval request has expired.", 403)
    active_run_statuses = {
        PipelineRun.STATUS_PENDING,
        PipelineRun.STATUS_RUNNING,
        PipelineRun.STATUS_HIBERNATING,
    }
    if approval.run.status not in active_run_statuses:
        if approval.status == ApprovalRequest.STATUS_PENDING:
            ApprovalRequest.objects.filter(pk=approval.pk, status=ApprovalRequest.STATUS_PENDING).update(
                status=ApprovalRequest.STATUS_EXPIRED
            )
            approval.status = ApprovalRequest.STATUS_EXPIRED
        raise ApprovalAccessError("Pipeline run is no longer active.", 409)


def get_approval_for_confirmation(
    *,
    run_id: int,
    node_id: str,
    user: User,
    raw_token: str,
) -> ApprovalRequest:
    approval = (
        ApprovalRequest.objects.select_related("run", "run__pipeline", "approver")
        .filter(run_id=run_id, node_id=node_id)
        .first()
    )
    if approval is None:
        raise ApprovalAccessError("Approval request not found.", 404)
    _validate_access(approval, user=user, raw_token=raw_token)
    return approval


@transaction.atomic
def record_approval_decision(
    *,
    run_id: int,
    node_id: str,
    user: User,
    raw_token: str,
    decision: str,
    response_text: str,
) -> tuple[ApprovalRequest, bool]:
    if decision not in {ApprovalRequest.STATUS_APPROVED, ApprovalRequest.STATUS_REJECTED}:
        raise ApprovalAccessError("Decision must be approved or rejected.")
    approval = (
        ApprovalRequest.objects.select_for_update(of=("self",))
        .select_related("run", "run__pipeline", "approver")
        .filter(run_id=run_id, node_id=node_id)
        .first()
    )
    if approval is None:
        raise ApprovalAccessError("Approval request not found.", 404)
    _validate_access(approval, user=user, raw_token=raw_token)
    if approval.status != ApprovalRequest.STATUS_PENDING:
        return approval, False

    approval.status = decision
    approval.response_text = str(response_text or "")[:4000]
    approval.decided_at = timezone.now()
    approval.decided_by = user
    approval.save(update_fields=["status", "response_text", "decided_at", "decided_by"])

    run = PipelineRun.objects.select_for_update().get(pk=run_id)
    node_state = dict((run.node_states or {}).get(node_id) or {})
    run.node_states[node_id] = {
        **node_state,
        "approval_decision": decision,
        "approval_response": approval.response_text,
        "approval_source": "assigned_approver",
        "approval_request_id": approval.pk,
        "decided_at": approval.decided_at.isoformat(),
    }
    run.save(update_fields=["node_states"])
    return approval, True
