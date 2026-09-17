"""Human-PTY occupancy gate for Fast-mode AI typing.

The Fast executor writes into the operator's interactive stdin. Before that
it must know whether the line is empty and whether a command is already
running — otherwise the agent concatenates onto a half-typed command.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Literal

OccupancyReason = Literal["", "typed_input", "held_input", "manual_command", "ai_command"]
IdleWaitResult = Literal["idle", "cancel", "timeout"]
TypedInputDecision = Literal["wait", "cancel"]

BUSY_POLL_SEC = 0.2
TYPED_INPUT_TIMEOUT_SEC = 300.0
BUSY_COMMAND_TIMEOUT_SEC = 120.0
INPUT_PREVIEW_LIMIT = 80


@dataclass(frozen=True)
class PtyOccupancy:
    """Snapshot of whether the human PTY can accept AI keystrokes."""

    idle: bool
    reason: OccupancyReason = ""
    preview: str = ""

    @property
    def is_typed_input(self) -> bool:
        return self.reason in {"typed_input", "held_input"}


def _preview_buffer(value: str) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > INPUT_PREVIEW_LIMIT:
        return text[: INPUT_PREVIEW_LIMIT - 1] + "…"
    return text


def inspect_pty_occupancy(
    *,
    input_buffer: str = "",
    input_forwarding_held: bool = False,
    manual_active_command_id: int | None = None,
    ai_active_command_id: int | None = None,
    current_ai_command_id: int | None = None,
) -> PtyOccupancy:
    """Return whether Fast AI may type into the shared PTY right now."""

    buffer = str(input_buffer or "")
    preview = _preview_buffer(buffer)
    if preview:
        return PtyOccupancy(idle=False, reason="typed_input", preview=preview)
    if input_forwarding_held:
        return PtyOccupancy(idle=False, reason="held_input", preview="")
    if manual_active_command_id is not None:
        return PtyOccupancy(idle=False, reason="manual_command")
    if ai_active_command_id is not None and (
        current_ai_command_id is None or int(ai_active_command_id) != int(current_ai_command_id)
    ):
        return PtyOccupancy(idle=False, reason="ai_command")
    return PtyOccupancy(idle=True)


def occupancy_prompt_note(occupancy: PtyOccupancy) -> str:
    """Short planner note about the human input line."""

    if occupancy.idle:
        return "Строка ввода общего терминала пустая — Fast может печатать команды."
    if occupancy.reason == "typed_input":
        return (
            "Оператор сейчас набирает в общем терминале: "
            f"`{occupancy.preview}`. Не планируй печать в этот PTY, пока строка не станет пустой."
        )
    if occupancy.reason == "held_input":
        return "Строка ввода общего терминала удерживается политикой. Не печатай в PTY, пока оператор не закончит."
    if occupancy.reason == "manual_command":
        return "В общем терминале сейчас выполняется команда оператора. Дождись её окончания, прежде чем печатать."
    return "В общем терминале сейчас выполняется команда ИИ. Дождись её окончания, прежде чем печатать."


async def wait_for_pty_idle(
    inspect: Callable[[], PtyOccupancy],
    *,
    on_typed_input: Callable[[PtyOccupancy], Awaitable[TypedInputDecision]] | None = None,
    sleep: Callable[[float], Coroutine[object, object, None]] | None = None,
    clock: Callable[[], float] | None = None,
    typed_timeout_sec: float = TYPED_INPUT_TIMEOUT_SEC,
    busy_timeout_sec: float = BUSY_COMMAND_TIMEOUT_SEC,
    poll_sec: float = BUSY_POLL_SEC,
) -> IdleWaitResult:
    """Poll occupancy until idle, operator cancel, or timeout.

    ``on_typed_input`` is invoked at most once when the line is occupied by
    typed-but-not-submitted text. ``wait`` keeps polling until the buffer
    clears; ``cancel`` aborts without typing.
    """

    sleeper = sleep or asyncio.sleep
    now = clock or (lambda: asyncio.get_running_loop().time())
    started = now()
    last_reason: OccupancyReason | None = None
    asked = False

    while True:
        occupancy = inspect()
        if occupancy.idle:
            return "idle"
        if last_reason is not None and occupancy.reason != last_reason:
            started = now()
        last_reason = occupancy.reason

        elapsed = now() - started
        timeout = typed_timeout_sec if occupancy.is_typed_input else busy_timeout_sec
        if elapsed > timeout:
            return "timeout"

        if occupancy.is_typed_input and on_typed_input is not None and not asked:
            asked = True
            decision = await on_typed_input(occupancy)
            if decision == "cancel":
                return "cancel"

        await sleeper(poll_sec)
