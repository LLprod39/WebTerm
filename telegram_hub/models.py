"""Telegram hub models: bots, account links, link codes, chat bindings."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class TelegramBot(models.Model):
    KIND_PLATFORM = "platform"
    KIND_PERSONAL = "personal"
    KIND_CHOICES = [
        (KIND_PLATFORM, "Platform"),
        (KIND_PERSONAL, "Personal"),
    ]

    MODE_ASSISTANT = "assistant"
    MODE_PIPELINE = "pipeline"
    MODE_CHOICES = [
        (MODE_ASSISTANT, "AI Assistant"),
        (MODE_PIPELINE, "Pipeline"),
    ]

    owner = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="telegram_bots",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_PERSONAL)
    name = models.CharField(max_length=120, blank=True, default="")
    bot_username = models.CharField(max_length=64, blank=True, default="")
    bot_user_id = models.BigIntegerField(null=True, blank=True)
    token_digest = models.CharField(max_length=64, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_ASSISTANT)
    pipeline = models.ForeignKey(
        "studio.Pipeline",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="telegram_bots",
    )
    system_prompt = models.TextField(blank=True, default="")
    provider_binding = models.JSONField(default=dict, blank=True)
    allow_group_chats = models.BooleanField(default=False)
    allowed_chat_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional allowlist of Telegram chat ids for pipeline mode.",
    )
    last_poll_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "kind"]),
            models.Index(fields=["owner", "is_active"]),
        ]

    def __str__(self) -> str:
        label = self.bot_username or self.name or f"bot#{self.pk}"
        return f"{self.kind}:{label}"


class TelegramAccountLink(models.Model):
    STATUS_LINKED = "linked"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = [
        (STATUS_LINKED, "Linked"),
        (STATUS_REVOKED, "Revoked"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="telegram_account_links")
    bot = models.ForeignKey(TelegramBot, on_delete=models.CASCADE, related_name="account_links")
    telegram_user_id = models.BigIntegerField()
    chat_id = models.CharField(max_length=64)
    username = models.CharField(max_length=150, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_LINKED)
    linked_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["bot", "telegram_user_id"], name="uniq_tg_link_bot_user"),
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["bot", "status"]),
            models.Index(fields=["chat_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}↔{self.telegram_user_id}@{self.bot_id}"


class TelegramLinkCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="telegram_link_codes")
    bot = models.ForeignKey(TelegramBot, on_delete=models.CASCADE, related_name="link_codes")
    code_digest = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["bot", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"link_code user={self.user_id} bot={self.bot_id}"


class TelegramChatBinding(models.Model):
    link = models.ForeignKey(TelegramAccountLink, on_delete=models.CASCADE, related_name="chat_bindings")
    chat_session = models.ForeignKey(
        "core_ui.ChatSession",
        on_delete=models.CASCADE,
        related_name="telegram_bindings",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["link", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"binding link={self.link_id} session={self.chat_session_id}"
