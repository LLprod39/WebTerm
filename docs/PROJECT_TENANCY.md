# Project tenancy

WebTerm uses a project as the tenant boundary for servers, server agents, playbooks, and Studio resources. A user may belong to several projects, but exactly one non-archived project is active at a time.

## Compatibility migration

- Every existing user receives one default personal project.
- Existing servers, agents, playbooks, MCP servers, Studio agents, pipelines, and owned skill metadata move into their owner's default project.
- Existing explicit server and Studio shares add the recipient as a member of the resource's project.
- A share-only user with an empty personal project is switched to their first shared team project, preserving legacy share links; users who already own resources keep their current project.
- Existing agent-to-server links that cross project boundaries are removed during migration; a single executable agent cannot span tenants.
- New owned resources inherit the owner's active project automatically, so existing API clients do not need to send a project identifier.

The migrations are `core_ui.0022_projects`, `servers.0052_project_tenant_boundary`, and `studio.0015_project_tenant_boundary`.

## Roles

| Role | Project membership | Manage members | Create resources |
|---|---:|---:|---:|
| owner | yes | yes | yes |
| admin | yes | yes | yes |
| operator | yes | no | yes |
| viewer | yes | no | no |

Object-level grants remain narrower than project membership. For example, joining a project does not by itself grant terminal execution on every server; `ServerShare` capabilities still apply. Creating a legacy server or Studio share enrolls that explicitly selected user in the resource's project so existing clients keep working.

## API

- `GET /api/projects/` — list memberships and the active project.
- `POST /api/projects/` — create a project and optionally activate it.
- `POST /api/projects/{project_id}/activate/` — select a project.
- `GET|POST /api/projects/{project_id}/members/` — list or invite members.
- `PATCH|DELETE /api/projects/{project_id}/members/{user_id}/` — change a role or remove a member.

`GET /api/auth/session/` also returns `active_project` and `project_count`, allowing the frontend to render a project switcher without a second blocking request.

## Isolation invariants

- Canonical server, playbook, Studio configuration, Studio run, and agent-run queries include the active project.
- Staff status does not silently bypass the selected project boundary.
- An agent cannot attach a server or MCP configuration from another project.
- Sharing selectors accept only users who are members of the resource's project.
- Switching projects changes visibility; resource identifiers from another project resolve as not found.

Background workers keep processing the project attached to the queued resource. Project selection only controls user-facing access and new resource placement; it does not mutate already queued work.
