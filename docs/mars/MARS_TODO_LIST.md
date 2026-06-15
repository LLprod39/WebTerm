# MARS Refactoring Task Plan

Last reviewed: 2026-06-15

This is the current human-readable MARS refactor backlog. It replaces the old generated 41-task dump with current status.

## Completed

| Task | Status |
| --- | --- |
| Add architecture boundary fitness checks | Done. `.importlinter`, `pyproject.toml`, and `scripts/check_architecture_sizes.py` are present. |
| Normalize memory-store import path | Done. Canonical import is `servers.adapters.memory_store.DjangoServerMemoryStore`. |
| Move Django memory store into server adapter layer | Done. Implementation lives under `servers/adapters/`. |
| Extract focused memory adapter modules | Mostly done. Many `servers/adapters/django_memory_*.py` files exist. |
| Split backend view endpoint groups | Mostly done across `core_ui/views/`, `servers/views/`, and `studio/views/`. |
| Remove `servers.mcp_tool_runtime` shim | Done. File is absent; Studio owns concrete MCP runtime. |
| Remove `passwords/` package | Done. Folder is absent. |
| Extract terminal support services | Substantial progress. Terminal input, lifecycle, events, preferences, snapshots, AI subservices, and access helpers exist. |
| Add frontend domain API modules | In progress but started. `frontend/src/api/` exists. |
| Restore architecture guard | Done. `python scripts\check_architecture_sizes.py --strict-new` passes. |

## Immediate Task

### MARS-002: Route `output/report` Through Node Registry

Target files:

- `studio/pipeline_executor.py`
- `studio/executor/nodes/output_report.py`
- `studio/executor/nodes/__init__.py`
- `tests/test_studio_node_executors.py`
- `tests/test_studio_pipeline_v2.py`

Acceptance:

- Production pipeline execution uses the registry implementation for `output/report`.
- Existing report behavior is unchanged.

### MARS-003: Route `output/webhook` Through Node Registry

Target files:

- `studio/pipeline_executor.py`
- `studio/executor/nodes/output_webhook.py`
- `studio/executor/nodes/__init__.py`
- `tests/test_studio_node_executors.py`
- `tests/test_studio_pipeline_v2.py`

Acceptance:

- Production pipeline execution uses the registry implementation for `output/webhook`.
- Webhook payload shape and error behavior stay compatible.

### MARS-004: Migrate `logic/condition`

Target files:

- `studio/pipeline_executor.py`
- `studio/executor/nodes/logic_condition.py`
- `studio/executor/nodes/__init__.py`
- `tests/test_studio_node_executors.py`

Acceptance:

- Condition branch behavior remains identical.
- Source handle validation remains covered by `studio/pipeline_validation.py`.

### MARS-005: Migrate `logic/merge`

Target files:

- `studio/pipeline_executor.py`
- `studio/executor/nodes/logic_merge.py`
- `studio/executor/nodes/__init__.py`
- `tests/test_studio_node_executors.py`
- `tests/test_studio_all_nodes_smoke.py`

Acceptance:

- `all` and `any` merge semantics remain stable.
- Pending merge state remains compatible with existing `PipelineRun.routing_state`.

### MARS-006: Add Shared Execution Policy Contract

Target files:

- `app/agent_kernel/permissions/engine.py`
- `app/tools/safety.py`
- `servers/services/`
- `studio/pipeline_executor.py`
- `tests/test_agent_and_pipeline_policy_enforcement.py`

Acceptance:

- SSH, MCP, file, webhook, terminal AI, and pipeline execution paths expose the same risk/approval/audit decision shape.

### MARS-007: Add Capability-Based Server Share Checks

Target files:

- `servers/models.py`
- `servers/views/server_helpers.py`
- `servers/views/server_files.py`
- `servers/views/server_ops.py`
- `servers/consumers/ssh_terminal.py`
- `servers/consumers/rdp_terminal.py`
- `tests/test_servers_api_smoke.py`

Acceptance:

- View-only shares cannot execute commands, write files, open RDP, reveal secrets, or administer shares.

### MARS-008: Continue Frontend API Decomposition

Target files:

- `frontend/src/lib/api.ts`
- `frontend/src/api/auth.ts`
- `frontend/src/api/servers.ts`
- `frontend/src/api/studio.ts`
- `frontend/src/api/settings.ts`
- `frontend/src/api/agents.ts`
- affected callers/tests

Acceptance:

- Domain callers import from domain API modules.
- `frontend/src/lib/api.ts` shrinks without breaking compatibility exports.

### MARS-009: Extract Pipeline Editor Controller

Target files:

- `frontend/src/pages/PipelineEditorPage.tsx`
- `frontend/src/components/pipeline/`
- new feature/controller hook files
- `frontend/src/pages/PipelineEditorPage.test.tsx`

Acceptance:

- Route component loses data/mutation/run-monitor orchestration.
- Existing editor tests pass.

### MARS-010: Document Production Worker Topology

Target files:

- `README.md`
- `docs/`
- `docker-compose.production.yml`
- `render.yaml`

Acceptance:

- Required background processes are explicit.
- Unsupported deploy modes are clearly marked.

## Parking Lot

- Kubernetes read-only inventory.
- Kubernetes guarded actions after read-only inventory.
- GitOps / PR-based remediation.
- CI/CD status visualization in Studio.
- Time-series operational metrics.
