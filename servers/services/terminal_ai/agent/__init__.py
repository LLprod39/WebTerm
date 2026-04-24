"""
servers.services.terminal_ai.agent — Interactive Terminal Agent (Nova).

A ReAct-style agent that lives inside an SSH terminal session. Unlike the
legacy plan-then-execute ``step``/``fast`` modes, the agent does NOT
pre-generate a full command list. Instead, every turn it picks the next
tool to call based on the latest observation — the same pattern used by
Claude Code, Cursor Agent, and similar systems.

Design goals
------------
- **Provider-agnostic**: uses JSON mode (:data:`stream_chat(json_mode=True)`)
  rather than native tool-calling, so it works on OpenAI/Claude/Gemini/
  Grok/Ollama with one code path.
- **Tool-first**: every capability is a :class:`TerminalTool` with a
  typed pydantic args schema and a :class:`ToolResult` return value.
- **Safe by default**: delegates command-safety decisions to the existing
  :mod:`app.tools.safety` and :mod:`servers.services.terminal_ai.policy`
  modules. Risky file edits take automatic snapshots (2.4).
- **Interruptible**: the loop checks a ``stop_requested`` flag every
  iteration so ``/stop`` from the user unwinds cleanly.
- **Budgeted**: hard caps on iterations and per-tool timeouts prevent
  runaway loops from burning tokens or the SSH session.

Public entry points
-------------------
- :class:`AgentContext`
- :func:`run_agent_loop`
- :class:`TerminalTool`
- :func:`default_tool_set`
"""

from servers.services.terminal_ai.agent.loop import (  # noqa: F401
    AgentContext,
    AgentResult,
    run_agent_loop,
)
from servers.services.terminal_ai.agent.schemas import (  # noqa: F401
    AgentStep,
    Todo,
    TodoStatus,
    ToolCall,
    ToolResult,
)
from servers.services.terminal_ai.agent.tools import (  # noqa: F401
    TerminalTool,
    ToolContext,
    default_tool_set,
)
