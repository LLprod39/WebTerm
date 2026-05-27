# Project Audit Report

## 1. Executive Summary

This report documents the architectural flaws, anti-patterns, security issues, and performance bottlenecks identified within the `weu-ai-platform` (WebTerm) codebase. The project integrates Django, Django Channels, React/Vite, WinUI 3, and several background worker processes. While the system demonstrates a sophisticated combination of capabilities, several fundamental violations of the established bounds and best practices pose risks to maintainability, performance, and security.

## 2. Architectural Flaws & Anti-patterns

### Bounded Context Leakage
The `.importlinter` configuration explicitly flags anti-patterns that exist within the codebase:
- **`app.tools` imports from `servers` ORM**: The `servers_tools.py` and `ssh_tools.py` directly query Django models (`Server`, `ServerCommandHistory`, `ServerShare`, etc.). This tightly couples the execution logic of tools to the server database layer.
- **Deprecated `mcp_tool_runtime.py` in `servers`**: This module acts as a re-export shim to `studio`, violating the separation between the execution/AI boundaries (`servers`) and the orchestrator layer (`studio`).
- **Deep imports in models**: Models and background workers tightly intertwine. Cross-domain queries are abundant across `views/_views_all.py` logic.
- **`__init__.py` and wildcard imports**: There are un-sorted import blocks and wildcard imports (`from web_ui.settings.base import *`) inside settings files that obfuscate overrides.

### Circular Dependencies
- Inline imports inside methods (`from servers.models import ...` embedded within function bodies) are widely used across `app/agent_kernel/memory/store.py` and `app/tools/server_tools.py` to circumvent circular import crashes. This is a clear indicator that bounded contexts are improperly mapped.

## 3. Security Issues

### Subprocess / Execution Risks
- **Shell injections**: `core_ui/views/_views_all.py` uses `asyncio.create_subprocess_exec` executing parameters passed potentially from the environment or user.
- **`safety.py` limitations**: `is_dangerous_command` evaluates safety through basic Regex pattern matching (`\bkill\b`, `\brm -r\b`). It fails to account for basic shell obfuscations (e.g., `k\ill`, `r\m`, variables usage) or non-standard paths.

### Secrets and Encryption Management
- **Weak Iteration Counts**: `servers.encryption.PasswordEncryption` uses PBKDF2HMAC with 100,000 iterations. Modern standards recommend at least 600,000 iterations for PBKDF2-HMAC-SHA256, or using Argon2id.
- **Secret Redaction**: `app/agent_kernel/memory/redaction.py` attempts to sanitize credentials prior to AI and logging stages. The `secret_assignment` regex fallback is naive (`password|token=...`) and can easily miss keys injected dynamically via JSON strings, or leak secrets that do not conform to explicit naming schemes.

## 4. Performance Bottlenecks

### N+1 and Unbounded Queries
- **Unbounded object fetching**: In `core_ui/views/_views_all.py`, calls like `User.objects.all().prefetch_related("groups")` are fully loaded into memory without pagination. On a sizable deployment, fetching the full table into memory will degrade performance and crash background worker processes.
- **ORM calls inside loops**: In `servers/views/_views_all.py`, individual queries inside list iterations are visible in operations pertaining to `ServerGroupMember.objects.filter(group_id__in=group_ids, user=request.user)`.

### Event Loop Blocking
- Synchronous file and JSON parsing logic runs within asynchronous functions in the `agent_kernel` loop. Large strings and memory compactions are parsed using `ast.literal_eval` synchronously (e.g., in `store.py: _try_parse_list_literal`), which blocks the entire async event loop.

## 5. Recommendations for Improvement

1. **Refactor Bounded Contexts**: Move server-specific execution logic out of `app/tools` and into `servers/tools/`. Remove the deprecated `mcp_tool_runtime` shim from `servers`.
2. **Eliminate Inline Imports**: Reorganize domain logic to avoid circular dependencies, decoupling the database abstractions from domain interfaces.
3. **Enhance Execution Safety**: Replace regex-based shell safety checks with an AST-based parser (like `bashlex`) to definitively determine the binaries and parameters being executed.
4. **Upgrade Encryption**: Transition PBKDF2 iterations to 600,000 or adopt Argon2 for `PasswordEncryption`. Add specific secret scanning to detect entropy rather than relying purely on regex patterns.
5. **Optimize Database Queries**: Introduce pagination limits to list endpoints, and bulk fetch relationships before looping over groups/users.
6. **Decouple Sync from Async**: Use `sync_to_async` around heavy CPU-bound parsing algorithms (like AST logic) within the agent loops to prevent blocking Django Channels.
