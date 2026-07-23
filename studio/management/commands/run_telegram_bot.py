"""
run_telegram_bot — Long-poll Telegram and fire a pipeline run for each new message.

The bot does NOT need a public server or webhook URL. It uses Telegram's
getUpdates long-polling API and runs entirely inside Django.

Usage:
    python manage.py run_telegram_bot
    python manage.py run_telegram_bot --pipeline-id 91
    python manage.py run_telegram_bot --bot-token "123456:ABC-DEF..."

Prerequisites:
    1. python manage.py setup_telegram_bot_pipeline
    2. Set TELEGRAM_BOT_TOKEN in .env  (or Studio → Notifications)
    3. python manage.py run_telegram_bot   ← just run this
"""

from __future__ import annotations

import asyncio
import time

import httpx
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from app.background_workers import STUDIO_TELEGRAM_BOT_WORKER
from app.runtime_limits import get_pipeline_run_limit_error
from app.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker
from studio.models import Pipeline, PipelineTrigger


class Command(BaseCommand):
    help = "Long-poll Telegram and trigger the Server Agent pipeline for each new message."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pipeline-id",
            type=int,
            default=None,
            dest="pipeline_id",
            help="Pipeline ID to use (default: auto-detect 'Telegram Bot — Server Agent').",
        )
        parser.add_argument(
            "--bot-token",
            type=str,
            default=None,
            dest="bot_token",
            help="Telegram bot token (default: TELEGRAM_BOT_TOKEN from .env or Studio Notifications).",
        )
        parser.add_argument(
            "--poll-timeout",
            type=int,
            default=25,
            dest="poll_timeout",
            help="Telegram long-poll timeout seconds (default: 25).",
        )
        parser.add_argument("--lease-seconds", type=int, default=180, help="Worker heartbeat lease duration")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key")
        parser.add_argument("--max-polls", type=int, default=0, help="Stop after N polls, mainly for smoke tests")

    def handle(self, *args, **options):
        from studio.pipeline_notifications import _load_notif_cfg

        bot_token = (options.get("bot_token") or "").strip() or _load_notif_cfg().get("telegram_bot_token", "")
        if not bot_token:
            raise CommandError(
                "No Telegram bot token found.\n\n"
                "  Option A: add to .env\n"
                "    TELEGRAM_BOT_TOKEN=<your_bot_token>\n\n"
                "  Option B: Studio → Notifications → set Telegram bot token\n\n"
                "  Get a token from @BotFather in Telegram."
            )

        pipeline, trigger = self._resolve_pipeline(options.get("pipeline_id"))
        poll_timeout = max(5, min(30, int(options.get("poll_timeout") or 25)))
        lease_seconds = max(30, int(options.get("lease_seconds") or 180))
        worker_key = str(options.get("worker_key") or "default").strip() or "default"
        max_polls = max(0, int(options.get("max_polls") or 0))

        state = claim_background_worker(
            STUDIO_TELEGRAM_BOT_WORKER,
            worker_key=worker_key,
            command="python manage.py run_telegram_bot",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(
                self.style.WARNING(f"Telegram bot worker {worker_key!r} is already leased by another process")
            )
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✅ Telegram bot started"))
        self.stdout.write(f"   Pipeline : {pipeline.name}  (ID={pipeline.id})")
        self.stdout.write("   Bot token: configured")
        self.stdout.write(f"   Poll      : {poll_timeout}s long-poll")
        self.stdout.write("")
        self.stdout.write("Send any message to your bot in Telegram.")
        self.stdout.write("Press Ctrl+C to stop.\n")

        offset = 0
        summary = {"polls": 0, "updates": 0, "runs_created": 0, "replies_routed": 0, "ignored": 0, "errors": 0}
        try:
            while True:
                try:
                    summary["polls"] += 1
                    heartbeat_background_worker(
                        STUDIO_TELEGRAM_BOT_WORKER,
                        worker_key=worker_key,
                        lease_seconds=lease_seconds,
                        summary=summary,
                        cycle_started=True,
                    )
                    updates, offset = asyncio.run(self._get_updates(bot_token, offset, poll_timeout))
                    summary["updates"] += len(updates)
                    for update in updates:
                        result = self._handle_update(update, bot_token, pipeline, trigger)
                        if result == "launched":
                            summary["runs_created"] += 1
                        elif result == "reply":
                            summary["replies_routed"] += 1
                        else:
                            summary["ignored"] += 1
                    heartbeat_background_worker(
                        STUDIO_TELEGRAM_BOT_WORKER,
                        worker_key=worker_key,
                        lease_seconds=lease_seconds,
                        summary=summary,
                        cycle_finished=True,
                    )
                    if max_polls and summary["polls"] >= max_polls:
                        break
                except KeyboardInterrupt:
                    self.stdout.write("\nBot stopped.")
                    break
                except Exception as exc:
                    summary["errors"] += 1
                    heartbeat_background_worker(
                        STUDIO_TELEGRAM_BOT_WORKER,
                        worker_key=worker_key,
                        lease_seconds=lease_seconds,
                        summary=summary | {"last_error": str(exc)[:300]},
                        cycle_finished=True,
                    )
                    self.stderr.write(f"Poll error (retrying in 5s): {exc}")
                    time.sleep(5)
        finally:
            stop_background_worker(STUDIO_TELEGRAM_BOT_WORKER, worker_key=worker_key, summary=summary)

    def _resolve_pipeline(self, pipeline_id: int | None):
        if pipeline_id:
            pipeline = Pipeline.objects.filter(id=pipeline_id).first()
            if not pipeline:
                raise CommandError(f"Pipeline #{pipeline_id} not found.")
        else:
            from studio.services.telegram_bot_pipeline import TELEGRAM_BOT_PIPELINE_NAME

            pipeline = Pipeline.objects.filter(name=TELEGRAM_BOT_PIPELINE_NAME).order_by("-id").first()
            if not pipeline:
                raise CommandError(
                    f'Pipeline "{TELEGRAM_BOT_PIPELINE_NAME}" not found.\n'
                    "Run this first:\n"
                    "  python manage.py setup_telegram_bot_pipeline"
                )

        trigger = (
            pipeline.triggers.filter(trigger_type=PipelineTrigger.TYPE_WEBHOOK, is_active=True).order_by("id").first()
        )
        if not trigger:
            raise CommandError(
                f'Pipeline "{pipeline.name}" has no active webhook trigger.\n'
                "Recreate it with: python manage.py setup_telegram_bot_pipeline"
            )
        return pipeline, trigger

    async def _get_updates(self, bot_token: str, offset: int, poll_timeout: int) -> tuple[list, int]:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        async with httpx.AsyncClient(timeout=poll_timeout + 10) as client:
            resp = await client.post(
                url,
                json={
                    "offset": offset,
                    "timeout": poll_timeout,
                    "allowed_updates": ["message"],
                },
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Telegram API {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data.get('description', data)}")

        updates: list = data.get("result") or []
        new_offset = offset
        for update in updates:
            uid = update.get("update_id")
            if isinstance(uid, int) and uid + 1 > new_offset:
                new_offset = uid + 1
        return updates, new_offset

    def _handle_update(self, update: dict, bot_token: str, pipeline: Pipeline, trigger: PipelineTrigger) -> str:
        message = update.get("message") or {}
        if not isinstance(message, dict):
            return "ignored"

        if message.get("reply_to_message"):
            from studio.pipeline_telegram import store_telegram_operator_reply

            if store_telegram_operator_reply(bot_token, message):
                ts = timezone.now().strftime("%H:%M:%S")
                chat = message.get("chat") or {}
                self.stdout.write(f"[{ts}] chat={chat.get('id')}  reply routed to waiting pipeline")
                return "reply"
            return "ignored"

        text = str(message.get("text") or "").strip()
        if not text:
            return "ignored"

        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        chat_id = str(chat.get("id") or "").strip()
        if not chat_id:
            return "ignored"

        context = {
            "user_task": text,
            "tg_chat_id": chat_id,
            "tg_user_name": str(from_user.get("first_name") or from_user.get("username") or "User"),
            "tg_message_id": str(message.get("message_id") or ""),
        }

        limit_error = get_pipeline_run_limit_error(pipeline.owner)
        if limit_error:
            self.stderr.write(f"Run limit exceeded: {limit_error.get('error')}")
            return "ignored"

        from studio.pipeline_validation import validate_pipeline_definition

        errors = validate_pipeline_definition(
            nodes=pipeline.nodes,
            edges=pipeline.edges,
            owner=pipeline.owner,
            graph_version=pipeline.graph_version,
        )
        if errors:
            self.stderr.write(f"Pipeline validation failed — fix it in Studio: {errors[:2]}")
            return "ignored"

        from studio.pipeline_runtime_context import validate_pipeline_entry_branch, validate_pipeline_runtime_context

        branch_errors = validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, trigger.node_id)
        if branch_errors:
            self.stderr.write(f"Pipeline entry branch failed — fix it in Studio: {branch_errors[:2]}")
            return "ignored"
        context_errors = validate_pipeline_runtime_context(
            pipeline.nodes,
            context,
            edges=pipeline.edges,
            entry_node_id=trigger.node_id,
        )
        if context_errors:
            self.stderr.write(f"Pipeline runtime context failed — fix it in Studio: {context_errors[:2]}")
            return "ignored"

        from studio.trigger_dispatch import (
            create_pipeline_run,
            launch_pipeline_run_async,
            pipeline_run_creation_error_details,
        )

        try:
            run = create_pipeline_run(
                pipeline=pipeline,
                trigger=trigger,
                context=context,
                trigger_data={
                    "source": "telegram_polling",
                    "chat_id": chat_id,
                    "text": text[:500],
                },
                entry_node_id=trigger.node_id,
            )
        except ValueError as exc:
            self.stderr.write(
                f"Pipeline run creation failed — fix it in Studio: {pipeline_run_creation_error_details(exc)[:2]}"
            )
            return "ignored"
        trigger.last_triggered_at = timezone.now()
        trigger.save(update_fields=["last_triggered_at"])
        launch_pipeline_run_async(run)

        ts = timezone.now().strftime("%H:%M:%S")
        preview = text[:60] + ("…" if len(text) > 60 else "")
        self.stdout.write(f"[{ts}] chat={chat_id}  msg={preview!r}  → run #{run.pk}")
        return "launched"
