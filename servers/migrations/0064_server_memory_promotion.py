import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0063_server_memory_assets_acl_retrieval"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ServerMemoryPromotion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "destination_kind",
                    models.CharField(
                        choices=[
                            ("playbook_revision", "Playbook Revision"),
                            ("studio_skill", "Studio Skill"),
                            ("knowledge_note", "Knowledge Note"),
                        ],
                        max_length=32,
                    ),
                ),
                ("skill_slug", models.CharField(blank=True, default="", max_length=120)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("requested", "Requested"),
                            ("draft_created", "Draft Created"),
                            ("validated", "Validated"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("failed", "Failed"),
                        ],
                        default="requested",
                        max_length=24,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=64, unique=True)),
                ("validation_result", models.JSONField(blank=True, default=dict)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("draft_created_at", models.DateTimeField(blank=True, null=True)),
                ("validated_at", models.DateTimeField(blank=True, null=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approved_server_memory_promotions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "generation_log",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="promotions",
                        to="servers.servermemorygenerationlog",
                    ),
                ),
                (
                    "knowledge_note",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="memory_promotions",
                        to="servers.serverknowledge",
                    ),
                ),
                (
                    "playbook",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="memory_promotions",
                        to="servers.playbook",
                    ),
                ),
                (
                    "playbook_revision",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="memory_promotions",
                        to="servers.playbookrevision",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requested_server_memory_promotions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="promotions",
                        to="servers.servermemoryasset",
                    ),
                ),
                (
                    "source_snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="promotions",
                        to="servers.servermemorysnapshot",
                    ),
                ),
            ],
            options={
                "ordering": ["-requested_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["source_asset", "status", "-requested_at"],
                        name="mem_prom_src_status_idx",
                    ),
                    models.Index(
                        fields=["requested_by", "status", "-requested_at"],
                        name="mem_prom_actor_status_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("destination_kind", "playbook_revision"),
                                ("knowledge_note__isnull", True),
                                ("playbook__isnull", False),
                            ),
                            models.Q(
                                ("destination_kind", "studio_skill"),
                                ("knowledge_note__isnull", True),
                                ("playbook__isnull", True),
                                ("playbook_revision__isnull", True),
                            ),
                            models.Q(
                                ("destination_kind", "knowledge_note"),
                                ("playbook__isnull", True),
                                ("playbook_revision__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="mem_prom_destination_refs",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("playbook_revision__isnull", True),
                            ("playbook__isnull", False),
                            _connector="OR",
                        ),
                        name="mem_prom_revision_playbook",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("status", "approved"), _negated=True),
                            models.Q(("approved_by__isnull", False), ("decided_at__isnull", False)),
                            _connector="OR",
                        ),
                        name="mem_prom_approved_actor",
                    ),
                ],
            },
        ),
    ]
