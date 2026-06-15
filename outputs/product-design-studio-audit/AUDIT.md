# Product Design Audit: Studio

Date: 2026-06-10
Surface: WebTerm Studio overview and AI Drafts
Evidence folder: `C:\WebTrerm\outputs\product-design-studio-audit`

## Captured Steps

1. `01-studio-overview-desktop.png` - Studio overview, desktop 1440x900.
2. `02-studio-drafts-desktop.png` - AI Drafts workspace, desktop 1440x900.
3. `03-studio-overview-mobile.png` - Studio overview, mobile 390x844.
4. `04-studio-drafts-mobile.png` - AI Drafts workspace, mobile 390x844.

## Step 1: Studio Overview Desktop

Health: mixed.

Strengths:
- The left app shell is stable and recognizable.
- Navigation clearly exposes Studio sections: Overview, AI Drafts, OPS Skills, MCP Tools, Agents, Runs, Alerts.
- Primary action `New pipeline` is easy to find.

UX/design issues:
- The page still behaves like a hero/marketing panel, with a large `Pipelines` banner and another large `AI Drafts` promo block below it.
- The AI Drafts block repeats navigation already present in the top Studio nav, so it competes with the actual pipeline list.
- Copy mixes product jargon and internal implementation terms: `Graph-first cockpit`, `DAG`, `composer`, `resources`, `risk review`.
- The pipeline card is visually smaller than the promo sections, even though pipelines are the core object on this screen.

Accessibility risks:
- Several labels are short and icon-heavy; keyboard focus order needs a live check.
- Low-contrast secondary text in the promo block may be difficult on dark backgrounds.

Recommendation:
- Make Overview a compact operations index: status row, pipeline list, draft queue summary, recent failures. Remove the oversized promo feeling.

## Step 2: AI Drafts Desktop

Health: promising but dense.

Strengths:
- The three-column layout has a clear mental model: queue, graph preview, composer/review.
- Draft status is visible at the top and in the queue.
- Risk and validation are visible before applying a draft.

UX/design issues:
- The graph canvas is visually dominant but the captured graph sits very low in the canvas, leaving a large empty grid above.
- The right panel mixes composer, preset buttons, review, metrics, tabs, assumptions, questions, and apply actions in one long column.
- The stats show `0 nodes / 0 edges / 0 edits` while the canvas badge says `4 nodes / 3 edges`, creating conflicting system feedback.
- Buttons use English action labels in a Russian/English mixed product surface: `Quick skeleton`, `Open canvas`, `Validate / dry-run`.

Accessibility risks:
- Dense three-column layout may create difficult tab order and screen-reader context switching.
- The disabled-looking action buttons need contrast/focus verification.

Recommendation:
- Split the right panel into two states: `Composer` before draft generation, `Review & Apply` after draft generation. Keep the graph centered and make node counts consistent.

## Step 3: Studio Overview Mobile

Health: usable but too long.

Strengths:
- Content stacks without horizontal overflow.
- Primary action remains visible.
- Pipeline card remains readable.

UX/design issues:
- Top Studio nav horizontally clips; the user sees only part of the section list.
- The hero card consumes too much first viewport height.
- AI Drafts promo card pushes the actual pipeline list down.
- The `No active trigger` badge wraps into a tight two-line pill.

Accessibility risks:
- Small badges and compact action groups may be hard to tap.
- Horizontal nav needs keyboard and touch scroll testing.

Recommendation:
- On mobile, collapse Studio section navigation into a segmented drawer or compact horizontal list with stronger scroll affordance. Put pipelines before promo content.

## Step 4: AI Drafts Mobile

Health: high risk.

Strengths:
- The page technically avoids horizontal overflow.
- Draft queue, graph, composer, review, and apply actions are all present.

UX/design issues:
- The mobile page becomes one very long stacked workspace: queue, graph, composer, review, and actions all compete in sequence.
- Graph preview is difficult to use at 390px width; nodes are tiny and partially off-screen.
- The composer starts far below the top, so the main task is delayed.
- Action buttons at the bottom can feel disconnected from the graph/review they apply to.

Accessibility risks:
- Graph canvas controls are tiny for touch.
- Long scroll depth makes it easy to lose context between draft, graph, and apply action.

Recommendation:
- On mobile, use tabs: `Queue`, `Graph`, `Compose`, `Review`. Keep the active draft summary sticky above tabs.

## Priority Fixes

1. Replace `StudioHero` usage with a compact `PageHero`/operation header that follows `frontend/DESIGN.md`.
2. Rename mixed-language labels and internal terms:
   - `AI Drafts cockpit` -> `Draft-пайплайны` or `Черновики пайплайнов`
   - `Graph-first cockpit` -> `Сборка пайплайна по описанию`
   - `Quick skeleton` -> `Быстрый шаблон`
   - `Build DAG` -> `Собрать граф`
   - `risk/apply actions` -> `риски/действия применения`
3. Make Studio overview prioritize operational objects: pipelines, active drafts, recent failed runs.
4. Center or fit the draft graph in its canvas on first render.
5. Fix node/edge count inconsistency between graph badge and review metrics.
6. Add a mobile AI Drafts layout with tabs instead of one long stacked page.
7. Add visual regression coverage for the current Studio heading (`Pipelines`), because the old snapshot expected `Pipeline Workspace`.

## Evidence Limits

- Screenshots used mocked platform data, not a live production backend.
- This audit did not verify keyboard navigation, screen-reader output, or color contrast numerically.
- This audit did not apply code changes to the product UI.
