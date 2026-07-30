"""Lifecycle cleanup for Studio-owned managed secrets."""

from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver

from core_ui.managed_secrets import delete_studio_pipeline_secrets
from core_ui.models.projects import ProjectMembership
from studio.models import AgentConfig, MCPServerPool, Pipeline, StudioSkillAccess


@receiver(post_delete, sender=Pipeline)
def delete_pipeline_managed_secrets(*, instance: Pipeline, **_kwargs: object) -> None:
    delete_studio_pipeline_secrets(instance.pk)


def _enforce_same_project(instance, model, pk_set) -> None:
    if pk_set and model.objects.filter(pk__in=pk_set).exclude(project_id=instance.project_id).exists():
        raise ValidationError("Studio resources must belong to the same project")


@receiver(m2m_changed, sender=AgentConfig.mcp_servers.through)
def enforce_agent_mcp_project(sender, instance, action: str, reverse: bool, pk_set, model, **kwargs):
    if action != "pre_add":
        return
    _enforce_same_project(instance, model, pk_set)


@receiver(m2m_changed, sender=AgentConfig.server_scope.through)
def enforce_agent_server_scope_project(sender, instance, action: str, reverse: bool, pk_set, model, **kwargs):
    if action != "pre_add":
        return
    _enforce_same_project(instance, model, pk_set)


def _enforce_shared_users_are_members(instance, action: str, reverse: bool, pk_set, model) -> None:
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        if model.objects.filter(pk__in=pk_set).exclude(project__memberships__user=instance).exists():
            raise ValidationError("Shared users must belong to the resource project")
        return
    if instance.project_id is None:
        return
    member_ids = set(
        ProjectMembership.objects.filter(project_id=instance.project_id, user_id__in=pk_set).values_list(
            "user_id", flat=True
        )
    )
    if set(pk_set) - member_ids:
        raise ValidationError("Shared users must belong to the resource project")


@receiver(m2m_changed, sender=MCPServerPool.shared_with.through)
@receiver(m2m_changed, sender=AgentConfig.shared_with.through)
@receiver(m2m_changed, sender=Pipeline.shared_with.through)
@receiver(m2m_changed, sender=StudioSkillAccess.shared_with.through)
def enforce_studio_share_project(sender, instance, action: str, reverse: bool, pk_set, model, **kwargs):
    _enforce_shared_users_are_members(instance, action, reverse, pk_set, model)
