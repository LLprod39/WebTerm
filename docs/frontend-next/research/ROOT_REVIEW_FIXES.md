# Focused review of infrastructure, terminal and session boundaries

Reviewed on 2026-09-02 from current backend and Frontend Next source. No old frontend or Git history used. Scope: only reproducible P1/P2 risks involving permissions, secrets, unintended execution, lost edits or API contracts.

## Changes

| Finding and trigger | Correction | Files |
| --- | --- | --- |
| P1: elevated file write interpolated the target inside `sh -c` without quoting the redirection operand. Valid filenames with spaces broke the write; shell metacharacters were interpreted as shell syntax under sudo. | Quote the path inside the inner shell, then quote the complete inner command for the outer shell. Endpoint, request schema and permission checks remain unchanged. | `servers/elevated_files.py` |
| P2: edit more text while a file save is pending. Both editors' success callbacks used the latest React closure, marking the newer unsent text as saved. Closing afterward lost those changes. | Pass an immutable submitted content snapshot to the mutation and acknowledge that exact snapshot. Late reads/writes in the file browser are applied only to the matching open path. | `frontend/src/features/infrastructure/TerminalFileEditor.tsx`, `ServerFiles.tsx` |
| P2: navigate away from an open editor, switch the server detail tab, or receive another intercepted editor command. The old component could unmount without warning. | Guard SPA navigation and page unload, confirm internal tab changes and replacement of dirty editors. Wait for pending file saves before normal editor close/replacement. Terminal navigation warns that sessions and unsaved files close; focus query changes stay in place. | `TerminalPage.tsx`, `TerminalFileEditor.tsx`, `ServerFiles.tsx`, `ServerDetailPage.tsx` |
| P2: terminal editor cached file content could be reused or refetched during an edit. | Keep each loaded read snapshot stable, abort reads on disposal, remove inactive file queries/mutations immediately. | `TerminalFileEditor.tsx` |
| P2: change form fields during a pending save in a form that closes on success. The response closed the form and discarded newer input. | Disable ServerForm and TerminalPreferences fieldsets while their submission is pending. | `ServerForm.tsx`, `TerminalPreferences.tsx` |
| P2: download a remote `.json` file. FileResponse serves it with `application/json` and attachment disposition; client treated every JSON response as an API error. | Accept successful JSON attachments, continue treating non-attachment JSON as API envelopes, emit session expiry for HTTP 401 downloads. | `frontend/src/api/client.ts` |

## Verification

- `tests/test_elevated_files.py`: command-capture regression covers a space, single quote, semicolon, `$()` substitution, backticks and newline in a valid path. Parses both shell layers with `shlex`; executes no shell, subprocess or remote command. All 12 tests pass in the native Python 3.12.2 / Django 6.0.7 environment.
- `frontend/tests/file-editor.test.tsx`: deferred remote writes prove that later textarea edits stay dirty in both editors, and that file-browser SPA navigation is blocked until explicit discard.
- `frontend/tests/api-client.test.ts`: JSON attachment download succeeds; unauthorized download emits session expiry. Existing CSRF/envelope/host-key boundary assertions retained.
- Focused ESLint over changed frontend modules passes. Final aggregate build and end-to-end suite are owned by the root task.

## Reviewed without changing

`SessionProvider`, auth endpoint adapters, ServerSecurity and server form payloads: no additional confirmed P1/P2 regression found. Secrets remain write-only in server forms and sudo requests use POST bodies. The new GET group-members endpoint uses the same owner/admin role gate as existing membership mutations, returns actual memberships and does not add a staff bypass. No changes to that endpoint were needed in this review.

## Backend ownership and runtime

The only backend source changed by this review is `servers/elevated_files.py`; the only backend test changed is `tests/test_elevated_files.py`. This is an existing helper correctness/security fix newly relevant to the frontend editor, not a new endpoint. Restart/reload both HTTP/ASGI processes that import this helper before relying on the corrected behavior. No migrations, settings or runtime database writes were performed by the regression test.
