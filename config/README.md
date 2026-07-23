# Config

Versioned runtime-adjacent configuration lives here when the tool does not require it at the repository root.

Root-level config files stay at the root only when external tools expect that exact location, for example `.github/`, `.pre-commit-config.yaml`, `.importlinter`, `docker-compose*.yml`, and `render.yaml`.

## Git / CI governance (F-11)

| File | Purpose |
| --- | --- |
| `github-governance.json` | Required check names, break-glass policy, stability clock fields |
| `ci-stability-ledger.json` | Unique green SHA ledger (reruns of the same SHA do not count) |
| `break-glass-log.json` | Logged emergency admin bypass incidents |

See `docs/architecture/CI_GOVERNANCE.md` and:

```bash
python scripts/github_governance.py
python scripts/github_governance.py --clock-status
```
