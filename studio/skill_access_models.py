from django.contrib.auth.models import User
from django.db import models


class StudioSkillAccess(models.Model):
    """Ownership and sharing metadata for filesystem-backed Studio skills."""

    slug = models.SlugField(max_length=100, unique=True)
    owner = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_studio_skills",
    )
    project = models.ForeignKey(
        "core_ui.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="studio_skill_access",
    )
    is_shared = models.BooleanField(default=False, help_text="Visible to all users with skill access")
    shared_with = models.ManyToManyField(
        User,
        blank=True,
        related_name="shared_studio_skills",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]
        verbose_name = "Studio Skill Access"
        verbose_name_plural = "Studio Skill Access"

    def __str__(self):
        return self.slug

    def save(self, *args, **kwargs):
        if self.owner_id:
            from core_ui.projects import assign_active_project

            assign_active_project(self, user_field="owner")
        return super().save(*args, **kwargs)
