"""Signal handlers for Telegram hub."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone


@receiver(pre_save, sender=User)
def revoke_telegram_links_on_deactivate(sender, instance: User, **kwargs):
    """Revoke all Telegram links when a user transitions active → inactive."""
    if kwargs.get("raw") or not instance.pk or instance.is_active:
        return
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "is_active" not in update_fields:
        return
    was_active = User.objects.filter(pk=instance.pk, is_active=True).exists()
    if not was_active:
        return
    from telegram_hub.models import TelegramAccountLink

    TelegramAccountLink.objects.filter(
        user_id=instance.pk,
        status=TelegramAccountLink.STATUS_LINKED,
    ).update(status=TelegramAccountLink.STATUS_REVOKED, revoked_at=timezone.now())
