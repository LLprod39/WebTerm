"""
4.2: Parallel execution grouping for terminal AI command plans.

Only ``exec_mode=direct`` commands can be truly parallelized because they
use separate non-PTY SSH channels.  PTY commands share the interactive
shell and must remain sequential.

Public API
----------
- ``collect_parallel_batch(plan, start, *, step_mode) -> list[int]``
"""

from __future__ import annotations

from typing import Any

# Hard ceiling on concurrent SSH channels opened in one batch.
MAX_PARALLEL_BATCH = 4


def collect_parallel_batch(
    plan: list[dict[str, Any]],
    start_index: int,
    *,
    step_mode: bool = False,
) -> list[int]:
    """Return indices of consecutive commands eligible for parallel execution.

    Rules:
    - Step mode → never batch (each command needs a post-step LLM call).
    - Only ``exec_mode == "direct"`` commands qualify.
    - Commands must be ``status == "pending"`` and not blocked / requiring
      confirmation.
    - The batch stops at the first ineligible item or after
      :data:`MAX_PARALLEL_BATCH`.
    - Returns **at least 1** index (the current item) if it is eligible,
      or an **empty list** if the current item doesn't qualify (caller
      should fall through to sequential execution).
    """
    if step_mode:
        return []

    if start_index >= len(plan):
        return []

    indices: list[int] = []
    for i in range(start_index, min(start_index + MAX_PARALLEL_BATCH, len(plan))):
        item = plan[i]
        status = str(item.get("status") or "pending")
        if status in ("done", "skipped", "cancelled"):
            # Already processed — skip over but don't break batch
            continue
        if bool(item.get("blocked")) or bool(item.get("requires_confirm")):
            break
        exec_mode = str(item.get("exec_mode") or "pty").strip().lower()
        if exec_mode != "direct":
            break
        indices.append(i)

    # Only return a batch if we found ≥ 2 parallelizable items.
    # Single items are handled more efficiently by the regular sequential path
    # (which includes step-decide, recovery, etc.).
    if len(indices) < 2:
        return []

    return indices
