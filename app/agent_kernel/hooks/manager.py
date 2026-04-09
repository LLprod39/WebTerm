from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.redaction import sanitize_observation_text, sanitize_prompt_context_text


@dataclass
class HookManager:
    """
    Lifecycle hook manager для agent runtime.

    Базовый класс предоставляет no-op реализации всех хуков.
    Подклассы могут переопределять нужные методы для:
    - мониторинга / логирования
    - промежуточных checkpoint'ов
    - кастомной обработки наблюдений
    - skill-triggering по паттернам
    """

    max_observation_chars: int = 2400
    # Метаданные текущего run — заполняются on_agent_start
    _run_metadata: dict[str, Any] = field(default_factory=dict, init=False)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def on_agent_start(
        self,
        *,
        run_id: str,
        server_id: int | None = None,
        goal: str = "",
        role: str = "custom",
        permission_mode: str = "SAFE",
    ) -> None:
        """
        GAP 4: вызывается в начале каждого AgentRun перед первым LLM-вызовом.
        Используется для инициализации контекста, логирования и warmup.
        """
        self._run_metadata = {
            "run_id": run_id,
            "server_id": server_id,
            "goal": goal,
            "role": role,
            "permission_mode": permission_mode,
        }
        logger.info(
            "agent_hook:start run_id={} server_id={} role={} mode={}",
            run_id, server_id, role, permission_mode,
        )

    async def on_iteration_complete(
        self,
        *,
        iteration: int,
        thought: str = "",
        action: str = "",
        tool: str = "",
        observation: str = "",
    ) -> None:
        """
        GAP 4: вызывается после каждой завершённой итерации ReAct loop.
        Подклассы могут делать checkpoint или adaptive logging.
        """
        run_id = self._run_metadata.get("run_id", "?")
        logger.debug(
            "agent_hook:iteration run_id={} iter={} tool={} action={}",
            run_id, iteration, tool, action[:80] if action else "",
        )

    async def on_skill_triggered(
        self,
        *,
        skill_slug: str,
        trigger_context: dict[str, Any] | None = None,
    ) -> None:
        """
        GAP 4: вызывается когда агент начинает использовать конкретный skill.
        Полезно для аудита и трекинга skill adoption.
        """
        run_id = self._run_metadata.get("run_id", "?")
        logger.info("agent_hook:skill run_id={} skill={}", run_id, skill_slug)

    async def on_memory_loaded(
        self,
        *,
        server_id: int,
        card_confidence: float = 0.0,
        has_patterns: bool = False,
        has_skill_drafts: bool = False,
    ) -> None:
        """
        GAP 4: вызывается после загрузки ServerMemoryCard перед prompt-сборкой.
        Позволяет адаптировать поведение на основе состояния памяти.
        """
        run_id = self._run_metadata.get("run_id", "?")
        logger.debug(
            "agent_hook:memory_loaded run_id={} server_id={} confidence={:.2f} patterns={} skills={}",
            run_id, server_id, card_confidence, has_patterns, has_skill_drafts,
        )

    async def on_run_budget_warning(
        self,
        *,
        iterations_used: int,
        iterations_max: int,
        remaining_fraction: float,
    ) -> None:
        """
        GAP 4: вызывается когда израсходовано > 75% бюджета итераций.
        Агент может переключиться в более агрессивный summarize-режим.
        """
        run_id = self._run_metadata.get("run_id", "?")
        logger.warning(
            "agent_hook:budget_warning run_id={} used={}/{} remaining={:.0%}",
            run_id, iterations_used, iterations_max, remaining_fraction,
        )

    # ------------------------------------------------------------------
    # Существующие методы (без изменений)
    # ------------------------------------------------------------------

    async def pre_tool_use(self, *_args, **_kwargs) -> tuple[str, ...]:
        return ()

    def sanitize_observation(self, result_text: str, *, limit: int) -> str:
        sanitized = sanitize_observation_text(result_text).text
        return compact_text(sanitized, limit=limit)

    async def post_tool_use(self, tool_name: str, result_text: str) -> str:
        if tool_name in {"read_console", "ssh_execute"}:
            return self.sanitize_observation(result_text, limit=self.max_observation_chars)
        return self.sanitize_observation(result_text, limit=min(self.max_observation_chars, 1800))

    def build_observation_message(self, observation: str, *, limit: int = 4000) -> str:
        return f"OBSERVATION: {self.sanitize_observation(observation, limit=limit)}"

    async def run_finished(self, final_report: str, verification_summary: str) -> str:
        final_report = sanitize_prompt_context_text(final_report).text
        verification_summary = sanitize_observation_text(verification_summary).text
        if not verification_summary:
            return final_report
        if verification_summary in final_report:
            return final_report
        return f"{final_report.rstrip()}\n\n## Контроль изменений\n- {verification_summary}\n"
