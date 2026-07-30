# Releases

WebTerm v0.2.1 is the security, isolation and operations hardening release built on the v0.1.0 Stage 1 foundation. Release artifacts use immutable container digests, signed attestations, SBOMs, checksums, install bundles, and automated runtime/Playwright proof on the published images. The support matrix and explicit capability exclusions remain authoritative.

Authoritative release documents:

- [Support matrix](SUPPORT_MATRIX.md) — supported runtimes, deployment shapes and explicit exclusions.
- [v0.1 release scope](V0_1_RELEASE_SCOPE.md) — capability status, prerequisites and required evidence.
- [v0.1 release checklist](V0_1_RELEASE_CHECKLIST.md) — exact gates and expected artifacts.
- [v0.1 performance budget](V0_1_PERFORMANCE_BUDGET.md) — Lighthouse and interaction-latency thresholds with CI evidence rules.
- [v0.2 release scope](V0_2_RELEASE_SCOPE.md) — current capability boundary after security and tenancy hardening.
- [v0.2 release checklist](V0_2_RELEASE_CHECKLIST.md) — mandatory promotion and publication gates.
- [Public API v0.1](PUBLIC_API_V0_1.md) — the explicitly declared stable HTTP route surface.
- [Brand compatibility](BRAND_COMPATIBILITY.md) — canonical WebTerm display identity and frozen legacy IDs.
- [Operations runbook](OPERATIONS_RUNBOOK.md) — install, upgrade, rollback, backup, restore and disaster recovery procedure.
- [First-release lifecycle policy](FIRST_RELEASE_LIFECYCLE_POLICY.md) — frozen fixtures and the separate application-rollback/database-restore rules.
- [Pilot UX script](../pilot/PILOT_UX_SCRIPT_V1.md) — versioned participant task and evidence rules.
- [CI and Git governance](../architecture/CI_GOVERNANCE.md) — check rollout, promotion and branch-protection policy.
- [v0.1.0 release notes](V0_1_0_RELEASE_NOTES.md) — install and verification commands for the published release.
- [v0.2.1 release notes](V0_2_1_RELEASE_NOTES.md) — upgrade, scope and verification notes for the current release.

A green local command is not a release. A release candidate requires a clean commit, pinned tools, all mandatory artifacts, an explicit reviewer decision and a traceable CI run. `scripts/collect_release_evidence.py` records those inputs but deliberately never approves a release itself.
