# WebTerm architecture contract

Last reviewed: 2026-07-30

This is the versioned human-readable contract enforced by `.importlinter`,
`pyproject.toml`, `scripts/check_architecture_sizes.py` and
`scripts/check_architecture_no_regression.py`.

## Import boundaries

The sixteen contracts in `.importlinter` are authoritative. Shared `app` layers
must not depend on Django ORM or feature applications; `core_ui`, `servers`,
`studio` and `plugin_marketplace` communicate across domain boundaries through
typed providers, registries or events. Adding an exception to hide a new edge
is not an architecture fix.

Monitoring, forecasting, live telemetry and watcher implementations live in
`servers.monitoring`. That package must not depend on HTTP views, websocket
consumers, or `studio`; callers import the defining domain module directly.

Agent execution, scheduling, reporting and multi-agent orchestration live in
`servers.agents`. The package is independent from HTTP views and websocket
consumers; the historical `servers.agents` mini-agent API is preserved through
lazy package exports so importing an agent submodule has no startup side effects.

Operator read tools, mutating actions and the server-side provider live in
`servers.operator`. Operator may call agent and monitoring services, while the
reverse dependency is forbidden.

Durable playbook leasing and execution live in `servers.playbooks`, below HTTP,
websocket and orchestration layers.

Studio validation, execution, runtime state and interaction services live in
`studio.pipeline`, independent from HTTP/websocket delivery and the `servers`
feature app.

MCP clients, subprocess/network policy, tool binding and demo adapters live in
`studio.mcp`, independent from HTTP/websocket delivery and `servers`.

Pipeline action classification, approval decisions and policy audit metadata
live in the leaf package `studio.policy`. Pipeline execution may depend on this
policy package, while the reverse dependency is forbidden.

## Complexity and coupling rules

- Cyclomatic complexity blocks at `>30` per Python function.
- Internal module fan-out blocks at `>20`; fan-in blocks at `>40`.
- Existing complexity/coupling debt is frozen numerically in
  `config/architecture-metrics-baseline.json`. New violations and growth above
  a frozen value fail CI. The baseline should only shrink after refactoring.
- The terminal consumer additionally has an executable state contract: AI,
  manual-command and SSH transport state are explicit dataclasses, legacy
  cross-mixin fields are forbidden, and the consumer declares fewer than 20
  state fields.
- 500 physical lines remains a non-blocking warning and review signal. New
  extracted modules should still target fewer than 500 lines; route, view and
  coordinator modules should target 300 lines or less.

## Exception visibility

- Ruff rules `E722` and `B904` are mandatory: bare handlers and raises that
  lose the original cause fail CI.
- Ruff rule `S110` forbids silent `try`/`except`/`pass` anywhere in the Python
  tree. Best-effort fallbacks must emit a sanitized debug/warning event.
- Security classifiers use specific exception types. Broad catches are allowed
  only at external execution boundaries where they log and convert the failure
  into an explicit failed/cancelled run or tool result.

Run both views of the gate:

```bash
python scripts/check_architecture_no_regression.py
python scripts/check_architecture_sizes.py
```

## Current status

**Architecture fitness (2026-07-30): complexity/coupling gate green.**

- All sixteen import contracts kept; 0 forbidden import edges.
- `python scripts/check_architecture_sizes.py` → **SUCCESS**
  (110 frozen complexity/coupling violations, 0 new or grown violations).
- `python scripts/check_architecture_no_regression.py` → **0 frozen size
  violations**, 0 frozen import edges.
- No file has a legacy size pin. Files over 500 lines remain visible warnings,
  while line count never decides pass/fail.

Every split must preserve public imports and behavior with characterization
tests before the extraction, update both debt baselines downward only, and run
the focused tests plus both architecture commands. `--update-metrics-baseline`
is a deliberate review operation, never a routine way to make CI green.
