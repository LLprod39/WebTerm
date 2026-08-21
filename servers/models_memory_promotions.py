"""Auditable promotion ledger for approved server-memory assets."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from servers.models_knowledge import ServerKnowledge
from servers.models_memory import ServerMemoryGenerationLog, ServerMemorySnapshot
from servers.models_memory_assets import ServerMemoryAsset
from servers.models_playbook_workspace import PlaybookRevision
from servers.models_playbooks import Playbook


class ServerMemoryPromotion(models.Model):
    DESTINATION_PLAYBOOK_REVISION = "playbook_revision"
    DESTINATION_STUDIO_SKILL = "studio_skill"
    DESTINATION_KNOWLEDGE_NOTE = "knowledge_note"
    DESTINATION_CHOICES = [
        (DESTINATION_PLAYBOOK_REVISION, "Playbook Revision"),
        (DESTINATION_STUDIO_SKILL, "Studio Skill"),
        (DESTINATION_KNOWLEDGE_NOTE, "Knowledge Note"),
    ]

    STATUS_REQUESTED = "requested"
    STATUS_DRAFT_CREATED = "draft_created"
    STATUS_VALIDATED = "validated"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Requested"),
        (STATUS_DRAFT_CREATED, "Draft Created"),
        (STATUS_VALIDATED, "Validated"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FAILED, "Failed"),
    ]

    source_asset = models.ForeignKey(ServerMemoryAsset, on_delete=models.PROTECT, related_name="promotions")
    source_snapshot = models.ForeignKey(ServerMemorySnapshot, on_delete=models.PROTECT, related_name="promotions")
    destination_kind = models.CharField(max_length=32, choices=DESTINATION_CHOICES)
    playbook = models.ForeignKey(
        Playbook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_promotions",
    )
    playbook_revision = models.ForeignKey(
        PlaybookRevision,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_promotions",
    )
    knowledge_note = models.ForeignKey(
        ServerKnowledge,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_promotions",
    )
    skill_slug = models.CharField(max_length=120, blank=True, default="")
    generation_log = models.ForeignKey(
        ServerMemoryGenerationLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotions",
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    idempotency_key = models.CharField(max_length=64, unique=True)
    validation_result = models.JSONField(default=dict, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_server_memory_promotions",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_server_memory_promotions",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    draft_created_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at", "-id"]
        indexes = [
            models.Index(fields=["source_asset", "status", "-requested_at"], name="mem_prom_src_status_idx"),
            models.Index(fields=["requested_by", "status", "-requested_at"], name="mem_prom_actor_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(destination_kind="playbook_revision", playbook__isnull=False, knowledge_note__isnull=True)
                    | models.Q(
                        destination_kind="studio_skill",
                        playbook__isnull=True,
                        playbook_revision__isnull=True,
                        knowledge_note__isnull=True,
                    )
                    | models.Q(
                        destination_kind="knowledge_note",
                        playbook__isnull=True,
                        playbook_revision__isnull=True,
                    )
                ),
                name="mem_prom_destination_refs",
            ),
            models.CheckConstraint(
                condition=models.Q(playbook_revision__isnull=True) | models.Q(playbook__isnull=False),
                name="mem_prom_revision_playbook",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status="approved")
                    | models.Q(approved_by__isnull=False, decided_at__isnull=False)
                ),
                name="mem_prom_approved_actor",
            ),
        ]

    def __str__(self) -> str:
        return f"Memory promotion {self.pk}: {self.destination_kind} ({self.status})"
