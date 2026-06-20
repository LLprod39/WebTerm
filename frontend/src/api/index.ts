/**
 * src/api/index.ts — canonical import location for all API functions.
 *
 * Migration status (T-017):
 *   Most new domain work should live in src/api/<domain>.ts.
 *   src/lib/api.ts is now a compatibility facade plus shared transport/demo
 *   helpers, and remains available for old imports while callers migrate.
 *
 *   Target structure (migrate function groups one PR at a time):
 *     api/auth.ts        — fetchAuthSession, login, logout, wsToken
 *     api/servers.ts     — server CRUD, shares, groups, bootstrap
 *     api/agents.ts      — agent CRUD, runs, events, reply, approve
 *     api/studio.ts      — pipelines, runs, MCP, skills, triggers, templates
 *     api/studio-types.ts — Studio API DTOs and public contracts
 *     api/settings.ts    — models, settings, activity
 *     api/monitoring.ts  — health, alerts, watchers
 *     api/types.ts       — all exported TypeScript interfaces / types
 *
 * Rule: NEVER import from src/lib/api directly in new code.
 *       Always use: import { ... } from "@/api"
 */
export * from "@/lib/api";
