"""
Create or update the Telegram Bot — Server Agent pipeline.

Usage:
    python manage.py setup_telegram_bot_pipeline
    python manage.py setup_telegram_bot_pipeline --username myuser

After running, follow the printed instructions to:
  1. Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in Studio → Notifications.
  2. Register the webhook URL with Telegram's setWebhook API.
  3. Send a message to your bot — the pipeline runs automatically.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from studio.services.telegram_bot_pipeline import ensure_telegram_bot_pipeline


class Command(BaseCommand):
    help = "Create or update the Telegram Bot — Server Agent pipeline for a user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="User to own the pipeline (default: first superuser or first user).",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("username"))
        pipeline = ensure_telegram_bot_pipeline(user)
        trigger = pipeline.triggers.filter(trigger_type="webhook", is_active=True).order_by("created_at", "id").first()
        if trigger is None:
            raise CommandError("Webhook trigger was not created for the pipeline.")

        webhook_path = f"/api/studio/triggers/{trigger.webhook_token}/receive/"

        self.stdout.write(
            self.style.SUCCESS(f'\nPipeline "{pipeline.name}" ready (ID={pipeline.id}) for user {user.username}.')
        )
        self.stdout.write("")
        self.stdout.write("=" * 65)
        self.stdout.write("  SETUP — 3 steps to activate the Telegram bot")
        self.stdout.write("=" * 65)
        self.stdout.write("")
        self.stdout.write("STEP 1 — Create a Telegram bot (if you don't have one):")
        self.stdout.write("  1. Open Telegram → search @BotFather → /newbot")
        self.stdout.write("  2. Copy the bot token (looks like 123456:ABC-DEF...)")
        self.stdout.write("  3. Send /start to your bot to get your chat_id")
        self.stdout.write("     (or use @userinfobot to find your chat ID)")
        self.stdout.write("")
        self.stdout.write("STEP 2 — Configure Telegram credentials in the platform:")
        self.stdout.write("  Option A: Studio → Notifications → set bot token + chat ID")
        self.stdout.write("  Option B: add to .env:")
        self.stdout.write("    TELEGRAM_BOT_TOKEN=<your_bot_token>")
        self.stdout.write("    TELEGRAM_CHAT_ID=<your_chat_id>")
        self.stdout.write("")
        self.stdout.write("STEP 3 — Register the webhook with Telegram:")
        self.stdout.write("  Replace YOUR_DOMAIN and YOUR_BOT_TOKEN below, then run:")
        self.stdout.write("")
        self.stdout.write("  curl -X POST https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook \\")
        self.stdout.write(f'    -d \'{{"url": "https://YOUR_DOMAIN{webhook_path}"}}\'')
        self.stdout.write("")
        self.stdout.write("  Your webhook path:")
        self.stdout.write(f"    {webhook_path}")
        self.stdout.write("")
        self.stdout.write("DONE — Open the pipeline in Studio:")
        self.stdout.write(f"  /studio/pipeline/{pipeline.id}")
        self.stdout.write("")
        self.stdout.write("  Now send any message to your Telegram bot.")
        self.stdout.write("  The pipeline will run and reply in Telegram.")
        self.stdout.write("")

    def _resolve_user(self, username: str | None):
        User = get_user_model()
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                raise CommandError(f"User '{username}' not found.")
            return user
        user = User.objects.filter(is_superuser=True).order_by("id").first()
        if user:
            return user
        user = User.objects.order_by("id").first()
        if user:
            return user
        raise CommandError("No users found in the database. Run: python manage.py createsuperuser")
