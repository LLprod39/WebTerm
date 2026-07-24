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
