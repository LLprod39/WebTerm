# Deferred UI scenarios

The user removed Overview, personal dashboard preferences, standalone Monitoring,
Kubernetes, and Team activity from the current product scope on 2026-09-02.
These historical scenarios are kept outside Playwright's active tests/e2e
directory with a .disabled suffix for a possible future return of those modules.
They are not release evidence, skipped tests, or proof that redirected URLs work.

The user also removed global search and excluded mobile UX on 2026-09-02.
Authentication, desktop shell navigation, project workflows, and backend
authorization checks remain in the active suite. New home
and legacy redirects must be verified as navigation behavior, not counted as
successful rendering of the removed modules.

Before restoring a historical scenario, update its imports and UI assertions for
the implemented module. Do not add this directory to the active test directory
merely to increase coverage counts.
