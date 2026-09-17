from django.contrib import admin

from telegram_hub.models import TelegramAccountLink, TelegramBot, TelegramChatBinding, TelegramLinkCode


@admin.register(TelegramBot)
class TelegramBotAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "bot_username", "owner", "mode", "is_active", "last_poll_at")
    list_filter = ("kind", "mode", "is_active")
    search_fields = ("bot_username", "name", "token_digest")
    readonly_fields = ("token_digest", "last_poll_at", "last_error", "created_at", "updated_at")


@admin.register(TelegramAccountLink)
class TelegramAccountLinkAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "bot", "telegram_user_id", "chat_id", "status", "linked_at")
    list_filter = ("status",)
    search_fields = ("username", "chat_id", "telegram_user_id")


@admin.register(TelegramLinkCode)
class TelegramLinkCodeAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "bot", "expires_at", "used_at", "created_at")
    readonly_fields = ("code_digest",)


@admin.register(TelegramChatBinding)
class TelegramChatBindingAdmin(admin.ModelAdmin):
    list_display = ("id", "link", "chat_session", "is_active", "updated_at")
