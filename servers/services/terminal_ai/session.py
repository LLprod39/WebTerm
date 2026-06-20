"""
Per-request Terminal AI session state (F2-1).

Encapsulates the transient state that a single Terminal-AI turn needs:
the command plan, its cursor, the current run identifiers, the user
message, the selected chat/execution mode, the step-mode safety counter,
and the collected ``done`` items for the eventual report/memory step.

Design rationale
----------------
The ``SSHTerminalConsumer`` used to own ~12 scattered ``self._ai_*``
attributes representing this state. That made:

- reset / cancel logic error-prone (easy to forget a field)
- unit testing impossible (needed a full WebSocket harness)
- code review hard (no single place to reason about lifecycle)

:class:`TerminalAiSession` gathers all per-request fields into a single
dataclass with clear defaults and a small set of mutation helpers. The
consumer composes one instance (``self._ai_session``) and — for
backward-compatibility — exposes the historical attributes as
``@property`` aliases, so the thousands of reads/writes in the file
continue to work unchanged.

Fields NOT held here
--------------------
These stay on the consumer because they are tied to its I/O lifecycle
rather than to a single turn:

- ``asyncio.Lock`` / ``asyncio.Task`` / ``asyncio.Future`` objects
- the SSH PTY state (``_ssh_proc``, ``_stdout_task`` etc.)
- the running per-command ``active_cmd_id`` + streamed output buffer
- the long-lived chat history (separate concern, F2-9)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TerminalAiCommandTransition:
    """Result of a user action against the current queued command."""

    command_id: int | None = None
    status: str = ""
    error: str = ""
    changed: bool = False


@dataclass(frozen=True)
class TerminalAiQueueStep:
    """State-machine decision for the next queued command."""

    action: str
    item: dict[str, Any] | None = None
    command_id: int | None = None
    command: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TerminalAiParallelBatch:
    """Snapshot of queue items that can run concurrently."""

    items: list[dict[str, Any]] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return bool(self.indices)


@dataclass
class TerminalAiSession:
    """State of a single ongoing terminal AI request.

    Mutable on purpose — the orchestrator keeps a long-lived reference
    and calls :meth:`reset_for_new_request` at the start of every turn.
    """

    # --- queue + cursor ----------------------------------------------------
    plan: list[dict[str, Any]] = field(default_factory=list)
    """Ordered list of plan-items (see `_build_plan_item`). Mutated in place."""

    plan_index: int = 0
    """Index of the next item to execute. Advanced by the orchestrator."""

    next_id: int = 1
    """Monotonic id assigned to freshly-created plan-items (must be unique per run)."""

    step_extra_count: int = 0
    """Safety counter: how many adaptive steps step-mode has already inserted.
    Bounded by ``_ai_settings['step_extra_limit']`` to prevent runaway plans."""

    forbidden_patterns: list[str] = field(default_factory=list)
    """Merged per-request command deny patterns from user, server, and AI plan rules."""

    # --- request context ---------------------------------------------------
    user_message: str = ""
    """The raw user prompt that started this run."""

    chat_mode: str = "agent"
    """One of ``"agent"`` (auto-run), ``"ask"`` (confirm every cmd)."""

    execution_mode: str = "step"
    """One of ``"step"`` (per-command LLM) or ``"fast"`` (execute then report)."""

    # --- run identifiers ---------------------------------------------------
    run_id: str = ""
    """Stable short id stamped on every ``ai_*`` WS event for this run."""

    marker_token: str = ""
    """Per-run PTY marker token used to detect ``__EXIT_<n>__`` boundaries."""

    # --- accumulated outcome ----------------------------------------------
    last_done_items: list[dict[str, Any]] = field(default_factory=list)
    """Executed plan-items with captured output/exit_code, for report + memory."""

    last_report: str = ""
    """Last LLM-generated report text (or fallback text) for this run."""

    # --- control flags -----------------------------------------------------
    stop_requested: bool = False
    """Set by ``/stop`` handler — the orchestrator must unwind cleanly."""

    # ----------------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------------

    def reset_for_new_request(
        self,
        *,
        user_message: str,
        chat_mode: str,
        execution_mode: str,
        run_id: str,
        marker_token: str,
    ) -> None:
        """Prepare the session to start a fresh turn.

        Keeps only the caller-provided context. Clears the plan queue,
        the cursor, the done-item buffer, the report cache and the
        stop flag — so the consumer cannot leak state across requests
        by forgetting to reset one field.
        """
        self.plan = []
        self.plan_index = 0
        self.next_id = 1
        self.step_extra_count = 0
        self.forbidden_patterns = []
        self.user_message = user_message
        self.chat_mode = chat_mode
        self.execution_mode = execution_mode
        self.run_id = run_id
        self.marker_token = marker_token
        self.last_done_items = []
        self.last_report = ""
        self.stop_requested = False

    def clear(self) -> None:
        """Cancel-path wipe. Keeps identifiers around for trailing events."""
        self.plan = []
        self.plan_index = 0
        self.step_extra_count = 0
        self.forbidden_patterns = []
        self.stop_requested = False

    # ----------------------------------------------------------------------
    # Mutation helpers (give the orchestrator a single vocabulary)
    # ----------------------------------------------------------------------

    def allocate_id(self) -> int:
        """Return the next plan-item id and advance the counter."""
        item_id = int(self.next_id)
        self.next_id += 1
        return item_id

    def load_plan(
        self,
        plan_items: list[dict[str, Any]],
        *,
        next_id: int,
        forbidden_patterns: list[str] | None = None,
    ) -> None:
        """Install a freshly planned queue and reset its execution cursor."""
        self.plan = list(plan_items)
        self.plan_index = 0
        self.next_id = int(next_id)
        self.forbidden_patterns = list(forbidden_patterns or [])

    def allocate_question_id(self, prefix: str) -> str:
        """Return a unique question id using the same per-run id sequence."""
        return f"{prefix}_{self.allocate_id()}"

    def append_plan_item(self, item: dict[str, Any]) -> None:
        """Append a plan-item to the end of the queue."""
        self.plan.append(item)

    def insert_after_current(self, item: dict[str, Any]) -> None:
        """Insert a plan-item immediately after the current cursor."""
        idx = max(0, min(self.plan_index + 1, len(self.plan)))
        self.plan.insert(idx, item)

    def insert_at_cursor(self, item: dict[str, Any]) -> None:
        """Insert a plan-item so it is the next command to run."""
        idx = max(0, min(self.plan_index, len(self.plan)))
        self.plan.insert(idx, item)

    def insert_after_cursor(self, item: dict[str, Any]) -> None:
        """Insert a plan-item right *before* the current cursor position.

        Used by step-mode when the LLM decides to inject an adaptive next
        command — it should run *now*, not after everything queued.
        """
        idx = max(0, min(self.plan_index, len(self.plan)))
        self.plan.insert(idx, item)

    def increment_step_extra_count(self) -> int:
        """Increment and return the adaptive step counter."""
        self.step_extra_count += 1
        return self.step_extra_count

    def remaining(self) -> list[dict[str, Any]]:
        """Return still-to-execute plan items (read-only snapshot)."""
        return list(self.plan[self.plan_index :])

    def remaining_commands_after_current(self) -> list[Any]:
        """Return command payloads after the current item for error recovery."""
        return [
            item.get("cmd", "")
            for item in self.plan[self.plan_index + 1 :]
            if item.get("status") not in ("done", "skipped")
        ]

    def remaining_commands_from_cursor(self) -> list[str]:
        """Return normalized command text from the current cursor onward."""
        return [
            str(item.get("cmd") or "").strip()
            for item in self.plan[self.plan_index :]
            if item.get("status") not in ("done", "skipped")
        ]

    def is_empty(self) -> bool:
        return not self.plan

    def is_finished(self) -> bool:
        """True iff every plan item has been consumed."""
        return self.plan_index >= len(self.plan)

    def record_done(self, item: dict[str, Any]) -> None:
        """Append an executed item to the report/memory buffer."""
        self.last_done_items.append(item)

    def prepare_parallel_batch(
        self,
        *,
        direct_exec_enabled: bool,
        step_mode: bool,
        has_ssh_connection: bool,
    ) -> TerminalAiParallelBatch:
        """Return the current direct-exec batch snapshot, if batching is allowed."""
        if not direct_exec_enabled or step_mode or not has_ssh_connection:
            return TerminalAiParallelBatch()

        from servers.services.parallel_executor import collect_parallel_batch

        indices = collect_parallel_batch(self.plan, self.plan_index, step_mode=step_mode)
        if not indices:
            return TerminalAiParallelBatch()
        return TerminalAiParallelBatch(
            items=[self.plan[index] for index in indices],
            indices=list(indices),
        )

    def advance_after_parallel_batch(self, plan_indices: list[int]) -> bool:
        """Advance the queue cursor past a completed parallel batch."""
        valid_indices = [index for index in plan_indices if index >= 0]
        if not valid_indices:
            return False

        next_index = min(max(valid_indices) + 1, len(self.plan))
        if next_index <= self.plan_index:
            return False

        self.plan_index = next_index
        return True

    def prepare_next_step(self) -> TerminalAiQueueStep:
        """Prepare the current queue item for execution or waiting.

        The caller remains responsible for emitting WebSocket events. This
        method only mutates queue cursor/status state.
        """
        item = self._current_item()
        if item is None:
            return TerminalAiQueueStep(action="empty")

        item_id = int(item.get("id") or 0)
        command = str(item.get("cmd") or "").strip()
        reason = str(item.get("reason") or "").strip()
        status = str(item.get("status") or "pending")

        if status in ("done", "skipped", "cancelled"):
            self.plan_index += 1
            return TerminalAiQueueStep(action="advance")

        if bool(item.get("blocked")):
            item["status"] = "skipped"
            self.plan_index += 1
            return TerminalAiQueueStep(
                action="blocked_skipped",
                item=item,
                command_id=item_id,
                command=command,
                reason=reason,
            )

        if bool(item.get("requires_confirm")):
            item["status"] = "pending_confirm"
            return TerminalAiQueueStep(
                action="waiting_confirm",
                item=item,
                command_id=item_id,
                command=command,
                reason=reason,
            )

        item["status"] = "running"
        return TerminalAiQueueStep(
            action="run",
            item=item,
            command_id=item_id,
            command=command,
            reason=reason,
        )

    def mark_current_done(self, command_id: int, exit_code: int | None, output_snippet: str) -> bool:
        """Mark the current item done if the cursor still points at it."""
        item = self._current_item()
        if item is None or int(item.get("id") or 0) != command_id:
            return False

        item["status"] = "done"
        item["exit_code"] = exit_code
        item["output_snippet"] = output_snippet or ""
        self.plan_index += 1
        return True

    def mark_plan_index_done(self, plan_index: int, exit_code: int | None, output_snippet: str) -> bool:
        """Mark an explicit plan index done without moving the queue cursor."""
        if plan_index < 0 or plan_index >= len(self.plan):
            return False

        item = self.plan[plan_index]
        item["status"] = "done"
        item["exit_code"] = exit_code
        item["output_snippet"] = output_snippet or ""
        return True

    def skip_remaining(self) -> list[int]:
        """Skip every not-yet-terminal item and move the cursor to the end."""
        skipped_ids: list[int] = []
        for item in self.remaining():
            item_id = int(item.get("id") or 0)
            status = str(item.get("status") or "")
            if item_id and status not in ("done", "skipped", "cancelled"):
                item["status"] = "skipped"
                skipped_ids.append(item_id)
        self.plan_index = len(self.plan)
        return skipped_ids

    def snapshot_done_items(self, *, output_limit: int = 4000) -> list[dict[str, Any]]:
        """Project completed plan items for reports and cache them on the session."""
        done_items = [
            {
                "cmd": str(item.get("cmd") or "").strip(),
                "exit_code": item.get("exit_code"),
                "output": (str(item.get("output_snippet") or "").strip())[:output_limit],
            }
            for item in self.plan
            if str(item.get("status") or "") == "done"
        ]
        self.last_done_items = list(done_items)
        return done_items

    @staticmethod
    def done_items_with_output(done_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return only completed command projections that carry non-empty output."""
        return [item for item in done_items if (item.get("output") or "").strip()]

    def confirm_current(self, command_id: int) -> TerminalAiCommandTransition:
        """Confirm the currently waiting command if it matches ``command_id``."""
        item = self._current_item()
        if item is None:
            return TerminalAiCommandTransition()
        if int(item.get("id") or 0) != command_id:
            return TerminalAiCommandTransition(
                command_id=command_id,
                error="Подтверждать можно только текущую ожидающую команду",
            )
        if not item.get("requires_confirm"):
            return TerminalAiCommandTransition(command_id=command_id)

        item["requires_confirm"] = False
        item["confirmed"] = True
        item["status"] = "pending"
        return TerminalAiCommandTransition(command_id=command_id, status="confirmed", changed=True)

    def cancel_current(self, command_id: int) -> TerminalAiCommandTransition:
        """Skip the currently waiting command if it matches ``command_id``."""
        item = self._current_item()
        if item is None:
            return TerminalAiCommandTransition()
        if int(item.get("id") or 0) != command_id:
            return TerminalAiCommandTransition(
                command_id=command_id,
                error="Отменять можно только текущую ожидающую команду",
            )

        item["status"] = "skipped"
        self.plan_index += 1
        return TerminalAiCommandTransition(command_id=command_id, status="skipped", changed=True)

    def request_stop(self, active_command_id: int | None = None) -> list[int]:
        """Mark the session as stopped and return pending command ids to skip."""
        self.stop_requested = True
        pending_to_skip: list[int] = []
        for item in self.remaining():
            item_id = int(item.get("id") or 0)
            status = str(item.get("status") or "pending")
            if item_id and item_id != active_command_id and status not in ("done", "skipped", "cancelled"):
                pending_to_skip.append(item_id)
        return pending_to_skip

    def _current_item(self) -> dict[str, Any] | None:
        if not self.plan or self.plan_index >= len(self.plan):
            return None
        return self.plan[self.plan_index]
