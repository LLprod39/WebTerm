# WebTerm v0.1 performance budget

Status: enforced in CI for the controlled internal pilot profile.

This contract is a repeatable laboratory gate. It does not replace production telemetry or the independent pilot required by the Stage 1 exit criteria.

## Lighthouse entry budget

Command: `cd frontend && npm run build:budget && npm run performance:budget`

The gate serves the production bundle locally and runs Lighthouse three times against `/login`. Median results must satisfy:

| Signal | Budget |
|---|---:|
| Performance score | >= 0.75 |
| Accessibility score | >= 0.95 |
| Best Practices score | >= 0.90 |
| SEO score | >= 0.90 |
| First Contentful Paint | <= 2,500 ms |
| Largest Contentful Paint | <= 3,500 ms |
| Speed Index | <= 3,500 ms |
| Total Blocking Time | <= 300 ms |
| Cumulative Layout Shift | <= 0.10 |

The Playwright workflow uploads the three raw Lighthouse reports and `artifacts/lighthouse-budget.json`. The budget script uses the Chromium installed by Playwright when available, so CI does not depend on an implicit system browser.

## Interaction latency budget

Command: `cd frontend && npm run test:e2e:performance`

After warming the Dashboard and Servers route chunks, Playwright measures six sidebar navigations. The observed p95 from click to the destination heading becoming visible must be <= 1,000 ms. The per-sample JSON report is attached to the Playwright evidence bundle.

This warm-navigation contract deliberately excludes network/server latency. F-13a and the real pilot must separately prove cold install, authenticated server operations and end-to-end task success.
