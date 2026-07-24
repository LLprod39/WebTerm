# WebTerm architecture contract

Last reviewed: 2026-07-23

This is the versioned human-readable contract enforced by `.importlinter`,
`pyproject.toml`, `scripts/check_architecture_sizes.py` and
`scripts/check_architecture_no_regression.py`.

## Import boundaries

The nine contracts in `.importlinter` are authoritative. Shared `app` layers
must not depend on Django ORM or feature applications; `core_ui`, `servers`,
`studio` and `plugin_marketplace` communicate across domain boundaries through
typed providers, registries or events. Adding an exception to hide a new edge
is not an architecture fix.

## File-size rules

- Standard source-file limit: 500 physical lines.
- New files above the limit fail the architecture gate.
- Existing debt is recorded in `config/quality-debt-baseline.json` only so the
  no-regression job can reject new or enlarged violations.
- The baseline must shrink as files are split; it must not be enlarged to make
  a red full gate look green.
- New extracted modules should remain below 500 lines; route, view and
  coordinator modules should target 300 lines or less.

Run both views of the gate:

```bash
python scripts/check_architecture_no_regression.py
python scripts/check_architecture_sizes.py --strict-new
```

## Current status

**F-09 (GER-22, 2026-07-23): architecture fitness green.**

- All nine import contracts kept; 0 forbidden import edges.
- `python scripts/check_architecture_sizes.py --strict-new` → **SUCCESS**
  (0 GOD-FILE, 0 LEGACY GROWTH).
- `python scripts/check_architecture_no_regression.py` → **0 frozen size
  violations**, 0 frozen import edges.
- Product/app/frontend/tests modules are under the 500-line standard limit.
  The only remaining `legacy_baselines` pin is `.tools/k8s-provider-fixture.py`
  (tooling fixture, must not grow).

Every split must preserve public imports and behavior with characterization
tests before the extraction, update the debt baseline downward only, and run
the focused tests plus both architecture commands.
