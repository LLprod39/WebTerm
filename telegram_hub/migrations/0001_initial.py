# Generated manually for telegram_hub models.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core_ui", "0034_chatsession_kind_telegram"),
        ("studio", "0021_pipelinerun_provider_execution_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramBot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("platform", "Platform"), ("personal", "Personal")], default="personal", max_length=20)),
                ("name", models.CharField(blank=True, default="", max_length=120)),
                ("bot_username", models.CharField(blank=True, default="", max_length=64)),
                ("bot_user_id", models.BigIntegerField(blank=True, null=True)),
                ("token_digest", models.CharField(db_index=True, max_length=64, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("mode", models.CharField(choices=[("assistant", "AI Assistant"), ("pipeline", "Pipeline")], default="assistant", max_length=20)),
                ("system_prompt", models.TextField(blank=True, default="")),
                ("provider_binding", models.JSONField(blank=True, default=dict)),
                ("allow_group_chats", models.BooleanField(default=False)),
                ("allowed_chat_ids", models.JSONField(blank=True, default=list, help_text="Optional allowlist of Telegram chat ids for pipeline mode.")),
                ("last_poll_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="telegram_bots", to=settings.AUTH_USER_MODEL)),
                ("pipeline", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="telegram_bots", to="studio.pipeline")),
            ],
        ),
        migrations.CreateModel(
            name="TelegramAccountLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_user_id", models.BigIntegerField()),
                ("chat_id", models.CharField(max_length=64)),
                ("username", models.CharField(blank=True, default="", max_length=150)),
                ("status", models.CharField(choices=[("linked", "Linked"), ("revoked", "Revoked")], default="linked", max_length=20)),
                ("linked_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("bot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="account_links", to="telegram_hub.telegrambot")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_account_links", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="TelegramLinkCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code_digest", models.CharField(db_index=True, max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("bot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="link_codes", to="telegram_hub.telegrambot")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_link_codes", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="TelegramChatBinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("chat_session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_bindings", to="core_ui.chatsession")),
                ("link", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_bindings", to="telegram_hub.telegramaccountlink")),
            ],
        ),
        migrations.AddIndex(
            model_name="telegrambot",
            index=models.Index(fields=["is_active", "kind"], name="telegram_hu_is_acti_fb5fea_idx"),
        ),
        migrations.AddIndex(
            model_name="telegrambot",
            index=models.Index(fields=["owner", "is_active"], name="telegram_hu_owner_i_008958_idx"),
        ),
        migrations.AddIndex(
            model_name="telegramaccountlink",
            index=models.Index(fields=["user", "status"], name="telegram_hu_user_id_09ce5c_idx"),
        ),
        migrations.AddIndex(
            model_name="telegramaccountlink",
            index=models.Index(fields=["bot", "status"], name="telegram_hu_bot_id_0d5af6_idx"),
        ),
        migrations.AddIndex(
            model_name="telegramaccountlink",
            index=models.Index(fields=["chat_id"], name="telegram_hu_chat_id_6b7697_idx"),
        ),
        migrations.AddConstraint(
            model_name="telegramaccountlink",
            constraint=models.UniqueConstraint(fields=("bot", "telegram_user_id"), name="uniq_tg_link_bot_user"),
        ),
        migrations.AddIndex(
            model_name="telegramlinkcode",
            index=models.Index(fields=["user", "created_at"], name="telegram_hu_user_id_e3bc45_idx"),
        ),
        migrations.AddIndex(
            model_name="telegramlinkcode",
            index=models.Index(fields=["bot", "expires_at"], name="telegram_hu_bot_id_5de494_idx"),
        ),
        migrations.AddIndex(
            model_name="telegramchatbinding",
            index=models.Index(fields=["link", "is_active"], name="telegram_hu_link_id_1d5639_idx"),
        ),
    ]
