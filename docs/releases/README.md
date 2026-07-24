# Releases

WebTerm has not yet published a production-ready release. The first target is a controlled internal pilot, not an unrestricted public or enterprise deployment.

Authoritative release documents:

- [Support matrix](SUPPORT_MATRIX.md) — supported runtimes, deployment shapes and explicit exclusions.
- [v0.1 release scope](V0_1_RELEASE_SCOPE.md) — capability status, prerequisites and required evidence.
- [v0.1 release checklist](V0_1_RELEASE_CHECKLIST.md) — exact gates and expected artifacts.
- [Public API v0.1](PUBLIC_API_V0_1.md) — the explicitly declared stable HTTP route surface.
- [Brand compatibility](BRAND_COMPATIBILITY.md) — canonical WebTerm display identity and frozen legacy IDs.
- [Operations runbook](OPERATIONS_RUNBOOK.md) — install, upgrade, rollback, backup, restore and disaster recovery procedure.
- [Pilot UX script](../pilot/PILOT_UX_SCRIPT_V1.md) — versioned participant task and evidence rules.
- [CI and Git governance](../architecture/CI_GOVERNANCE.md) — check rollout, promotion and branch-protection policy.

A green local command is not a release. A release candidate requires a clean commit, pinned tools, all mandatory artifacts, an explicit reviewer decision and a traceable CI run. `scripts/collect_release_evidence.py` records those inputs but deliberately never approves a release itself.
