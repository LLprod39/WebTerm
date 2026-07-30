"""Ops memory prompt + run summary helpers for AgentEngine."""

from __future__ import annotations

from asgiref.sync import sync_to_async
from loguru import logger

from app.agent_kernel.memory.compaction import build_run_summary_payload
from app.agent_kernel.memory.server_cards import render_server_cards_prompt
from app.agent_kernel.runtime.context import build_ops_prompt_context
from servers.models import AgentRun


class AgentEngineOpsMixin:
    """Memory/ops prompt + summary persistence mixed into AgentEngine."""

    async def _build_ops_prompt_context(self) -> str:
        cards = []
        server_ids: list[int] = []
        group_ids: list[int] = []
        for server in self.servers[:3]:
            server_ids.append(server.id)
            if getattr(server, "group_id", None):
                group_ids.append(server.group_id)
        # P2-7: batch-load all server cards in one pass
        try:
            cards = await sync_to_async(self.memory_store._get_server_cards_batch_sync)(server_ids)
        except Exception as exc:
            logger.debug("Batch card loading failed, falling back to sequential: {}", exc)
            for server in self.servers[:3]:
                try:
                    cards.append(await self.memory_store.get_server_card(server.id))
                except Exception as card_exc:
                    logger.debug("Failed to load memory card for server {}: {}", server.id, card_exc)

        # GAP 4: on_memory_loaded hook
        if cards:
            primary_card = cards[0]
            has_patterns = any(
                k.startswith(("pattern_candidate:", "automation_candidate:", "skill_draft:"))
                for k in getattr(primary_card, "extra_snapshots", {})
            )
            await self.hook_manager.on_memory_loaded(
                server_id=server_ids[0] if server_ids else 0,
                card_confidence=getattr(primary_card, "confidence", 0.0) or 0.0,
                has_patterns=has_patterns,
                has_skill_drafts=has_patterns,
            )

        server_memory_prompt = render_server_cards_prompt(cards, max_cards=3, max_records=6)
        recipes_query = "\n".join(
            part for part in [self.agent.goal or self.agent.ai_prompt or "", *self.role_spec.focus_areas] if part
        )
        operational_recipes_prompt = await self.memory_store.build_operational_recipes_prompt(
            recipes_query,
            server_ids=server_ids,
            group_ids=list(dict.fromkeys(group_ids)),
            limit=5,
        )
        tool_registry_prompt = self.tool_registry.build_prompt_slice(limit=10) if self.tool_registry else ""

        # GAP 5: memory warmup prompt — recent agent run history
        warmup = ""
        if server_ids:
            try:
                warmup = await sync_to_async(self.memory_store._build_memory_warmup_prompt, thread_sensitive=False)(
                    server_ids[0], last_n=3
                )
            except Exception:
                warmup = ""

        return build_ops_prompt_context(
            role_spec=self.role_spec,
            permission_mode=self.permission_engine.mode,
            server_memory_prompt=server_memory_prompt,
            operational_recipes_prompt=operational_recipes_prompt,
            tool_registry_prompt=tool_registry_prompt,
            max_iterations=self.max_iterations,
            session_timeout=self.session_timeout,
            memory_warmup_prompt=warmup,
        )

    async def _persist_ops_summary(
        self,
        *,
        run: AgentRun,
        final_status: str,
        final_report: str,
        iterations_log: list[dict],
        tool_calls_log: list[dict],
    ):
        if not getattr(run, "pk", None):
            return
        payload = build_run_summary_payload(
            run=run,
            role_slug=self.role_spec.slug,
            final_status=final_status,
            final_report=final_report,
            iterations=iterations_log,
            tool_calls=tool_calls_log,
            verification_summary=self.permission_engine.verification_summary(),
        )
        await self.memory_store.append_run_summary(run.pk, payload)
