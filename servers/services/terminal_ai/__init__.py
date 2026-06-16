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

from servers.services.terminal_ai.decision import (  # noqa: F401
    decide_recovery,
    decide_step_next,
)
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
from servers.services.terminal_ai.memory_extraction import (  # noqa: F401
    extract_server_memory,
    run_memory_extraction,
    save_extracted_server_memory,
)
from servers.services.terminal_ai.output_explanation import explain_command_output  # noqa: F401
from servers.services.terminal_ai.plan_items import (  # noqa: F401
    build_plan_item,
    normalize_command_text,
    normalize_execution_mode,
    resolve_auto_execution_mode,
)
from servers.services.terminal_ai.planning import (  # noqa: F401
    extract_json_object,
    plan_terminal_commands,
)
from servers.services.terminal_ai.policy import (  # noqa: F401
    CommandPolicy,
    choose_exec_mode,
    compute_confirm_reason,
    decide_command_policy,
    match_patterns,
)
from servers.services.terminal_ai.preferences import (  # noqa: F401
    DEFAULT_AI_SETTINGS,
    clone_ai_settings,
    default_ai_settings,
    is_auto_report_enabled,
    normalize_ai_chat_mode,
    normalize_ai_settings,
    normalize_int_list,
    normalize_pattern_list,
    parse_bool,
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
from servers.services.terminal_ai.report_generation import (  # noqa: F401
    generate_ai_report_text,
    make_ai_report,
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
