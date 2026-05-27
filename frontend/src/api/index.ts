/**
 * src/api/index.ts — canonical import location for all API functions.
 *
 * Migration status (T-017):
 *   The implementation is still in src/lib/api.ts (4133 lines).
 *   This file re-exports everything so pages can switch their imports
 *   from `../lib/api` to `../api` without any breaking changes.
 *
 *   Target structure (migrate function groups one PR at a time):
 *     api/auth.ts        — fetchAuthSession, login, logout, csrf, wsToken
 *     api/servers.ts     — server CRUD, files, linux UI, memory, knowledge
 *     api/agents.ts      — agent CRUD, runs, events, reply, approve
 *     api/studio.ts      — pipelines, runs, MCP, skills, triggers, templates
 *     api/settings.ts    — models, settings, activity
 *     api/monitoring.ts  — health, alerts, watchers
 *     api/types.ts       — all exported TypeScript interfaces / types
 *
 * Rule: NEVER import from src/lib/api directly in new code.
 *       Always use: import { ... } from "@/api"
 */
export * from "@/lib/api";
