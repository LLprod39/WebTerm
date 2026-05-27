# Frontend UI/UX Worklog

This file is the continuation anchor for the frontend UI/UX and copy cleanup work.
Use it when conversation context is missing or compacted.

## Project Context

- Repository root: `C:\WebTrerm`.
- Frontend app: `frontend`.
- Frontend stack: React 18, TypeScript, Vite, React Router, TanStack Query, Radix UI, Tailwind, shadcn-style local UI components, lucide-react.
- Product shape: local OPS automation platform. Studio is for operations automation, not for writing code as the primary user task.
- Backend/Django architecture work may be happening in parallel. Do not revert unrelated backend or architecture changes.

## Current Product Direction

- Keep the UI work-focused, quiet, and operational.
- Prefer OPS language: runbook, playbook, tool registry, pipeline, approval, verification, health, risk.
- Avoid AI/marketing wording that makes the product feel vague or magical.
- `Studio Skills` should read as OPS playbooks/runbooks for controlled automation.
- MCP UI should read as a tool/integration registry, not as a developer toy.

## Active Skills To Use

- `ui-ux-pro-max`: use for interaction size, layout, accessibility, touch targets, visual hierarchy.
- `design-md`: use for maintaining this worklog/design direction when context changes.
- `frontend-testing-debugging`: use after frontend changes; attempt Browser plugin first, then fall back to Playwright if Browser invocation fails.
- Useful next skills when needed:
  - `web-accessibility`: keyboard, aria labels, focus states.
  - `shadcn-ui`: component consistency when adding or normalizing components.
  - `stitch-loop`: screenshot -> critique -> fix loops.
  - `taste-skill` / `platform-design`: final visual polish.
  - `figma`: only if creating a separate design system or mockups.

## Validation Routine

From `C:\WebTrerm\frontend`:

```bash
npx eslint <changed frontend files>
npm run build
git diff --check -- <changed frontend files>
```

Rendered smoke:

- Dev server currently used: `http://127.0.0.1:5173`.
- In-app Browser has failed in this environment with:
  `failed to write kernel assets: Системе не удается найти указанный путь. (os error 3)`.
- If Browser still fails, use Playwright + Chrome fallback and record that in the final answer.
- Smoke checks should verify:
  - page is not blank;
  - no Vite/framework overlay;
  - no relevant console errors;
  - no horizontal overflow on desktop and mobile;
  - at least one real interaction per changed surface.

## Completed UI/UX Work

- Normalized general button sizing and added `xs` button variant.
- Improved app shell/sidebar/header target sizes and grouped nav.
- Cleaned Studio nav labels toward OPS language.
- Simplified settings layout visuals and removed decorative noise.
- Humanized/cut down text in Agents, MCP Hub, Settings AI, and locales.
- Extracted MCP dialog/report UI into:
  - `frontend/src/components/studio/MCPForm.tsx`
  - `frontend/src/components/studio/AgentReportModal.tsx`
- Improved `Servers` buttons/tabs/playbook controls.
- Improved `StudioSkillsPage` filters, tabs, workspace buttons.
- Improved terminal `AiPanel` toolbar/input/report actions.
- Created this worklog as the continuation source for frontend UI/UX work.
- Improved `PipelineRunsPage`:
  - localized OPS copy in hero/status/filter labels;
  - larger filter/action targets;
  - mobile detail/list layout no longer keeps two panes side by side;
  - run detail actions, report copy, node rows, and raw JSON toggle are more touch-friendly.
  - detail rendering is now split into `frontend/src/components/studio/PipelineRunDetail.tsx`.
  - fixed mobile back-to-list behavior by preventing immediate auto-selection after closing detail.
  - live WebSocket connection now starts only for loaded `running` / `pending` runs, avoiding unnecessary socket warnings for completed runs.
- Improved top-level shell in `PipelineEditorPage`:
  - larger toolbar buttons and responsive wrapping;
  - `AI Builder` visible copy changed to assistant/operator wording;
  - palette hides on narrow screens to reduce overflow;
  - side panel becomes a mobile overlay instead of forcing horizontal layout;
  - run dialog buttons/text are more OPS-oriented and touch-friendly.
- Improved `/studio` overview:
  - localized visible Studio dashboard copy toward OPS/runbook language;
  - replaced visible `AI Automation Agent` framing with assistant/operator wording;
  - increased key card/menu/run/dialog button targets;
  - added localized pipeline activity text helpers in `frontend/src/components/studio/StudioActivityText.ts`;
  - fixed mobile `StudioNav` left offset so the sidebar toggle no longer covers the Studio label.
- Improved access settings pages:
  - normalized select/input/action heights on `/settings/users`, `/settings/groups`, and `/settings/permissions`;
  - made icon-only edit/password/delete/toggle actions larger and accessible via `aria-label`;
  - kept permission row actions visible on mobile instead of hover-only;
  - kept changes UI-only with no access API behavior changes.
- Improved full terminal workspace:
  - normalized `/servers/hub` toolbar touch targets to 40px where possible;
  - replaced nested tab close controls with separate buttons for valid, accessible interaction;
  - added `aria-pressed` to SFTP/Linux/AI mode toggles and `aria-label` to icon-only actions;
  - made the server picker a real dialog with larger close/search/row targets;
  - fixed mobile header spacing so the global sidebar trigger no longer overlaps `Назад`;
  - kept terminal/WebSocket behavior unchanged.
- Improved `SftpPanel`:
  - localized visible file actions and states to Russian (`Загрузить`, `Обновить`, `Открыть`, `Скачать`, `Передачи`);
  - increased primary file-panel controls from dense 32px actions toward 36px+ targets;
  - added clearer labels for parent-folder and transfer remove/cancel actions;
  - kept file operation API behavior unchanged.
- Improved `LinuxUiPanel` shell:
  - localized launcher, desktop icon titles, app subtitles, taskbar labels, context menus, overview action buttons, and window control aria labels;
  - increased workspace window control targets from 28px to 32px;
  - made uptime/window-count/status labels more human-readable in Russian;
  - added stable empty-array constants to remove existing `react-hooks/exhaustive-deps` warnings in the component;
  - kept service/process/docker action behavior unchanged.

## Latest Verified Smoke

Last verified routes:

- `/servers` desktop and mobile.
- `/studio/skills` catalog and workspace.
- `/studio` desktop and mobile overview/search/manual-run dialog.
- `/settings/users`, `/settings/groups`, `/settings/permissions` desktop and mobile with mocked access API data.
- `/studio/runs` desktop and mobile list/detail/back-to-list.
- `/studio/pipeline/1` desktop and mobile, including opening the pipeline assistant.
- `/servers/hub` with real admin session:
  - desktop terminal shell;
  - AI side panel toggle;
  - SFTP side panel toggle;
  - server picker dialog;
  - mobile terminal header.
  - Linux workspace desktop shell;
  - Linux launcher menu;
  - Linux overview window;
  - Linux workspace mobile shell.

Result:

- Build passed.
- ESLint passed for the latest changed frontend files without new warnings.
- Build passed with the usual Browserslist/chunk-size warnings.
- No horizontal overflow in smoke.
- No relevant console errors.
- Browser plugin still failed in this environment with the known kernel-assets path error; Playwright + installed Chrome was used as fallback.
- Screenshots were written to `%TEMP%\webterm-ui-real\`.

## Current Next Focus

1. Next frontend targets:
   - deeper `LinuxUiPanel` pass inside `Services`, `Processes`, `Logs`, `Disk`, `Network`, `Docker`, and `Packages` windows.
   - mobile terminal readability: xterm itself wraps very aggressively on narrow screens even after header overlap is fixed.

2. Later deeper pass for `PipelineEditorPage`:
   - Node config panel control sizes.
   - Run monitor panel action sizes.
   - Palette discoverability on mobile/tablet.
   - Better confirmation treatment for risky execution actions.

## Guardrails

- Do not add a new UI framework.
- Use existing Radix/shadcn-style local components and lucide icons.
- Keep cards for repeated items and modals; avoid nested card-heavy marketing layouts.
- Keep touch targets near 40-44px where possible.
- Use aria labels for icon-only buttons.
- Do not change backend behavior during UI-only passes unless explicitly required.
- Do not stage or commit unless the user asks.
