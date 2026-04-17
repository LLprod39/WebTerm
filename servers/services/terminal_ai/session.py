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
        self.stop_requested = False

    # ----------------------------------------------------------------------
    # Mutation helpers (give the orchestrator a single vocabulary)
    # ----------------------------------------------------------------------

    def allocate_id(self) -> int:
        """Return the next plan-item id and advance the counter."""
        item_id = int(self.next_id)
        self.next_id += 1
        return item_id

    def append_plan_item(self, item: dict[str, Any]) -> None:
        """Append a plan-item to the end of the queue."""
        self.plan.append(item)

    def insert_after_cursor(self, item: dict[str, Any]) -> None:
        """Insert a plan-item right *before* the current cursor position.

        Used by step-mode when the LLM decides to inject an adaptive next
        command — it should run *now*, not after everything queued.
        """
        idx = max(0, min(self.plan_index, len(self.plan)))
        self.plan.insert(idx, item)

    def remaining(self) -> list[dict[str, Any]]:
        """Return still-to-execute plan items (read-only snapshot)."""
        return list(self.plan[self.plan_index :])

    def is_empty(self) -> bool:
        return not self.plan

    def is_finished(self) -> bool:
        """True iff every plan item has been consumed."""
        return self.plan_index >= len(self.plan)

    def record_done(self, item: dict[str, Any]) -> None:
        """Append an executed item to the report/memory buffer."""
        self.last_done_items.append(item)
