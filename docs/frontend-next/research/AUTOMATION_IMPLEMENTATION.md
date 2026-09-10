# Automation frontend implementation evidence

Implemented from current Django contracts on 2026-09-02. Previous frontend and Git history were not inspected or reused.

## Delivered vertical slices

* Playbook catalog, YAML/runbook creation, template installation, schema-driven guided recipes, raw YAML/archive/GitLab preview and hash-pinned import.
* Playbook workspace: metadata, structured runbook steps, YAML and project-file editors, expected-version/hash conflict handling, immutable revisions, publish/rollback/download, archive and immediate restore, explicit user/group grants, per-user binding profiles with secret replacement/removal.
* Launch: revision, binding, authorized server targets, inventory mapping, runtime variables, engine/check mode/become/concurrency, preflight and deliberate execution. Passwords remain in component memory and are cleared after submission.
* Compatibility: saved-file analysis, AI proposal, side-by-side source review, semantic checks, explicit apply bound to reviewed path/content hash/draft version/bundle hash/base revision. GitLab refresh displays file additions/changes/removals and creates a reviewed new revision.
* Pipeline catalog and actual React Flow editor: manifest-backed palette, source handles, typed nested configuration, context/entry selection, local self/cycle guard, server validation, save/run, clone/template/export/delete. New trigger nodes start inactive.
* Draft assistant: create/revise/template/validate/graph preview/apply/discard. Applying creates/updates a pipeline, execution remains an explicit action.
* Triggers: pipeline/node/type selection, cron, webhook header URL/token reveal/copy and signing secret, monitoring filters, edit/toggle/delete.
* Runs: cursor history, report progress with unknown totals preserved, host tasks, bounded delta logs, cancellation/retry with fresh variables, terminal report downloads; pipeline states with WebSocket updates and REST reconciliation, stop/resume/non-idempotent confirmation, dead-letter acknowledgment.
* Skills: catalog, scaffold templates, metadata/policies, rendered instructions, file workspace/create/save/delete/validation, staff sharing. General sharing mode is submitted only on explicit selection because backend `is_shared` also represents individual grants.
* Route-level lazy loading, feature guards and object capability controls, loading/error/empty states, responsive styles, unsaved editor guards for route/tab/file switches.

## Route feature mapping

| Routes | Feature |
| --- | --- |
| `/automation/playbooks`, `/:id`, `/automation/runs/playbook/:id` | `automation` plus object capabilities |
| `/automation/pipelines`, `/:id`, `/automation/drafts`, `/:id`, `/automation/schedules` | `studio_pipelines` |
| `/automation/runs/pipeline/:id` | `studio_runs` |
| `/automation/runs` | `automation` OR `studio_runs`; each dataset is gated separately |
| `/intelligence/skills`, `/:slug` | `studio_skills` plus object capabilities |

## Verification

* Area ESLint passed with no warnings/errors.
* Contract tests passed: 6 tests across graph transport, graph cycle prevention, inactive new triggers, typed nested settings, adaptation concurrency binding and backend `node_ids` validation navigation. Combined with TerminalAssistant: 10 tests in 3 files passed.
* Global TypeScript check passed after integration, including TerminalAssistant and server groups.
* Backend source references and non-obvious transport/permission constraints are recorded in `AUTOMATION_CONTRACTS.md`.
* Live browser/integration evidence belongs to the parent task. No SSH commands, playbooks, pipelines, external notifications, provider calls or GitLab fetches were executed by this implementation task.

## Backend limits surfaced honestly

Approval tokens are intentionally absent from run data; awaiting approvals link users to the assigned approval delivery flow. Studio run WebSocket ACL is narrower than REST, so REST reconciliation remains available. The library endpoint has no archived-list filter; restore is offered immediately after archive. Historical execution and live environment/provider readiness cannot be established by client-side tests.

## Authored live QA tests

`frontend/tests/e2e/automation.spec.ts` contains four real-backend scenarios, restricted to `http://127.0.0.1:8091`: YAML create/edit/reload/archive/restore; visual node/edge configuration with rejected saves, field-error navigation, persisted graph and validate-only preflight; optimistic draft conflict preserving user text; and an isolated pure `logic/condition` run that performs no remote operation. Fixtures are unique `qa_auto_*` entities and cleanup checks their identity.

Parity review corrected backend readiness issue navigation from `node_ids[]` and now renders structured save rejection details while preserving the unsaved graph. Error messages already represented by issues are not repeated.

## Real QA execution — 2026-09-02

Automation plus server-group suites: **6 passed in 56.6 seconds**, Chromium, QA frontend 8091 and backend 9001. The four automation scenarios passed against the real PostgreSQL-backed API. The initial pure run correctly remained pending because the isolated QA service had no pipeline dispatcher. A test-only helper now executes its single fixture through the real `claim_next_pipeline_dispatch` and `execute_pipeline_dispatch` functions.

`frontend/tests/backend/run_safe_pipeline.py` refuses every database except `webterm_frontend_qa_20260902` (both configured name and live `current_database()`), requires `qa_settings`, the `qa_auto_pure_run_` prefix, the QA owner, a fresh run with empty context, exact `trigger/manual → logic/condition(always_true)` snapshot, and no other live queue entry. It holds the existing dispatch-control transaction while checking and claiming; no production execution code or general worker was changed. The E2E invokes it using `WEBTERM_QA_PYTHON` or the local `.venv`/CI Python.

Visual corrections validated in the same run: long catalog descriptions clamp to two lines; Russian node-count forms are correct; React Flow controls, minimap, edge labels and pattern use app theme tokens and `colorMode`. The dark screenshot was visually inspected. Assertions verify both the dark class and actual control/minimap background colors.

Evidence: `frontend/playwright-report-automation/index.html`, `frontend/test-results-automation/.last-run.json`, and explicit screenshots `frontend/test-results/automation-playbook-workspace.png`, `automation-pipeline-canvas.png`, `automation-pipeline-canvas-dark.png`, `automation-pure-run-report.png`. These isolated results establish the tested workflows, not readiness of external integrations or production workers.

## Persisted run canvas — final parity correction

Pipeline run detail now includes a lazy-loaded, read-only React Flow canvas. It renders the run's `nodes_snapshot`, `edges_snapshot` and actual public `node_states`; it never substitutes the current pipeline graph. The same `WorkflowNode` renderer is used by the editor, draft preview and run view. Canvas selection and the accessible step table both select the adjacent output/error/timing panel. WebSocket updates and REST reconciliation update the node badges. Nodes without a persisted state display “Нет результата”; no synthetic pending/completed status is inferred from the whole run.

The run view requires only `studio_runs`; it does not fetch the separately gated pipeline manifest API. Source handles are derived from the saved edges. Editing, connecting, reconnecting and deleting are disabled. Light/Dark controls use the same theme tokens as the editor. When an older backend omits `edges_snapshot`, the canvas explicitly reports unavailable connections and still shows saved nodes, without inventing edges.

This required the **third minimal backend change** in the frontend project (after group membership listing and sudo file-path escaping): `studio/model_serializers.py` adds the already stored `edges_snapshot` field to `pipeline_run_to_dict`. It is an additive response field under unchanged run ACLs, with no migration or execution-engine change. `tests/test_pipeline_run_snapshot_contract.py` changes the current pipeline after persisting a run, then verifies the actual run-detail API still returns the original nodes, source handles, edges and statuses; a second case preserves an empty edge snapshot. Both tests passed: **2/2, 40.25 seconds**. Ruff check and format passed for the serializer and regression test.

The existing pure-condition E2E additionally asserts one snapshot edge, no fabricated initial node status, the persisted completed badge, and selection from the canvas into the result panel. Its final integrated execution is recorded by the parent task after restarting the QA API with the additive field.
