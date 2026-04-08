from __future__ import annotations

from dataclasses import dataclass

from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.redaction import sanitize_observation_text, sanitize_prompt_context_text


@dataclass
class HookManager:
    max_observation_chars: int = 2400

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
