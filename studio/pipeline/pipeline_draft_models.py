from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class PipelineDraftSession(models.Model):
    """Persistent AI-drafter session for building or editing Studio pipelines."""

    STATUS_DRAFTING = "drafting"
    STATUS_NEEDS_INPUT = "needs_input"
    STATUS_READY = "ready"
    STATUS_INVALID = "invalid"
    STATUS_BLOCKED = "blocked"
    STATUS_APPLIED = "applied"
    STATUS_DISCARDED = "discarded"
    STATUS_CHOICES = [
        (STATUS_DRAFTING, "Drafting"),
        (STATUS_NEEDS_INPUT, "Needs input"),
        (STATUS_READY, "Ready"),
        (STATUS_INVALID, "Invalid"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_DISCARDED, "Discarded"),
    ]

    INTENT_CREATE = "create"
    INTENT_EDIT = "edit"
    INTENT_VALIDATE = "validate"
    INTENT_FIX_RUN = "fix_run"
    INTENT_CHOICES = [
        (INTENT_CREATE, "Create"),
        (INTENT_EDIT, "Edit"),
        (INTENT_VALIDATE, "Validate"),
        (INTENT_FIX_RUN, "Fix run"),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pipeline_draft_sessions")
    source_pipeline = models.ForeignKey(
        "Pipeline",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="draft_sessions",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFTING)
    intent = models.CharField(max_length=20, choices=INTENT_CHOICES, default=INTENT_CREATE)
    title = models.CharField(max_length=200, blank=True, default="")
    user_goal = models.TextField(blank=True, default="")
    current_graph_snapshot = models.JSONField(default=dict, blank=True)
    selected_node_id = models.CharField(max_length=100, blank=True, default="")
    applied_pipeline = models.ForeignKey(
        "Pipeline",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_draft_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["owner", "-updated_at"], name="studio_draft_owner_upd_idx"),
            models.Index(fields=["source_pipeline", "-updated_at"], name="studio_draft_source_upd_idx"),
            models.Index(fields=["status"], name="studio_draft_status_idx"),
        ]

    def __str__(self):
        return self.title or f"Pipeline draft #{self.pk}"

    def latest_revision(self) -> PipelineDraftRevision | None:
        return self.revisions.order_by("-created_at", "-id").first()

    def to_dict(self, *, include_latest: bool = True) -> dict:
        latest = self.latest_revision() if include_latest else None
        return {
            "id": self.pk,
            "status": self.status,
            "intent": self.intent,
            "title": self.title,
            "user_goal": self.user_goal,
            "source_pipeline_id": self.source_pipeline_id,
            "applied_pipeline_id": self.applied_pipeline_id,
            "selected_node_id": self.selected_node_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "latest_revision": latest.to_dict() if latest else None,
        }


class PipelineDraftRevision(models.Model):
    """One AI-drafter proposal inside a PipelineDraftSession."""

    session = models.ForeignKey(PipelineDraftSession, on_delete=models.CASCADE, related_name="revisions")
    user_message = models.TextField(blank=True, default="")
    assistant_reply = models.TextField(blank=True, default="")
    target_node_id = models.CharField(max_length=100, blank=True, default="")
    node_patch = models.JSONField(default=dict, blank=True)
    graph_patch = models.JSONField(default=dict, blank=True)
    preview_nodes = models.JSONField(default=list, blank=True)
    preview_edges = models.JSONField(default=list, blank=True)
    validation = models.JSONField(default=dict, blank=True)
    risk = models.JSONField(default=dict, blank=True)
    requirements = models.JSONField(default=list, blank=True)
    assumptions = models.JSONField(default=list, blank=True)
    questions = models.JSONField(default=list, blank=True)
    resource_plan = models.JSONField(default=dict, blank=True)
    node_explanations = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    patch_summary = models.TextField(blank=True, default="")
    suggested_next_actions = models.JSONField(default=list, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="studio_draft_rev_session_idx"),
        ]

    def __str__(self):
        return f"{self.session_id} revision #{self.pk}"

    def to_dict(self) -> dict:
        from studio.pipeline.pipeline_secrets import redact_pipeline_nodes, redact_pipeline_secret_values

        response = dict(self.response_payload or {})
        response.setdefault("reply", self.assistant_reply)
        response.setdefault("target_node_id", self.target_node_id or None)
        response.setdefault("node_patch", self.node_patch or {})
        response.setdefault("graph_patch", self.graph_patch or {})
        response.setdefault("validation", self.validation or {})
        response.setdefault("risk", self.risk or {})
        response.setdefault("requirements", self.requirements or [])
        response.setdefault("assumptions", self.assumptions or [])
        response.setdefault("questions", self.questions or [])
        response.setdefault("resource_plan", self.resource_plan or {})
        response.setdefault("node_explanations", self.node_explanations or {})
        response.setdefault("warnings", self.warnings or [])
        response.setdefault("patch_summary", self.patch_summary)
        response.setdefault("suggested_next_actions", self.suggested_next_actions or [])
        response.setdefault("confidence", self.confidence)
        response = redact_pipeline_secret_values(response)
        return {
            "id": self.pk,
            "session_id": self.session_id,
            "user_message": self.user_message,
            "created_at": self.created_at.isoformat(),
            "preview_nodes": redact_pipeline_nodes(self.preview_nodes),
            "preview_edges": self.preview_edges,
            "response": response,
        }
