"""
run_telegram_hub — Multi-bot long-poll worker for platform + personal Telegram bots.

Usage:
    python manage.py run_telegram_hub
    python manage.py run_telegram_hub --reload-seconds 30
"""

from __future__ import annotations

import asyncio
import contextlib

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from django.utils import timezone

from app.background_workers import STUDIO_TELEGRAM_BOT_WORKER
from app.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker
from studio.telegram_delivery_service import (
    advance_telegram_update_offset,
    get_telegram_update_offset,
    telegram_worker_key,
)
from telegram_hub.client import TelegramAPIError, TelegramClient
from telegram_hub.router import BOT_COMMANDS, TelegramUpdateRouter
from telegram_hub.services.bots import (
    get_bot_token,
    list_active_bots_for_polling,
    mark_bot_unauthorized,
    touch_bot_poll,
)


class Command(BaseCommand):
    help = "Long-poll all active Telegram bots (platform + personal) and route updates."

    def add_arguments(self, parser):
        parser.add_argument("--poll-timeout", type=int, default=25)
        parser.add_argument("--reload-seconds", type=int, default=30)
        parser.add_argument("--lease-seconds", type=int, default=180)
        parser.add_argument("--max-cycles", type=int, default=0, help="Stop after N reload cycles (tests)")

    def handle(self, *args, **options):
        poll_timeout = max(5, min(30, int(options.get("poll_timeout") or 25)))
        reload_seconds = max(5, int(options.get("reload_seconds") or 30))
        lease_seconds = max(30, int(options.get("lease_seconds") or 180))
        max_cycles = max(0, int(options.get("max_cycles") or 0))

        self.stdout.write(self.style.SUCCESS("Telegram hub starting…"))
        try:
            asyncio.run(
                self._run_hub(
                    poll_timeout=poll_timeout,
                    reload_seconds=reload_seconds,
                    lease_seconds=lease_seconds,
                    max_cycles=max_cycles,
                )
            )
        except KeyboardInterrupt:
            self.stdout.write("\nHub stopped.")

    async def _run_hub(self, *, poll_timeout: int, reload_seconds: int, lease_seconds: int, max_cycles: int):
        tasks: dict[int, asyncio.Task] = {}
        stop_flags: dict[int, asyncio.Event] = {}
        cycles = 0
        while True:
            cycles += 1
            bots = await sync_to_async(list_active_bots_for_polling, thread_sensitive=True)()
            active_ids = {bot.pk for bot in bots}

            for bot_id in list(tasks.keys()):
                if bot_id not in active_ids:
                    stop_flags[bot_id].set()
                    tasks[bot_id].cancel()
                    with contextlib.suppress(Exception):
                        await tasks[bot_id]
                    tasks.pop(bot_id, None)
                    stop_flags.pop(bot_id, None)

            for bot in bots:
                if bot.pk in tasks and not tasks[bot.pk].done():
                    continue
                stop_event = asyncio.Event()
                stop_flags[bot.pk] = stop_event
                tasks[bot.pk] = asyncio.create_task(
                    self._poll_bot(
                        bot_id=bot.pk,
                        poll_timeout=poll_timeout,
                        lease_seconds=lease_seconds,
                        stop_event=stop_event,
                    )
                )

            self.stdout.write(f"[{timezone.now():%H:%M:%S}] active bots: {len(bots)}")
            if max_cycles and cycles >= max_cycles:
                # Give poll tasks a chance to claim leases / do one cycle.
                await asyncio.sleep(min(2.0, float(poll_timeout)))
                for event in stop_flags.values():
                    event.set()
                for task in tasks.values():
                    task.cancel()
                with contextlib.suppress(Exception):
                    await asyncio.gather(*tasks.values(), return_exceptions=True)
                break
            await asyncio.sleep(reload_seconds)

    async def _poll_bot(self, *, bot_id: int, poll_timeout: int, lease_seconds: int, stop_event: asyncio.Event):
        from telegram_hub.models import TelegramBot

        bot = await sync_to_async(TelegramBot.objects.filter(pk=bot_id).first, thread_sensitive=True)()
        if bot is None:
            return
        token = await sync_to_async(get_bot_token, thread_sensitive=True)(bot)
        if not token:
            await sync_to_async(mark_bot_unauthorized, thread_sensitive=True)(bot, "Missing bot token")
            return

        worker_key = telegram_worker_key(token)
        state = await sync_to_async(claim_background_worker, thread_sensitive=True)(
            STUDIO_TELEGRAM_BOT_WORKER,
            worker_key=worker_key,
            command="python manage.py run_telegram_hub",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Bot {bot_id} already leased"))
            return

        client = TelegramClient(token, timeout=poll_timeout + 10)
        router = TelegramUpdateRouter(bot, client)
        summary = {"updates": 0, "errors": 0}

        try:
            with contextlib.suppress(Exception):
                await client.set_my_commands(BOT_COMMANDS)
            offset = await sync_to_async(get_telegram_update_offset, thread_sensitive=True)(token)
            while not stop_event.is_set():
                try:
                    await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                        STUDIO_TELEGRAM_BOT_WORKER,
                        worker_key=worker_key,
                        lease_seconds=lease_seconds,
                        summary=summary,
                        cycle_started=True,
                    )
                    updates = await client.get_updates(offset=offset, timeout=poll_timeout)
                    summary["updates"] += len(updates)
                    for update in updates:
                        fresh = await sync_to_async(
                            TelegramBot.objects.filter(pk=bot_id).first,
                            thread_sensitive=True,
                        )()
                        if fresh is None or not fresh.is_active:
                            stop_event.set()
                            break
                        bot = fresh
                        router.bot = bot
                        result = await sync_to_async(router.handle_update, thread_sensitive=True)(update)
                        self.stdout.write(f"bot={bot_id} update → {result}")
                        update_id = update.get("update_id")
                        if isinstance(update_id, int):
                            offset = await sync_to_async(advance_telegram_update_offset, thread_sensitive=True)(
                                token, update_id + 1
                            )
                    if stop_event.is_set():
                        break
                    await sync_to_async(touch_bot_poll, thread_sensitive=True)(bot)
                    await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                        STUDIO_TELEGRAM_BOT_WORKER,
                        worker_key=worker_key,
                        lease_seconds=lease_seconds,
                        summary=summary,
                        cycle_finished=True,
                    )
                except TelegramAPIError as exc:
                    summary["errors"] += 1
                    if exc.status_code == 401:
                        await sync_to_async(mark_bot_unauthorized, thread_sensitive=True)(bot, str(exc))
                        break
                    await sync_to_async(touch_bot_poll, thread_sensitive=True)(bot, error=str(exc))
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    summary["errors"] += 1
                    await sync_to_async(touch_bot_poll, thread_sensitive=True)(bot, error=str(exc))
                    await asyncio.sleep(5)
        finally:
            await sync_to_async(stop_background_worker, thread_sensitive=True)(
                STUDIO_TELEGRAM_BOT_WORKER,
                worker_key=worker_key,
                summary=summary,
            )
