# Architecture Decision Records

ADRs record decisions that change WebTerm's long-lived public or technical contract. Accepted ADRs are immutable; a later decision supersedes them with a new record.

| ADR | Status | Decision |
| --- | --- | --- |
| [0001](0001-primary-runtime-and-toolchain.md) | Accepted | Primary runtime, toolchain and Windows/WSL boundary |
| [0002](0002-public-version-reset.md) | Accepted | Reset the first public contract to version 0.1.0 |
| [0003](0003-kubernetes-ops-and-mars-boundary.md) | Accepted | Keep Kubernetes Ops and MARS as disabled optional bounded contexts until an extraction trigger is met |

New records use the next number and include context, decision, consequences and verification.
