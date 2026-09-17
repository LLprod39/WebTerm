"""
run_telegram_bot — Compatibility alias for run_telegram_hub.

Legacy entrypoint used by docker-compose and older docs.
"""

from telegram_hub.management.commands.run_telegram_hub import Command as HubCommand


class Command(HubCommand):
    help = "Alias for run_telegram_hub (multi-bot Telegram long-poll worker)."
