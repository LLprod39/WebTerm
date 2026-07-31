from __future__ import annotations

STUDIO_SCHEDULED_PIPELINES_WORKER = "studio_scheduled_pipelines"
STUDIO_MONITOR_WORKER = "studio_monitor"
STUDIO_TELEGRAM_BOT_WORKER = "studio_telegram_bot"
STUDIO_PIPELINE_EXECUTION_WORKER = "studio_pipeline_execution"
OPERATOR_TURN_EXECUTION_WORKER = "operator_turn_execution"

STUDIO_WORKER_SPECS = {
    "operator-execution": {
        "worker_kind": OPERATOR_TURN_EXECUTION_WORKER,
        "command": "python manage.py run_operator_execution_plane",
    },
    "pipeline-execution": {
        "worker_kind": STUDIO_PIPELINE_EXECUTION_WORKER,
        "command": "python manage.py run_pipeline_execution_plane",
    },
    "scheduled-pipelines": {
        "worker_kind": STUDIO_SCHEDULED_PIPELINES_WORKER,
        "command": "python manage.py run_scheduled_pipelines --daemon --interval 60",
    },
    "monitor": {
        "worker_kind": STUDIO_MONITOR_WORKER,
        "command": "python manage.py run_monitor",
    },
    "telegram-bot": {
        "worker_kind": STUDIO_TELEGRAM_BOT_WORKER,
        "command": "python manage.py run_telegram_bot",
    },
}
