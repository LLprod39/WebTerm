# Frontend UI/UX Worklog

Last reviewed: 2026-05-27

This file is the continuation anchor for frontend UI/UX and copy cleanup work.

## Project Context

- Repository root: `C:\WebTrerm`.
- Frontend app: `frontend/`.
- Stack: React 18, TypeScript, Vite, React Router, TanStack Query, Radix UI, Tailwind, local shadcn-style components, lucide-react.
- Product shape: work-focused ops automation platform, not a marketing UI and not a code-writing product first.
- Backend architecture work can happen in parallel. Do not revert unrelated backend changes.

## Product Direction

- Use ops language: server, terminal, runbook, pipeline, approval, verification, health, risk, evidence, tool registry.
- Avoid vague AI/marketing copy.
- Studio Skills should read as controlled runbooks/playbooks.
- MCP UI should read as a tool/integration registry.
- Keep dense operational pages readable and predictable.

## Validation Routine

From `C:\WebTrerm\frontend`:

```powershell
npm run build
npm run test
npm run test:e2e:smoke
```

For targeted UI edits:

```powershell
npx eslint <changed files>
npm run build
```

Rendered smoke should check:

- page is not blank;
- no Vite/framework overlay;
- no relevant console errors;
- no horizontal overflow at desktop and mobile widths;
- at least one real interaction on each changed surface.

## Current UI Surfaces

| Route/surface | Notes |
| --- | --- |
| `/servers` | Server inventory, groups, access, health, quick actions. |
| `/servers/hub` | Full terminal workspace with SSH shell, SFTP, Linux UI, AI panel, server picker. |
| `/studio` | Pipeline/runbook overview and manual run entry points. |
| `/studio/pipeline/:id` | Pipeline graph editor, node palette, node config panel, run monitor. |
| `/studio/runs` | Pipeline run list/detail/live status. |
| `/studio/skills` | Skill/runbook catalog and workspace. |
| `/settings/*` | Users, groups, permissions, access, AI, memory, audit, SSO. |
| `/agents` and related pages | Server agent configuration and run monitoring. |

## Completed UI/UX Work

- Normalized app shell/sidebar/header sizing and grouped navigation.
- Cleaned Studio labels toward ops language.
- Simplified settings layout visuals.
- Extracted MCP form and agent report modal into focused components.
- Improved `PipelineRunsPage` list/detail layout, live WebSocket behavior, mobile back-to-list flow, and action sizing.
- Improved `PipelineEditorPage` top-level toolbar wrapping, mobile side panel behavior, and assistant/operator wording.
- Improved `/studio` overview copy, card/menu/run dialog targets, and mobile Studio nav spacing.
- Improved access settings pages with larger action targets and accessible icon labels.
- Improved `/servers/hub` terminal workspace controls, server picker dialog, SFTP toggle, AI panel toggle, and mobile header spacing.
- Improved `SftpPanel` visible Russian labels and control sizes.
- Improved `LinuxUiPanel` shell labels, window controls, launcher, overview, and stable empty-array constants.

## Current Next Focus

1. Deeper `LinuxUiPanel` pass inside Services, Processes, Logs, Disk, Network, Docker, and Packages windows.
2. Mobile terminal readability, especially aggressive xterm wrapping on narrow screens.
3. Pipeline editor node config panel control sizing.
4. Run monitor panel action sizing and risky-execution confirmation treatment.
5. Reduce large frontend files by extracting domain API callers and controller hooks without redesign.

## Guardrails

- Do not add a new UI framework.
- Use existing Radix/local shadcn-style components and lucide icons.
- Keep cards for repeated items and modals; avoid nested card-heavy layouts.
- Keep touch targets near 40-44px where practical.
- Use `aria-label` for icon-only controls.
- Keep backend behavior unchanged during UI-only passes.
- Do not stage or commit unless explicitly asked.
