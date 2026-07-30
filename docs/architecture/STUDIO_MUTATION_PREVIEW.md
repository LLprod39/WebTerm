# Studio mutation preview contract

Every built-in Studio node which can change server or WebTerm state supports a
`dry_run` input and returns a `change_preview` object. This applies to direct
SSH commands and to file, package, disk, service, Docker, process, and alert
actions.

`change_preview` uses schema `webterm.change-preview.v1` and contains the
operation, bounded/redacted target, before and planned/after state, a unified
diff, and the `dry_run` marker. Secret-like values are redacted before the
preview enters pipeline output.

When `dry_run=true`, mutating calls are skipped. Read-only inspection needed to
build a useful preview may still run. Disk cleanup uses its existing guarded
remote inspection command, but the destructive branch is disabled. A changing
SSH command does not open an SSH connection in preview mode.

The pipeline executor rejects a successful mutating node result which omits a
valid preview. Tests also require every `mutates_state` manifest to expose the
`dry_run` input and `change_preview` output, so newly added mutation nodes fail
CI until they implement the contract.
