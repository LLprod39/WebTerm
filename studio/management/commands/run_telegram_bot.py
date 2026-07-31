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
    2. Set TELEGRAM_BOT_POLL_TOKEN in .env (or Studio → Notifications)
    3. python manage.py run_telegram_bot   ← just run this
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time

import httpx
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from app.background_workers import STUDIO_TELEGRAM_BOT_WORKER
from app.runtime_limits import get_pipeline_run_limit_error
from app.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker
from studio.models import Pipeline, PipelineTrigger
from studio.telegram_delivery_service import (
    advance_telegram_update_offset,
    get_telegram_update_offset,
    record_telegram_approval_callback,
    store_telegram_operator_reply,
    telegram_worker_key,
)


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
            help="Telegram bot token (default: TELEGRAM_BOT_POLL_TOKEN or Studio Notifications).",
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
        from studio.pipeline.pipeline_notifications import _load_notif_cfg

        bot_token = (
            (options.get("bot_token") or "").strip()
            or (os.getenv("TELEGRAM_BOT_POLL_TOKEN") or "").strip()
            or _load_notif_cfg().get("telegram_bot_token", "")
        )
        if not bot_token:
            raise CommandError(
                "No Telegram bot token found.\n\n"
                "  Option A: add to the Telegram worker environment\n"
                "    TELEGRAM_BOT_POLL_TOKEN=<your_bot_token>\n\n"
                "  Option B: Studio → Notifications → set Telegram bot token\n\n"
                "  Get a token from @BotFather in Telegram."
            )

        pipeline, trigger = self._resolve_pipeline(options.get("pipeline_id"))
        poll_timeout = max(5, min(30, int(options.get("poll_timeout") or 25)))
        lease_seconds = max(30, int(options.get("lease_seconds") or 180))
        worker_key = telegram_worker_key(bot_token)
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

        offset = get_telegram_update_offset(bot_token)
        summary = {
            "polls": 0,
            "updates": 0,
            "runs_created": 0,
            "replies_routed": 0,
            "approvals_routed": 0,
            "ignored": 0,
            "errors": 0,
        }
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
                    updates, _next_offset = asyncio.run(self._get_updates(bot_token, offset, poll_timeout))
                    summary["updates"] += len(updates)
                    for update in updates:
                        result = self._handle_update(update, bot_token, pipeline, trigger)
                        if result == "launched":
                            summary["runs_created"] += 1
                        elif result == "reply":
                            summary["replies_routed"] += 1
                        elif result == "approval":
                            summary["approvals_routed"] += 1
                        else:
                            summary["ignored"] += 1
                        update_id = update.get("update_id")
                        if isinstance(update_id, int):
                            offset = advance_telegram_update_offset(bot_token, update_id + 1)
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
                    "allowed_updates": ["message", "callback_query"],
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
        callback = update.get("callback_query") or {}
        if isinstance(callback, dict) and callback:
            return self._handle_callback(callback, bot_token)

        message = update.get("message") or {}
        if not isinstance(message, dict):
            return "ignored"
        if message.get("reply_to_message"):
            return self._handle_reply(message, bot_token)
        return self._launch_message(message, pipeline, trigger)

    def _handle_callback(self, callback: dict, bot_token: str) -> str:
        callback_message = callback.get("message") or {}
        callback_chat = callback_message.get("chat") or {}
        callback_from = callback.get("from") or {}
        accepted, answer = record_telegram_approval_callback(
            bot_token=bot_token,
            callback_data=callback.get("data"),
            chat_id=callback_chat.get("id"),
            from_username=callback_from.get("username") or callback_from.get("first_name") or "",
        )
        callback_id = str(callback.get("id") or "").strip()
        if callback_id:
            with contextlib.suppress(Exception):
                asyncio.run(self._answer_callback_query(bot_token, callback_id, answer))
        return "approval" if accepted else "ignored"

    def _handle_reply(self, message: dict, bot_token: str) -> str:
        if not store_telegram_operator_reply(bot_token, message):
            return "ignored"
        ts = timezone.now().strftime("%H:%M:%S")
        chat = message.get("chat") or {}
        self.stdout.write(f"[{ts}] chat={chat.get('id')}  reply routed to waiting pipeline")
        return "reply"

    def _validate_launch(self, pipeline: Pipeline, trigger: PipelineTrigger, context: dict) -> bool:
        from studio.pipeline.pipeline_runtime_context import (
            validate_pipeline_entry_branch,
            validate_pipeline_runtime_context,
        )
        from studio.pipeline.pipeline_validation import validate_pipeline_definition

        errors = validate_pipeline_definition(
            nodes=pipeline.nodes,
            edges=pipeline.edges,
            owner=pipeline.owner,
            graph_version=pipeline.graph_version,
        )
        if errors:
            self.stderr.write(f"Pipeline validation failed — fix it in Studio: {errors[:2]}")
            return False
        branch_errors = validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, trigger.node_id)
        if branch_errors:
            self.stderr.write(f"Pipeline entry branch failed — fix it in Studio: {branch_errors[:2]}")
            return False
        context_errors = validate_pipeline_runtime_context(
            pipeline.nodes,
            context,
            edges=pipeline.edges,
            entry_node_id=trigger.node_id,
        )
        if context_errors:
            self.stderr.write(f"Pipeline runtime context failed — fix it in Studio: {context_errors[:2]}")
            return False
        return True

    def _launch_message(self, message: dict, pipeline: Pipeline, trigger: PipelineTrigger) -> str:
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
        if not self._validate_launch(pipeline, trigger, context):
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

    async def _answer_callback_query(self, bot_token: str, callback_query_id: str, text: str) -> None:
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={"callback_query_id": callback_query_id, "text": str(text or "")[:200]},
            )
