"""
servers.services.terminal_ai — extracted building blocks for the SSH terminal
AI assistant (F1-5 / F1-6 of the architecture audit roadmap).

Public entry points
-------------------
- prompts.build_planner_prompt
- prompts.build_recovery_prompt
- prompts.build_step_decision_prompt
- prompts.build_report_prompt
- prompts.build_memory_extraction_prompt
- prompts.sanitize_for_prompt
- schemas.TerminalPlanResponse
- schemas.RecoveryDecision
- schemas.StepDecision
- schemas.MemoryExtraction
- schemas.parse_or_repair

These modules are pure Python — no Django ORM, no WebSocket — so they are
independently unit-testable. The SSH consumer should import from here
instead of embedding f-string prompts inline.
"""

from servers.services.terminal_ai.history import (  # noqa: F401
    append_message,
    append_message_sync,
    clear_history,
    clear_history_sync,
    load_recent,
    load_recent_sync,
)
from servers.services.terminal_ai.memory import (  # noqa: F401
    sanitize_memory_line,
    save_server_profile,
    save_server_profile_sync,
    select_memory_candidate_commands,
    should_extract_memory,
)
from servers.services.terminal_ai.policy import (  # noqa: F401
    CommandPolicy,
    choose_exec_mode,
    decide_command_policy,
    match_patterns,
)
from servers.services.terminal_ai.prompts import (  # noqa: F401
    build_dry_run_block,
    build_explain_output_prompt,
    build_memory_extraction_prompt,
    build_planner_prompt,
    build_planner_prompt_parts,
    build_recovery_prompt,
    build_report_prompt,
    build_step_decision_prompt,
    sanitize_for_prompt,
)
from servers.services.terminal_ai.reporter import (  # noqa: F401
    build_fallback_report,
    compute_report_status,
)
from servers.services.terminal_ai.rules_loader import (  # noqa: F401
    TerminalRulesContext,
    load_effective_environment_vars,
    load_terminal_rules,
)
from servers.services.terminal_ai.schemas import (  # noqa: F401
    MemoryExtraction,
    PlannedCommand,
    RecoveryDecision,
    StepDecision,
    TerminalPlanResponse,
    parse_or_repair,
)
from servers.services.terminal_ai.server_ai_policy import is_server_ai_read_only  # noqa: F401
from servers.services.terminal_ai.session import TerminalAiSession  # noqa: F401
