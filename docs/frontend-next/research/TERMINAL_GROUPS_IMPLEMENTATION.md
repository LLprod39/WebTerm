# Terminal AI and server group workflows

Implemented from current backend contracts on 2026-09-02. No previous frontend or Git history was read.

## Terminal assistant

`api/terminal-ai.ts`, `terminal-ai-state.ts`, `TerminalAssistant.tsx`, and `terminal-assistant.css` attach to the existing SSH WebSocket through subscription callbacks. Root owns `TerminalPage.tsx` integration; the assistant creates no additional SSH connection.

The UI covers request modes, mandatory command confirmation by default, exact command IDs for confirm/skip, stop, adaptive command plans, questions and explicit approval option values, progress, selected-output explanation, report generation/download, persistent memory clearing, extra targets, sudo policy, dry run and blocklist settings. Runtime model selection remains in user settings. Internal agent thinking is not rendered. Command output is shown only when actually supplied by the backend.

The event reducer buffers rapid updates, bounds retained history, rejects old tagged run events after a new request, deduplicates mirrored final replies and clears pending approval controls on disconnection. Backend restored memory count is displayed as context availability; it is not fabricated into visible chat history.

Contract tests: 4 terminal tests plus 6 automation tests passed. Global TypeScript passed at the integration checkpoint; the final scoped ESLint passed without warnings.

## Server groups

`ServerGroups.tsx` now opens a persistent URL-addressed group drawer. It provides actual membership rows with exact-login/email add and role update, protected owner identity and confirmed revoke; group rules and forbidden commands; environment variable fields with hidden values and unsaved-change protection; selected owned-server move/tags/activity updates; and durable group bulk operations with project-role/automation checks, reviewed confirmation, progress polling and resumable links.

Bulk group API supports only `set_active`, `set_ai_read_only`, `set_tags`. The UI sends typed values and explains that active state changes metadata rather than powering off a machine. Targets are snapshotted by the backend in the active project. Polling uses returned operation ID and stops on completed/failed status. There is no invented cancellation or operation-list API. Favorite/follow actions acknowledge a successful subscription without presenting an unsupported unsubscribe toggle.

Selected-server updates filter to bootstrap `can_edit` (owned servers) and submit only selected IDs plus the chosen field. Group context read is available to actual members; environment values and writes are restricted to owner/admin. Group management uses returned `can_edit` and role. Bulk creation additionally requires current project owner/admin/operator, and disabling AI read-only requires automation.

## Minimal compatible backend addition

Existing group mutations provided `add-member` and `remove-member`, but no JSON endpoint could list members or return IDs required for revoke. The bootstrap only exposes the current user's group role. A scoped read endpoint was therefore necessary for a usable access editor and explicitly approved by the parent task.

Added `GET /servers/api/groups/{id}/members/` in `servers/views/server_groups.py` and one route in `servers/urls.py`. It applies login, `servers` feature and the same `_get_group_role` owner/admin check as existing membership mutations. ServerGroup membership itself is group scoped, not project scoped; no new cross-project or staff bypass was introduced. All existing mutation behavior remains unchanged.

Response: `{group_id, owner:{user_id,username,email}, members:[{user_id,username,email,role,joined_at}]}`. Owner is returned separately so legacy groups without an owner membership remain correctly represented. Only persisted membership rows appear in `members`; the endpoint creates no rows.

`tests/test_server_group_members_api.py`: **5 passed**, covering owner/admin allowed shape and read-only behavior, viewer denied, unrelated group owner denied, anonymous denied and explicit feature denial. Ruff passed on the two modified backend files and the new test. A pre-existing pytest event-loop-fixture deprecation warning remains.

Backend unit checks use isolated SQLite test settings. Production data and external providers were not touched. The later live QA browser run is described below.

## Authored live QA tests

`frontend/tests/e2e/server-groups.spec.ts` has two real-backend scenarios restricted to port 8091: create group/add exact viewer/check persisted membership/revoke/reload; and an isolated group with one dedicated loopback fixture server, queue a metadata-only tag replacement, verify the target count and durable operation link after reload. The latter accepts queued/running/completed states and only asserts the actual server tag update when completed; it does not claim worker completion from a queue acknowledgment. All created groups and server rows use unique `qa_groups_*` names and are cleaned up. No command execution or external provider action is requested by these tests.

Both group scenarios **passed** in the combined six-test QA run on 2026-09-02 (56.6 seconds total). The first execution caught a real React sibling-key collision that duplicated tab content; each group panel now has a distinct stable key, and the full add/list/revoke/reload scenario passed after the correction. HTML evidence is at `frontend/playwright-report-automation/index.html`. Group bulk evidence establishes durable queueing and restoration; it does not establish the availability of a persistent bulk worker.
