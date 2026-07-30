# WebTerm architecture contract

Last reviewed: 2026-07-30

This is the versioned human-readable contract enforced by `.importlinter`,
`pyproject.toml`, `scripts/check_architecture_sizes.py` and
`scripts/check_architecture_no_regression.py`.

## Import boundaries

The eleven contracts in `.importlinter` are authoritative. Shared `app` layers
must not depend on Django ORM or feature applications; `core_ui`, `servers`,
`studio` and `plugin_marketplace` communicate across domain boundaries through
typed providers, registries or events. Adding an exception to hide a new edge
is not an architecture fix.

Monitoring, forecasting, live telemetry and watcher implementations live in
`servers.monitoring`. That package must not depend on HTTP views, websocket
consumers, or `studio`. The historical `servers.monitor` and
`servers.monitoring_live` modules remain compatibility facades for supported
public imports while internal callers use the domain package directly.

Agent execution, scheduling, reporting and multi-agent orchestration live in
`servers.agents`. The package is independent from HTTP views and websocket
consumers; the historical `servers.agents` mini-agent API is preserved through
lazy package exports so importing an agent submodule has no startup side effects.

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

Run both views of the gate:

```bash
python scripts/check_architecture_no_regression.py
python scripts/check_architecture_sizes.py --strict-new
```

## Current status

**Architecture fitness (2026-07-30): complexity/coupling gate green.**

- All eleven import contracts kept; 0 forbidden import edges.
- `python scripts/check_architecture_sizes.py --strict-new` → **SUCCESS**
  (111 frozen complexity/coupling violations, 0 new or grown violations).
- `python scripts/check_architecture_no_regression.py` → **0 frozen size
  violations**, 0 frozen import edges.
- Product/app/frontend/tests modules are under the 500-line review target. The
  only remaining line baseline pin is `.tools/k8s-provider-fixture.py`; line
  count no longer decides pass/fail.

Every split must preserve public imports and behavior with characterization
tests before the extraction, update both debt baselines downward only, and run
the focused tests plus both architecture commands. `--update-metrics-baseline`
is a deliberate review operation, never a routine way to make CI green.
