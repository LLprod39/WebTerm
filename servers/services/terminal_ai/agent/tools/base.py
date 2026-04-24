"""
Base classes for Terminal Agent tools.

Every tool is a :class:`TerminalTool` subclass with:
  - a ``name`` visible to the LLM
  - a ``description`` for the system prompt
  - a pydantic ``args_schema`` for typed argument validation
  - an async ``run(args, ctx)`` coroutine that returns a :class:`ToolResult`

This is intentionally simpler than :class:`app.tools.base.BaseTool` —
we want tight integration with the terminal session (SSH connection,
event emitter, snapshot service) rather than the generic kwarg-based
contract used by the pipeline tool registry.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from servers.services.terminal_ai.agent.schemas import ToolResult


@dataclass
class UserPromptOption:
    label: str
    value: str
    description: str = ""


@dataclass
class UserPromptRequest:
    question: str
    timeout_seconds: float
    options: list[UserPromptOption] = field(default_factory=list)
    allow_multiple: bool = False
    free_text_allowed: bool = True
    placeholder: str = ""


@dataclass
class ServerTarget:
    """A named server the agent can operate on during this session.

    The **primary** target is the server the user connected to (always
    available). **Extras** are opt-in — the user grants them for the
    current session via the terminal settings panel. They disappear
    when the WebSocket closes.

    SSH connections are lazy — extras only open a connection on first
    use (see :meth:`ensure_connected`).
    """

    name: str
    """Short handle the agent uses (``""`` / ``"primary"`` / custom)."""

    server_id: int
    """``servers.Server.id`` — canonical reference."""

    display_name: str = ""
    """Human-readable server name shown in UI + to the agent."""

    host: str = ""
    """Hostname/IP for logging and disambiguation."""

    ssh_conn: Any = None
    """asyncssh connection handle (None until first use for extras)."""

    read_only: bool = False
    """2.11: if True, only read-only commands permitted on this target."""

    is_primary: bool = False
    """True for the session's originating server."""

    description: str = ""
    """Optional free-text hint shown via `list_targets` (e.g. role=master)."""


@dataclass
class ToolContext:
    """Ambient context handed to every tool invocation.

    The agent loop constructs one per request and passes it to every
    tool. Fields that are not relevant to a particular tool are simply
    ignored.

    Fields are intentionally loosely typed (``Any``) for heavyweight
    runtime objects (consumer, Server model) so this module stays free
    of Django/asyncssh imports.
    """

    # --- server targets ----------------------------------------------------
    primary: ServerTarget | None = None
    """The session's own server (mandatory at runtime; optional here so
    tests can construct minimal contexts)."""

    extras: dict[str, ServerTarget] = field(default_factory=dict)
    """Extra targets the user authorised for this session only."""

    # --- identity / audit --------------------------------------------------
    user_id: int | None = None

    # --- async callbacks ---------------------------------------------------
    # Emit a WebSocket event to the user.
    emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    # Pause and wait for the user to type a reply. Returns text or None.
    prompt_user: Callable[[UserPromptRequest], Awaitable[str | None]] | None = None

    # Open SSH connection to an extra target on demand.
    # Signature: ``conn = await open_target(target_name)``.
    # Caller is responsible for caching the result on the ServerTarget.
    open_target: Callable[[str], Awaitable[Any | None]] | None = None

    # --- mutable per-loop state -------------------------------------------
    todos: list[dict[str, Any]] = field(default_factory=list)
    scratch: dict[str, Any] = field(default_factory=dict)

    # --- session flags -----------------------------------------------------
    dry_run: bool = False
    default_timeout: float = 30.0

    # ----------------------------------------------------------------------
    # Target resolution helpers
    # ----------------------------------------------------------------------

    def resolve_target(self, name: str | None) -> ServerTarget | None:
        """Return a target by name (``""`` / ``None`` = primary).

        Returns ``None`` when the name is unknown — tools should surface
        this as a tool error rather than raise.
        """
        if not name or name in ("", "primary", "self", "current"):
            return self.primary
        if self.primary and name == self.primary.name:
            return self.primary
        return self.extras.get(name)

    def all_targets(self) -> list[ServerTarget]:
        """Every target available this session (primary first)."""
        result: list[ServerTarget] = []
        if self.primary:
            result.append(self.primary)
        result.extend(self.extras.values())
        return result

    async def ensure_connection(self, target: ServerTarget) -> Any | None:
        """Return a live SSH connection for ``target``, opening one if
        needed. Returns ``None`` if unreachable / not configured."""
        if target.ssh_conn is not None:
            return target.ssh_conn
        if self.open_target is None:
            return None
        conn = await self.open_target(target.name)
        if conn is not None:
            target.ssh_conn = conn
        return conn


@runtime_checkable
class TerminalTool(Protocol):
    """Protocol implemented by every agent tool.

    Tools are singletons — the registry instantiates them once. State
    lives on the :class:`ToolContext`, not the tool instance.
    """

    name: str
    description: str
    args_schema: type[BaseModel]

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        """Execute the tool and return a :class:`ToolResult`."""
        ...


# ---------------------------------------------------------------------------
# Convenience helpers for tool authors
# ---------------------------------------------------------------------------


def tool_ok(output: str, *, data: dict[str, Any] | None = None) -> ToolResult:
    """Build a successful :class:`ToolResult`."""
    return ToolResult(ok=True, output=output, data=data)


def tool_err(error: str, *, fatal: bool = False, output: str = "") -> ToolResult:
    """Build a failed :class:`ToolResult`.

    ``output`` is optional — when populated it's what the LLM reads next;
    ``error`` is the machine-friendly cause.
    """
    return ToolResult(
        ok=False,
        output=output or f"ERROR: {error}",
        error=error,
        fatal=fatal,
    )
