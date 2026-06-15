# MARS Architecture Refactoring Status

Last reviewed: 2026-05-27

This folder now records the current status of the MARS-driven refactor history. It is not the live queue source of truth; live MARS queue/debug state, when needed, lives outside this docs folder.

## Current Summary

| Area | Status |
| --- | --- |
| Import boundaries | Green. `import-linter` passed during `python scripts\check_architecture_sizes.py --strict-new`. |
| Size guard | Red. `key_mcp.py` grew to `2094` lines against pinned baseline `2089`. |
| Memory store import path | Done. Callers use `servers.adapters.memory_store.DjangoServerMemoryStore`. |
| MCP runtime ownership | Done. `servers.mcp_tool_runtime` is deleted; server agents use `MCPRuntimeProvider`; Studio owns concrete MCP runtime. |
| `passwords/` package | Done. Folder is absent. |
| Backend view split | Mostly done. Focused modules own endpoint groups; `_views_all.py` files are compatibility shims. |
| Terminal service extraction | Substantial progress. Many terminal input, lifecycle, AI, event, snapshot, and preference services exist. |
| Studio node registry | In progress. Target registry exists; production executor is still mostly `studio/pipeline_executor.py`. |
| Frontend decomposition | In progress. Domain API modules exist; large route/components remain pinned. |

## Immediate Next Action

Fix the architecture guard:

```powershell
python scripts\check_architecture_sizes.py --strict-new
```

Current known failure:

```text
[LEGACY GROWTH] .\key_mcp.py
Legacy file grew: 2094 > 2089
```

Prefer shrinking/extracting `key_mcp.py`. Re-pin the baseline only if the growth is intentional and documented.

## Completed Refactor Themes

- Architecture checker and import-linter contracts were added.
- Django memory store implementation moved behind `servers.adapters.memory_store`.
- Many memory workflows moved into focused `servers/adapters/django_memory_*.py` modules.
- `core_ui`, `servers`, and `studio` view endpoint groups were split into focused modules.
- Terminal services were extracted for command parsing, connection records, command history, preferences, report generation, memory extraction, planning, decisions, output explanation, access, connection options, events, lifecycle, plan items, and snapshotting.
- MCP runtime bridge was inverted through `MCPRuntimeProvider`.

## Open Refactor Themes

- Restore green architecture guard.
- Continue shrinking legacy-large files.
- Finish Studio node-registry migration.
- Continue frontend API/controller decomposition.
- Convert remaining broad permission checks into explicit capability checks.
- Keep production worker topology explicit in docs and deploy config.

## How To Resume Refactor Work

1. Check `git status --short`.
2. Run the architecture guard.
3. Pick one narrow task from `docs/mars/MARS_TODO_LIST.md`.
4. Update tests for that task only.
5. Update this status file if the refactor status changes.
