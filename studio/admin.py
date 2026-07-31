from django.contrib import admin

from .models import (
    AgentConfig,
    ApprovalRequest,
    MCPServerPool,
    Pipeline,
    PipelineDraftRevision,
    PipelineDraftSession,
    PipelineNodeDeadLetter,
    PipelineRun,
    PipelineRunDispatch,
    PipelineTemplate,
    PipelineTrigger,
    PipelineWebhookDelivery,
    TelegramBotCursor,
    TelegramReplyRequest,
)


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ["run", "node_id", "approver", "status", "expires_at", "decided_at"]
    list_filter = ["status", "expires_at"]
    search_fields = ["run__pipeline__name", "node_id", "approver__username"]
    readonly_fields = ["token_digest", "created_at", "decided_at"]


@admin.register(TelegramBotCursor)
class TelegramBotCursorAdmin(admin.ModelAdmin):
    list_display = ["bot_token_digest", "update_offset", "updated_at"]
    readonly_fields = ["bot_token_digest", "update_offset", "updated_at"]


@admin.register(TelegramReplyRequest)
class TelegramReplyRequestAdmin(admin.ModelAdmin):
    list_display = ["run", "node_id", "chat_id", "prompt_message_id", "status", "expires_at"]
    list_filter = ["status", "expires_at"]
    search_fields = ["run__pipeline__name", "node_id", "chat_id"]
    readonly_fields = ["bot_token_digest", "created_at", "received_at"]


@admin.register(MCPServerPool)
class MCPServerPoolAdmin(admin.ModelAdmin):
    list_display = ["name", "transport", "owner", "is_shared", "last_test_ok", "created_at"]
    list_filter = ["transport", "is_shared", "last_test_ok"]
    search_fields = ["name", "command"]
    readonly_fields = ["last_test_ok", "last_test_at", "last_test_error"]


@admin.register(AgentConfig)
class AgentConfigAdmin(admin.ModelAdmin):
    list_display = ["name", "model", "owner", "is_shared", "max_iterations", "updated_at"]
    list_filter = ["model", "is_shared"]
    search_fields = ["name", "system_prompt"]
    filter_horizontal = ["mcp_servers", "server_scope"]


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "is_shared", "is_template", "updated_at"]
    list_filter = ["is_shared", "is_template"]
    search_fields = ["name", "description"]


@admin.register(PipelineTrigger)
class PipelineTriggerAdmin(admin.ModelAdmin):
    list_display = ["pipeline", "trigger_type", "is_active", "last_triggered_at"]
    list_filter = ["trigger_type", "is_active"]
    readonly_fields = ["webhook_token", "last_triggered_at"]


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ["pipeline", "status", "triggered_by", "started_at", "finished_at"]
    list_filter = ["status"]
    readonly_fields = ["started_at", "finished_at", "created_at", "node_states"]


@admin.register(PipelineRunDispatch)
class PipelineRunDispatchAdmin(admin.ModelAdmin):
    list_display = ["run", "status", "claimed_by", "attempt_count", "max_attempts", "queued_at"]
    list_filter = ["status", "queued_at"]
    search_fields = ["run__pipeline__name", "claimed_by"]
    readonly_fields = ["queued_at", "claimed_at", "heartbeat_at", "lease_expires_at", "completed_at"]


@admin.register(PipelineNodeDeadLetter)
class PipelineNodeDeadLetterAdmin(admin.ModelAdmin):
    list_display = ["run", "node_id", "node_type", "status", "attempt_count", "max_attempts", "created_at"]
    list_filter = ["status", "node_type", "created_at"]
    search_fields = ["run__pipeline__name", "node_id", "last_error"]
    readonly_fields = ["run", "node_id", "node_type", "attempt_count", "max_attempts", "created_at", "updated_at"]


@admin.register(PipelineWebhookDelivery)
class PipelineWebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ["trigger", "delivery_id", "run", "received_at"]
    search_fields = ["delivery_id", "body_sha256"]
    readonly_fields = ["trigger", "delivery_id", "body_sha256", "run", "received_at"]


@admin.register(PipelineDraftSession)
class PipelineDraftSessionAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "source_pipeline", "status", "intent", "updated_at"]
    list_filter = ["status", "intent", "created_at"]
    search_fields = ["title", "user_goal"]
    readonly_fields = ["created_at", "updated_at", "applied_at"]


@admin.register(PipelineDraftRevision)
class PipelineDraftRevisionAdmin(admin.ModelAdmin):
    list_display = ["session", "patch_summary", "created_at"]
    list_filter = ["created_at"]
    readonly_fields = ["created_at"]


@admin.register(PipelineTemplate)
class PipelineTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "slug", "created_at"]
    list_filter = ["category"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
