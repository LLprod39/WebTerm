"""
Tool registry for the Terminal Agent.

The registry exposes :func:`default_tool_set` — the canonical collection
of tools wired into the agent loop. Individual tool classes are also
re-exported here so tests / alternate agent configurations can pick and
choose.

Adding a new tool
-----------------
1. Create ``agent/tools/<name>.py`` implementing the :class:`TerminalTool`
   protocol (see :mod:`agent/tools/base.py`).
2. Import and add it to :func:`default_tool_set`.
3. Write at least one test in ``tests/test_agent_tools.py``.
"""

from __future__ import annotations

from servers.services.terminal_ai.agent.tools.base import (  # noqa: F401
    ServerTarget,
    TerminalTool,
    ToolContext,
    UserPromptOption,
    UserPromptRequest,
    tool_err,
    tool_ok,
)
from servers.services.terminal_ai.agent.tools.files import (  # noqa: F401
    EditFileArgs,
    EditFileTool,
    ListFilesArgs,
    ListFilesTool,
    ReadFileArgs,
    ReadFileTool,
)
from servers.services.terminal_ai.agent.tools.meta import (  # noqa: F401
    AskUserArgs,
    AskUserOption,
    AskUserTool,
    DoneArgs,
    DoneTool,
    ListTargetsArgs,
    ListTargetsTool,
    RememberArgs,
    RememberTool,
    TodoWriteArgs,
    TodoWriteTool,
)
from servers.services.terminal_ai.agent.tools.search import (  # noqa: F401
    GrepArgs,
    GrepTool,
)
from servers.services.terminal_ai.agent.tools.shell import (  # noqa: F401
    ShellArgs,
    ShellTool,
)


def default_tool_set() -> dict[str, TerminalTool]:
    """Return the canonical mapping of tool-name → tool-instance.

    Mutating the returned dict does NOT affect future calls — each
    invocation builds a fresh mapping.
    """
    tools: list[TerminalTool] = [
        ShellTool(),
        ReadFileTool(),
        EditFileTool(),
        ListFilesTool(),
        GrepTool(),
        ListTargetsTool(),
        AskUserTool(),
        TodoWriteTool(),
        RememberTool(),
        DoneTool(),
    ]
    return {t.name: t for t in tools}


__all__ = [
    "TerminalTool",
    "ToolContext",
    "ServerTarget",
    "UserPromptOption",
    "UserPromptRequest",
    "tool_ok",
    "tool_err",
    "default_tool_set",
    # concrete tools
    "ShellTool",
    "ShellArgs",
    "ReadFileTool",
    "ReadFileArgs",
    "EditFileTool",
    "EditFileArgs",
    "ListFilesTool",
    "ListFilesArgs",
    "GrepTool",
    "GrepArgs",
    "ListTargetsTool",
    "ListTargetsArgs",
    "AskUserTool",
    "AskUserArgs",
    "AskUserOption",
    "TodoWriteTool",
    "TodoWriteArgs",
    "RememberTool",
    "RememberArgs",
    "DoneTool",
    "DoneArgs",
]
