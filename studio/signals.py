"""Lifecycle cleanup for Studio-owned managed secrets."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from core_ui.managed_secrets import delete_studio_pipeline_secrets
from studio.models import Pipeline


@receiver(post_delete, sender=Pipeline)
def delete_pipeline_managed_secrets(*, instance: Pipeline, **_kwargs: object) -> None:
    delete_studio_pipeline_secrets(instance.pk)
