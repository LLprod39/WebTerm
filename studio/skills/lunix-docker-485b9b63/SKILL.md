---
name: lunix Docker Ops
description: Автосгенерированный operational skill на основе повторяющегося паттерна `echo '===== DISK SPACE ====='; df -h; echo; echo '===== RUNNING CONTAINERS ====='; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Sta…` для сервера lunix.
service: lunix
category: docker
safety_level: standard
ui_hint: server_ops
guardrail_summary: ["Resolve the target server before mutation.","Run verification after every change.","Do not expose secrets from command output."]
recommended_tools: ["read_console","ssh_execute","report"]
tags: ["auto-generated","server-memory","docker"]
---
# lunix Docker Ops

Use this skill for work done through MCP tools against lunix.

## When to use

- The user asks for operational work that touches lunix.
- The request is free-form, ambiguous, or safety-sensitive.
- The environment, tenant, realm, project, or profile must be resolved before mutation.

## Mandatory workflow

1. Start with environment and permission discovery using the correct read-only MCP tools.
2. Normalize the user request into a short structured plan before making changes.
3. Resolve exact targets with read-only discovery tools before any mutation.
4. Execute only the minimum required mutations.
5. Run read-only verification after every mutation and compare the final state with the request.
6. Stop and ask the user whenever discovery is incomplete or the target is ambiguous.

## Hard rules

- Always prefer exact identifiers over fuzzy matching.
- Never mutate if discovery data is incomplete.
- Never switch context mid-run unless the user explicitly asks and confirms it.
- Always pass required environment arguments explicitly when the MCP tool supports them.
- If this skill defines runtime policy, treat it as mandatory and assume those guardrails are enforced by the platform.
- If this skill works with service-specific MCP tools, use the original tool names in the policy, for example `lunix_current_environment`.

## Reportinрg

- State which environment, tenant, realm, profile, or project was used.
- State which entities were discovered before mutation.
- State which mutations were applied and which were skipped.
- State which verification calls were used.
- State any ambiguity, blockers, or follow-up required.

## Derived Draft

- # Skill Draft: docker
- Trigger: задачи, где нужен шаг `echo '===== DISK SPACE ====='; df -h; echo; echo '===== RUNNING CONTAINERS ====='; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Sta…`.
- Reuse signal: 4 повторений, успех 100%.
- Primary command: echo '===== DISK SPACE ====='; df -h; echo; echo '===== RUNNING CONTAINERS ====='; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Sta…
- Verification: проверить состояние контейнеров через `docker ps` и при необходимости `docker stats --no-stream`.
- Hints: вернуть короткую operational-выжимку и рекомендации по следующему действию.

## Derived Workflow

1. `echo '===== DISK SPACE ====='; df -h; echo; echo '===== RUNNING CONTAINERS ====='; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Sta…`

## Source Signal

- Server: lunix (172.25.173.251)
- Memory key: skill_draft:485b9b637aa7555f
- Display command: echo '===== DISK SPACE ====='; df -h; echo; echo '===== RUNNING CONTAINERS ====='; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Sta…
- Intent: docker
