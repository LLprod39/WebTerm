# Releases

WebTerm v0.2.3 is the current local controlled-pilot candidate built on the
v0.2.2 recovery and runtime-hardening release. It is not tagged, published or
approved for pilot use yet. Promotion still requires one exact SHA to pass all
mandatory CI, Linux delivery, real Codex/Grok, recovery, notification and load
gates. Release artifacts use immutable container digests, signed attestations,
SBOMs and checksums. The support matrix and explicit capability exclusions
remain authoritative.

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
- [v0.2.1 release notes](V0_2_1_RELEASE_NOTES.md) — security and isolation hardening release notes.
- [v0.2.2 release notes](V0_2_2_RELEASE_NOTES.md) — install, recovery and verification notes for the current published release.
- [v0.2.3 candidate release notes](V0_2_3_RELEASE_NOTES.md) — controlled Linux pilot scope and remaining promotion evidence.
- [v0.2.3 Linux pilot runbook](../pilot/V0_2_3_LINUX_PILOT_RUNBOOK.md) — fail-closed install, observability, encrypted backup and emergency-cleanup procedure.

A green local command is not a release. A release candidate requires a clean commit, pinned tools, all mandatory artifacts, an explicit reviewer decision and a traceable CI run. `scripts/collect_release_evidence.py` records those inputs but deliberately never approves a release itself.
