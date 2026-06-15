# WebTerm Audit Development Plan

Last reviewed: 2026-05-27

This roadmap turns the current audit into implementation-sized work. It is intentionally shorter than the old report: completed cleanup is recorded, and open work is ordered by risk.

## Current Status

| Area | Status |
| --- | --- |
| Import boundaries | Green on 2026-05-27. |
| Architecture size guard | Red: `key_mcp.py` grew to `2094` lines against baseline `2089`. |
| Backend view split | Mostly complete; compatibility shims remain. |
| MCP runtime shim | Complete; `servers.mcp_tool_runtime` no longer exists. |
| `passwords/` compatibility package | Complete; folder no longer exists. |
| Pipeline node registry | In progress; target architecture exists, most execution still in `studio/pipeline_executor.py`. |
| Frontend decomposition | In progress; domain API modules exist, legacy-large files remain. |
| Security policy unification | Not complete. |
| Production worker topology | Needs explicit deployment documentation/config. |

## Phase 0: Restore Green Guardrails

### A0.1 Fix `key_mcp.py` Legacy Growth

Scope:

- `key_mcp.py`
- `pyproject.toml`

Steps:

1. Inspect recent changes around `key_mcp.py`.
2. Shrink or extract at least 5 lines to get back under the pinned baseline.
3. If extraction is not practical, intentionally re-pin with a note.
4. Run `python scripts/check_architecture_sizes.py --strict-new`.

Done when:

- Architecture guard passes.

## Phase 1: Security And Safety

### A1. Shared Server Permission Matrix

Goal: replace broad shared-server access with capability checks.

Capabilities:

- `view`
- `connect_terminal`
- `execute_command`
- `read_files`
- `write_files`
- `use_rdp`
- `view_context`
- `admin_share`

Done when:

- Shared view-only user cannot execute, write files, use RDP, reveal secrets, or administer shares.
- Owner behavior is unchanged.
- Regression tests cover negative cases.

### A2. Unified Execution Policy Gate

Goal: one policy/audit decision for SSH, MCP, file writes, webhooks, pipeline nodes, terminal AI, and server agents.

Decision fields:

- actor/user
- operation kind
- target
- redacted preview
- risk categories
- policy mode
- approval requirement
- audit evidence payload

Done when:

- Pipeline nodes and terminal/server tools use the same decision shape.
- Tests prove direct nodes cannot bypass the gate.

### A3. Shell Safety Parser Upgrade

Goal: improve `app/tools/safety.py` beyond regex-only detection.

Required cases:

- chained commands
- pipes to shell
- command substitution
- quoted executable names
- `bash -c`
- encoded script execution

Done when:

- Existing safe commands still pass.
- Obfuscated dangerous commands are detected.

### A4. Versioned Credential Encryption

Goal: introduce versioned encrypted payloads without breaking old secrets.

Done when:

- Legacy payloads decrypt.
- New payloads store version/kdf metadata.
- Rotation command reports counts without printing values.

### A5. Egress Redaction

Goal: apply redaction before logs, activity records, pipeline excerpts, MCP args, reports, memory, and prompt context.

Done when:

- Unit tests prove token/password/private-key/high-entropy samples are redacted at all egress points.

## Phase 2: Architecture And Legacy Cleanup

### B1. Continue Node-Registry Migration

Current:

- `studio/executor/registry.py` and `BaseNode` exist.
- `output/report` and `output/webhook` have registry implementations.
- `studio/pipeline_executor.py` remains the production executor.

Next:

1. Auto-register migrated nodes if not already imported by tests/runtime.
2. Route `output/report` through registry.
3. Route `output/webhook` through registry.
4. Migrate `logic/condition`.
5. Migrate `logic/merge`.

Done when:

- Node-specific logic shrinks out of `studio/pipeline_executor.py` with equivalent runtime behavior.

### B2. Continue Frontend API And Controller Split

Current:

- `frontend/src/api/auth.ts`, `servers.ts`, `settings.ts`, `studio.ts`, and `agents.ts` exist.
- `frontend/src/lib/api.ts` remains a large compatibility surface.

Next:

1. Finish moving auth/server/studio API callers to domain modules.
2. Extract controller hooks from large pages only when behavior is covered.
3. Keep UI redesign out of pure decomposition tasks.

Done when:

- Large pinned frontend files shrink without changing behavior.

### B3. Reduce Legacy-Large Backend Files

Targets:

- `key_mcp.py`
- `servers/consumers/ssh_terminal.py`
- `studio/pipeline_executor.py`
- `servers/models.py`
- `servers/adapters/django_memory_store.py`

Done when:

- Files shrink below pinned baselines.
- Baseline entries are removed once below the standard limit.

## Phase 3: Operations And Deployment

### C1. Worker Topology

Document and configure:

- backend HTTP
- Redis channel layer
- scheduled pipelines
- scheduled agents
- server monitor
- watchers
- memory dreams
- agent execution plane

Done when:

- Production compose/Render docs do not imply background features run inside the HTTP process unless that is explicitly true.

### C2. Time-Series Metrics

Start with operational metrics:

- CPU
- RAM
- disk
- network/load
- service status
- container health

Then add AI-memory health metrics:

- event count
- episode count
- dream duration
- compaction failures
- revalidation queue size

Done when:

- UI can render useful 1h/24h/7d operational history.

## Phase 4: Product Expansion

### D1. Kubernetes Read-Only First

Do not start with free-form `kubectl apply/delete`.

MVP:

- attach cluster
- list namespaces/workloads/pods/services/ingress
- logs/events/describe
- AI read-only diagnosis

Mutations come later through plan, dry-run, approval, apply, verify.

### D2. GitOps / PR-Based Remediation

Default for non-incident changes:

- create branch
- patch file
- run configured checks
- create PR/MR
- attach verification and rollback note

Direct SSH writes remain for incident/break-glass workflows.

### D3. CI/CD Visibility

Read-only first:

- GitHub Actions / GitLab pipeline status
- failed job summary
- relevant log excerpts
- Studio run context integration

## Recommended Work Order

1. Fix `key_mcp.py` guard failure.
2. Shared server capability checks.
3. Unified execution policy.
4. Egress redaction.
5. Shell safety parser.
6. Versioned encryption.
7. Node-registry migration.
8. Frontend decomposition.
9. Worker/deploy topology.
10. Metrics.
11. Kubernetes read-only.
12. GitOps remediation.
13. CI/CD visibility.

## Definition Of Done

- Architecture guard is green.
- Dangerous operations share one policy/audit/redaction contract.
- Shared server access is capability-based.
- Large files shrink over time instead of growing baselines by default.
- Production docs explain which worker process owns each background feature.
