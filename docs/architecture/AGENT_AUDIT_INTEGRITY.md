# Agent Audit Integrity

Last reviewed: 2026-07-30

`AgentRunEvent` is the durable audit trail for agent execution. Events are append-only, retained indefinitely, and linked by a per-run SHA-256 chain. Each hash covers the immutable run reference, owner reference, sequence number, event data, UTC timestamp, and previous hash.

## Guarantees

- Application code cannot update or delete persisted audit events.
- Appends for one run are serialized by a database row lock and receive a unique sequence number.
- Deleting an agent or aged `AgentRun` does not delete its audit events. The live foreign key becomes null while `run_ref` and `owner_user_ref` remain.
- The normal history-pruning job never selects `AgentRunEvent`.
- Verification detects sequence gaps, reordered, relinked, or modified records.
- HTTP and management exports are refused when verification fails.

The chain is tamper-evident, not an external notarization system. A database administrator who can rewrite all rows and hashes can forge a new chain. For stronger non-repudiation, regularly export the JSONL manifest and store its final event hash and content hash in separate immutable storage.

## API and export

The owner-scoped event endpoint includes full-chain verification metadata:

```text
GET /servers/api/agents/runs/<run_id>/events/
```

A verified portable JSONL export is available at:

```text
GET /servers/api/agents/runs/<run_id>/audit-export/
```

The export contains a header, ordered event records, and a manifest with the event count, first/final event hashes, and SHA-256 of all preceding export lines.

Operators can also export by retained run reference:

```powershell
python manage.py export_agent_audit <run_ref> --output artifacts/agent-audit-<run_ref>.jsonl
```

The command exits with an error instead of exporting when the chain is invalid.

## Retention and recovery

Audit events have no automatic expiry or row-count ceiling. Capacity planning and external archival are operational responsibilities. If verification fails, preserve a database snapshot and the last trusted export, investigate privileged database access, and do not repair or re-hash the affected rows in place.
