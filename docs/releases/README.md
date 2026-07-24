# Releases

WebTerm has not yet published a production-ready release. The first target is a controlled internal pilot, not an unrestricted public or enterprise deployment.

Authoritative release documents:

- [Support matrix](SUPPORT_MATRIX.md) — supported runtimes, deployment shapes and explicit exclusions.
- [v0.1 release scope](V0_1_RELEASE_SCOPE.md) — capability status, prerequisites and required evidence.
- [v0.1 release checklist](V0_1_RELEASE_CHECKLIST.md) — exact gates and expected artifacts.
- [CI and Git governance](../architecture/CI_GOVERNANCE.md) — check rollout, promotion and branch-protection policy.

A green local command is not a release. A release candidate requires a clean commit, pinned tools, all mandatory artifacts, an explicit reviewer decision and a traceable CI run. `scripts/collect_release_evidence.py` records those inputs but deliberately never approves a release itself.
