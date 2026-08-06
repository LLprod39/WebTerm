# Agent execution scaling plan

Status: implemented for the next release candidate; production evidence is
required before increasing the supported pilot envelope.

## Goal

Allow many users to launch independent mini, full and multi-agent runs without
the single `ops-supervisor` worker serializing every run.

## Implemented topology

- A dedicated `agent-execution` service replaces the supervisor-owned single
  execution worker in Compose and Render deployments.
- Compose starts five replicas. Each process may execute two dispatches at the
  same time, providing ten worker slots by default.
- Every replica uses its hostname as a unique worker key and publishes an
  independent database heartbeat.
- PostgreSQL owns the authoritative cluster-wide and per-user capacity limits.
  A named control row makes each capacity decision atomic across processes.
- Fair selection prioritizes queued users with fewer active dispatches before
  giving another slot to a user who is already consuming capacity.
- Dispatch leases, heartbeats, retry limits and attempt fencing remain the
  recovery boundary when a worker exits.
- Launch admission is serialized separately so concurrent HTTP requests cannot
  race past the active-run limits or start the same agent twice.

## Default capacity

| Setting | Default | Purpose |
|---|---:|---|
| `AGENT_EXECUTION_REPLICAS` | 5 | Worker processes in production Compose |
| `AGENT_EXECUTION_WORKER_CONCURRENCY` | 2 | Concurrent runs inside one worker |
| `AGENT_EXECUTION_GLOBAL_CONCURRENCY` | 10 | Hard database cap across the pool |
| `AGENT_EXECUTION_PER_USER_CONCURRENCY` | 2 | Fair-share cap per user |
| `AGENT_ACTIVE_RUNS_PER_USER_LIMIT` | 5 | Running plus durable queued admission limit |
| `AGENT_ACTIVE_RUNS_GLOBAL_LIMIT` | 25 | Global running plus queued admission limit |

These defaults target a five-user pilot where each user can have two agents
executing concurrently. Additional accepted runs remain durable until a slot is
available. A zero-wait guarantee is intentionally not claimed because external
LLM quotas, host resources and burst size are finite.

## Release gates

1. Migration drift and the complete PostgreSQL backend suite are green.
2. Concurrent claim tests prove global and per-user limits across DB
   connections, without duplicate dispatch ownership.
3. Production Compose resolves the requested replica count and the installer
   observes every agent worker heartbeat.
4. A production-like load run covers at least five users and two distinct
   agents per user, recording queue age, completion latency, provider throttles,
   CPU and memory.
5. Scale to 10, 20 and 30 users only after the preceding cohort remains within
   the declared latency and error budgets.
