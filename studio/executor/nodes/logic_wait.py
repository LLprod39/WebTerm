from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.models import PipelineRun

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


logger = logging.getLogger(__name__)


@registry.register
class LogicWaitNode(BaseNode):
    node_type = "logic/wait"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data if isinstance(self.node_data, dict) else {}
        try:
            minutes = float(config.get("wait_minutes", 1))
        except (TypeError, ValueError):
            minutes = 1.0

        minutes = max(0.1, min(minutes, 1440))
        logger.info("logic/wait node %s: sleeping %.1f minutes", self.node_id, minutes)

        remaining_seconds = minutes * 60
        while remaining_seconds > 0:
            if ctx.should_stop:
                return NodeResult(output={"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True})

            fresh_status = await sync_to_async(
                lambda: PipelineRun.objects.filter(pk=ctx.run_id).values_list("status", flat=True).first(),
                thread_sensitive=False,
            )()
            if fresh_status == PipelineRun.STATUS_STOPPED:
                return NodeResult(output={"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True})

            sleep_seconds = min(1.0, remaining_seconds)
            await asyncio.sleep(sleep_seconds)
            remaining_seconds -= sleep_seconds

        return NodeResult(output={"status": "completed", "output": f"⏱️ Ожидание завершено: {minutes:.1f} мин."})
