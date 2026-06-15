# WebTerm Documentation

Last reviewed: 2026-05-27

This folder is the documentation source for the current `C:\WebTrerm` checkout. Root-level documentation stays limited to files required by common tools or the public project entry point.

## Current Map

| Path | Purpose | Status |
| --- | --- | --- |
| `PROJECT_STRUCTURE.md` | Current repository layout, active modules, generated/local-only paths. | Current |
| `PIPELINE_NODES_SPEC.md` | Studio pipeline graph contract and supported node types. | Current |
| `architecture/` | Short architecture entry points and the Studio OPS automation platform plan. | Current |
| `qa/qa_master_plan.yaml` | Canonical QA plan and automation baseline. | Current |
| `reports/` | Current audit, roadmap, review plan, and frontend worklog. | Current |
| `mars/` | Historical MARS architecture/refactor artifacts kept as status and migration context. | Current snapshot |
| `local/` | Ignored internal docs copied from older root docs. Not published by git. | Local-only |

## Editing Rules

- Update this index when a doc is added, removed, renamed, or demoted to historical status.
- Prefer concise current-state docs over long stale reports.
- Do not put secrets, local credentials, dumps, Playwright reports, or generated bundles in `docs/`.
- For architecture rules, keep `pyproject.toml`, `.importlinter`, and `docs/local/ARCHITECTURE_CONTRACT.md` aligned.
