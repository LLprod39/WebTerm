# Project Audit Report

Last reviewed: 2026-06-15

This is the current audit snapshot for `C:\WebTrerm`. Older findings that were already fixed are kept only when they affect remaining work.

## Executive Summary

WebTerm is an ops control plane built from Django/Channels, a React/Vite SPA, server terminal/RDP tooling, Studio pipelines, MCP/skills, server agents, and layered server memory.

Current architecture is much healthier than the older audit described: most backend view groups have been split into focused modules, the old `servers.mcp_tool_runtime` shim is gone, and the `passwords/` compatibility package is gone. Import boundaries currently pass through `import-linter`.

The main open risks are now narrower:

1. Dangerous execution paths still need one shared policy/audit/redaction contract across SSH, MCP, webhooks, files, and pipeline nodes.
2. Shared server permissions still need capability-level enforcement for connect/execute/file-write/RDP/admin.
3. Several legacy-large files remain pinned and should shrink over time.
4. Production worker/scheduler topology needs to stay explicit in deploy docs and compose/Render config.

## Current Architecture Evidence

| Area | Current state |
| --- | --- |
| Import boundaries | `import-linter` passed on 2026-06-15. Contracts live in `.importlinter`. |
| Size guard | Green on 2026-06-15. `key_mcp.py` is 1865 lines against pinned baseline 2089. |
| Backend views | `core_ui/views/`, `servers/views/`, and `studio/views/` are split into focused modules with compatibility shims. |
| MCP runtime | Server agents use `MCPRuntimeProvider`; concrete implementation lives in `studio.mcp_runtime_adapter` / `studio.mcp_tool_runtime`. |
| Passwords shim | No `passwords/` folder exists; only historical/migration references remain. |
| Pipeline executor | `studio/pipeline_executor.py` still executes the full node set; `studio/executor/` is the target registry migration path. |
| Test config | `pyproject.toml` points pytest to `web_ui.settings.test`, which isolates tests on SQLite and in-memory services. |

## Findings

### P0: Execution Policy Is Still Cross-Cutting

SSH commands, MCP calls, file writes, outbound webhooks, pipeline execution, terminal AI, and server agents all represent potentially mutating operations.

Impact: risk decisions can diverge between runtime paths.

Recommended fix: define one `ExecutionPolicyDecision` contract with actor, target, operation kind, redacted preview, risk categories, approval requirement, and audit evidence. Wire it into pipeline nodes and server/terminal tool paths.

### P0: Shared Server Permissions Need Capability Checks

`ServerShare`-style access should not be treated as one broad "server is accessible" decision for every endpoint.

Impact: view-only users can become risky if an endpoint only checks broad server accessibility.

Recommended fix: enforce explicit capabilities: view, terminal connect, command execute, file read, file write, RDP, context view, share/admin.

### P1: Secret Redaction Should Be Applied At Every Egress Point

Memory redaction exists, but pipeline outputs, MCP args, logs, activity records, and report excerpts should all use a shared redaction helper.

Impact: operational logs and reports can become a leakage path even when prompts are sanitized.

Recommended fix: one egress redaction helper, unit tests with tokens/passwords/private keys/high-entropy values, and targeted checks for logger/activity/event writes.

### P1: Legacy-Large Files Remain

The repository still carries large pinned files such as `frontend/src/pages/PipelineEditorPage.tsx`, `frontend/src/lib/api.ts`, `servers/consumers/ssh_terminal.py`, `studio/pipeline_executor.py`, `key_mcp.py`, and others in `pyproject.toml`.

Impact: changes are harder to review and regression risk remains high.

Recommended fix: continue one-domain-at-a-time extraction, and remove baseline entries once files fall below the standard limit.

### P1: Pipeline Executor Migration Is Incomplete

The target registry exists under `studio/executor/`, but the production path still runs through `studio/pipeline_executor.py` for most node types.

Impact: node-specific logic remains centralized and difficult to test independently.

Recommended fix: migrate one node at a time to `BaseNode` implementations and keep `tests/test_studio_node_executors.py` plus runtime smoke tests green.

### P2: Production Worker Topology Needs Explicit Ownership

Management commands exist for monitor, scheduled pipelines, scheduled agents, watchers, memory dreams, and agent execution plane.

Impact: a deployment can serve HTTP while silently missing background behavior.

Recommended fix: document and configure required worker processes for production compose/Render or explicitly mark unsupported modes.

## Completed Since Older Audits

- Architecture guard is green again: `python scripts/check_architecture_sizes.py --strict-new` passes.
- `servers.mcp_tool_runtime` shim removed.
- `passwords/` package removed.
- Backend view monolith split is largely done.
- `web_ui.settings` is a compatibility shim; explicit settings modules exist.
- Frontend app is clearly under `frontend/`.
- Test settings isolate DB/email/Celery/channel layer.
- `.dockerignore` and `.gitignore` cover key generated and secret-prone paths.

## Recommended Next Order

1. Add shared execution policy/audit/redaction contract.
2. Add capability-based shared server permissions.
3. Normalize egress redaction across logs/activity/pipeline/MCP.
4. Continue pipeline executor node-registry migration.
5. Continue frontend API/page decomposition.
6. Make production worker topology explicit.
