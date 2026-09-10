# Intelligence and Kubernetes — scoped backend-to-UI audit

Audit scope: current Django backend and the new frontend only. Historical frontend and Git history were not used. Endpoint and permission details are in `INTELLIGENCE_CONTRACTS.md` and `KUBERNETES_CONTRACTS.md`. This is a workflow inventory, not a claim that every overlapping backend read endpoint has a separate screen.

## Intelligence

| Backend capability | New frontend workflow | Acceptance boundary |
|---|---|---|
| ServerAgent CRUD, templates, execution, reports, events, artifacts, plan and human feedback | Agents inventory/editor and run page; questions, approval, pause/resume/stop, plan task edit/refine | Actual agent execution needs reachable selected servers and configured AI workers/providers |
| Six schedule modes, due dispatch, stale-run cleanup | Editor calendar/timezone fields and runtime drawer with explicit dispatch/cleanup | Dispatch only targets due agents; actual worker scheduling needs running workers |
| Agent sudo/connection scope, input documents/scripts/task lists, report delivery | Editor runtime settings and structured materials/task editor | Uploading a script does not execute it; Telegram delivery requires configured credentials/chat access |
| Separate Studio AgentConfig entity | `/intelligence/profiles`, CRUD, instructions, tools, skills, MCP/server assignments | Profile is consumed by pipeline execution owned by the automation area |
| MCP CRUD, catalog, connectivity test, tool inventory and sharing | MCP configuration drawer and explicit test/inspection | A configured reachable stdio/SSE server is needed to certify tool invocation |
| MCP/profile global sharing and personal assignments | Explicit unchanged/enable/disable global setting plus user selection | Derived serializer `is_shared` is never silently round-tripped into global sharing |
| Operator Chat persisted history, WS streaming, tools, approval, artifacts, rename | Chat workspace with exact server selection, action review, history/reconnect and artifact editing | Live model streaming/tool execution needs configured runtime; no synthetic response fallback |
| Duty enable/disable and briefing | Explicit duty drawer/settings and brief request | Backend brief generation may invoke configured AI services |
| Server memory list/search/edit/delete, archive/promotion, selected bulk deletion | Server-scoped knowledge page, snapshot actions, named-server bulk confirmation | Search and consolidation may depend on enabled retrieval/storage/AI workers |
| Memory overview/dream execution/policy/purge | Staff controls with returned statistics and operation errors | Policy is per user; deletion of the last active snapshot also removes derived memory |
| MARS interview, plan, approval, run/test/review/events/stop | Sessions and runs with editable interview/plan and evidence | End-to-end acceptance requires the configured MARS CLI/workspace/toolchain |

Purpose/provider routing and CLI connection administration belong to the settings area maintained by the governance agent. Operational pages preserve the central policy rather than adding independent provider controls.

## Kubernetes

| Backend capability | New frontend workflow | Acceptance boundary |
|---|---|---|
| Provider configuration/probe/sync/delete; readiness and capabilities | Staff providers and readiness pages | A stored provider row is not evidence of connectivity; probe/sync failures remain visible |
| Cluster/namespace/workload/pod/network inventory and relationships | Cluster drill-down and resource detail with events and snapshot logs | Inventory freshness and provider sync state are shown |
| Helm ownership; Fleet bundles; Devtron apps/history/values metadata | Delivery inventory and detail, workload/pod/event links, conflict/ownership evidence | Helm values remain redacted/digest-based as provided by backend |
| Fleet/GitOps/Devtron external changes | All applicable action-request target forms, preview, approval and verification | These requests do not fabricate direct external execution; external evidence is recorded explicitly |
| Read/write/break-glass session lifecycle and post-review | Scoped access request, independent staff approval, close/revoke/review | Real acceptance needs two principals and actual granted Kubernetes permissions |
| Live discovery and generic resources | Session-bound explorer, filters, pagination, detail, JSON manifest, events, Secret reveal; live describe tab with identity, conditions, metadata, owners, ports, related Pods/ReplicaSets and partial-availability reasons | CRDs and Nodes are available through discovered kinds; dedicated snapshot endpoint variants are not separate screens |
| Resource logs, watch and metrics | Snapshot and bounded WS logs, resource watch, CPU/memory snapshot drawer | A live provider, metrics.k8s.io and allowed API verbs are required |
| Schema validation, dry-run, apply, patch, scale, restart, delete | Mutation editor with invalidated proof on edits, target/reason review and exact deletion phrase | Successful fixture response cannot certify native cluster mutation or proof freshness against a real provider |
| Cluster terminal, node debug and pod exec | Explicitly reviewed xterm sessions, capability/transport guards | Approved break-glass, provider stream support and runtime flags required; no automatic reconnect/re-execution |
| Pod/Service port-forward | Reviewed browser tunnel with HTTP GET helper, UTF-8/Base64 send and response view | Browser transport does not expose a local OS TCP listener; output view is bounded UTF-8 text |
| Cordon/uncordon/drain and restricted context | Emergency tools, exact drain confirmation and returned RBAC/context review | Native drain has an additional runtime gate; blocked bridge responses are not presented as execution |
| Separate action-request queue with all nine action types | `/requests` and detail, preview/rollback, peer approval, native execute under access policy, verification/report export | Native apply requires the approved JSON manifest/proof; external actions retain external verification semantics |
| Admin action reports, review and recordings | Activity page, report/recording inspection and export | Availability, retention and redaction reflect backend policy; absent transcript is not an empty successful run |
| Diagnose and external fallback audit | Explicit Devtron diagnosis into a Studio draft; staff external link after audit | Diagnosis creates a draft only; user follows the external link explicitly |

### Overlapping read surfaces without dedicated screens

`resources/describe/` is exposed in the resource-detail tab «Описание и связи». It fetches live enrichment only when opened, within the active session, and distinguishes unavailable related resources from a successful empty result. Specialized Nodes/CRDs and rollout overview/release/diagnostic/action-summary read aggregations are represented through generic discovery and normalized resource/delivery evidence, rather than one screen per endpoint. These overlapping read endpoints do not need duplicate navigation screens.

## Verification recorded for this area

- Scoped ESLint passed after all transport, action-request, material and sharing additions.
- TypeScript reported no errors in this area. The last whole-project check was blocked only by a Storybook tab-item property; the parent owns its correction and the final whole-project gate.
- Seven focused Vitest checks passed earlier: four action-review guards and three dry-run/mutation guards.
- Three Chromium Playwright contract-fixture scenarios passed with real isolated QA authentication: inventory drill-down, proof invalidation plus separate apply confirmation, and session peer approval.
- A fourth action-request scenario was added for the parent's final suite: own-request approval blocked, peer approval required, native execution hidden by access policy, and explicit external verification.
- Test fixtures intercept Kubernetes endpoints only inside tests. They are not product data or production runtime certification. Tests did not mutate the user's main frontend8090 database.

## External runtime acceptance still required

1. Reachable Rancher/Kubernetes with real credentials, an allowed namespace and representative workload/Pod/Service; metrics API for CPU/memory.
2. Two authorized accounts to exercise actual peer approval, approved write/break-glass scopes, revocation and expiry at the provider boundary.
3. Enabled and configured native mutation, terminal, node-debug, pod-exec, port-forward and drain transports; verify real operation result, audit entry and recording/redaction/retention behavior.
4. Reachable Fleet/Devtron and GitOps environment for external action handoff and verification evidence; Helm ownership/conflict fixtures are not production ownership evidence.
5. Configured AI/CLI providers, MCP processes/services, selected server access and agent/MARS workers for live streaming, tool use, run completion and stop/recovery.
6. Configured Telegram delivery and retrieval/consolidation infrastructure for their respective acceptance checks.

No unavailable dependency is replaced by invented successful data. The final release decision must distinguish frontend contract coverage from these real provider acceptance gates.
