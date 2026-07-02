# Kubernetes Ops Production Handoff

- Status: blocked
- Can enable sidebar: no
- Evidence: /workspace/artifacts/kubernetes_ops_release_evidence.json
- Evidence generated at: 2026-07-02T14:35:16.150469+00:00
- Release scope: local (production target environment is not selected)
- Missing production refs: 0

## Current Blockers
- readiness:sidebar_release_scope=missing
- release_scope:local

## Completion Audit
- Core backend complete: yes
- Runtime readiness complete: yes
- Production evidence complete: no
- Sidebar enablement complete: no
- Remaining: production_evidence, sidebar_enablement

## Release Proofs
- `action_controls`: ready - native_execution_enabled=False, approval_status=approved_external, rollback_plan=required, restart_template=ready, verification_plan=pending, auto_verification=verified, gitops=gitlab, git_write=False, cluster_mutation=False, restricted_write_gate=ready
- `admin_mode_safety`: ready - provider_called=False, admin_actions_created=0
- `post_review_retention`: ready - pending_review=True, deleted_events=1, post_review_redacted=True
- `external_evidence_bundle`: ready - refs_missing=0, artifacts=6/6, local_indicators=18
- `production_action_evidence`: ready - rollback_actions=5, native_checks=10, blocked_actions=11, blocked_contract=True
- `interactive_transport_evidence`: ready - enabled=0, blockers=0, dangerous_live_action_started=False
- `interactive_live_smoke`: ready - simulated_checks=4, live_contracts=4, required=False, production_live_provider_evidence=False
- `interactive_shell_streams`: ready - actions=2, recordings=2, events=4, provider_requests_safe=True
- `definition_of_done`: ready - ready=13/13, missing=0, missing_ids=none
- `normal_user_surface`: ready - reader_external_links_visible=False, credential_scan=ready, surfaces=31, secret_ref_serialized=False, forbidden_values=False
- `secret_read_controls`: ready - default_redacted=True, list_metadata_only=True, denied_without_grant=True, denied_without_runtime_flag=True, allowed_all_gates=True
- `provider_secret_lifecycle`: ready - storage=managed, rotation_supported=True, plaintext_serialized=False, persistent_rows=False
- `audit_redaction`: ready - api_serializer_redacted=True, cluster_event_redacted=True, credentialed_url_sanitized=True, persistent_rows=False

## Next Steps
1. Run release evidence in production with non-local Rancher/Devtron/MCP endpoints, approval ref and core evidence refs.

## Production Execution Plan
- Status: blocked
- Recommended next: Select the production release environment.

### Blocked Until
- `target_environment`: target environment must be production
- `production_approval_ref`: production approval reference must be present
- `local_indicators`: local/test markers must be removed from evidence (8)
- `production_ready`: release evidence must report production_ready=true
- `ready_for_sidebar`: release evidence must report ready_for_sidebar=true
- `production_evidence_complete`: completion audit must mark production evidence complete
- `sidebar_enablement_complete`: completion audit must mark sidebar enablement complete

### Phases
- Configure production scope (`configure_production_scope`)
  - manual: Set KUBERNETES_OPS_RELEASE_ENVIRONMENT=production only for the real target.
  - manual: Set approval and evidence reference env vars; do not paste provider tokens.
- Collect production prerequisite evidence (`collect_production_evidence`)
  - command: `python manage.py verify_kubernetes_ops_live_provider_smoke --output artifacts/kubernetes_ops_live_provider_smoke.json`
  - command: `python scripts/verify_kubernetes_ops_readonly_rbac_live.py --apply`
  - command: `python manage.py verify_kubernetes_ops_interactive_transport_evidence --output artifacts/kubernetes_ops_interactive_transport_evidence.json`
  - command: `python manage.py verify_kubernetes_ops_interactive_live_smoke --output artifacts/kubernetes_ops_interactive_live_smoke.json`
  - command: `python manage.py verify_kubernetes_ops_interactive_production_controls --output artifacts/kubernetes_ops_interactive_production_controls.json`
  - command: `python manage.py verify_kubernetes_ops_production_action_evidence --output artifacts/kubernetes_ops_production_action_evidence.json`
  - command: `python manage.py verify_kubernetes_ops_external_evidence_bundle --output artifacts/kubernetes_ops_external_evidence_bundle.json`
- Generate release artifacts (`generate_release_artifacts`)
  - command: `python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json`
  - command: `python manage.py verify_kubernetes_ops_release --username <staff-user> --output artifacts/kubernetes_ops_release_evidence.json`
  - command: `python manage.py render_kubernetes_ops_release_handoff --output artifacts/kubernetes_ops_release_handoff.md`
- Enable sidebar after green handoff (`enable_sidebar_after_green`)
  - manual: Set KUBERNETES_OPS_READY_FOR_SIDEBAR=true only after production_ready=true and approved operator change.

## Required Commands
- `python manage.py check`
- `python scripts/check_architecture_sizes.py --strict-new`
- `python manage.py makemigrations kubernetes_ops --check --dry-run`
- `python -m pytest tests/test_kubernetes_ops_*.py`
- `python manage.py render_kubernetes_ops_readonly_rbac --validate-only`
- `python manage.py verify_kubernetes_ops_sync_prune_safety`
- `python scripts/verify_kubernetes_ops_readonly_rbac_live.py --apply`
- `python scripts/verify_kubernetes_ops_local_platform.py --output artifacts/kubernetes_ops_local_platform_evidence.json`
- `python manage.py verify_kubernetes_ops_live_provider_smoke --output artifacts/kubernetes_ops_live_provider_smoke.json`
- `python manage.py verify_kubernetes_ops_interactive_transport_evidence --output artifacts/kubernetes_ops_interactive_transport_evidence.json`
- `python manage.py verify_kubernetes_ops_interactive_live_smoke --output artifacts/kubernetes_ops_interactive_live_smoke.json`
- `python manage.py verify_kubernetes_ops_interactive_production_controls --output artifacts/kubernetes_ops_interactive_production_controls.json`
- `python manage.py verify_kubernetes_ops_production_action_evidence --output artifacts/kubernetes_ops_production_action_evidence.json`
- `python manage.py verify_kubernetes_ops_external_evidence_bundle --output artifacts/kubernetes_ops_external_evidence_bundle.json`
- `python manage.py verify_kubernetes_ops_release --username <staff-user> --output artifacts/kubernetes_ops_release_evidence.json`
- `python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json`
- `python manage.py render_kubernetes_ops_release_handoff --output artifacts/kubernetes_ops_release_handoff.md`

## Production Env Flags
- `KUBERNETES_OPS_RELEASE_ENVIRONMENT`: production
- `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF`: <change-or-approval-id>
- `KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF`: <operator-reviewed production evidence bundle ref>
- `KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF`: <production SSO/Keycloak runtime evidence ref>
- `KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF`: <production Rancher/Fleet/Devtron live provider evidence ref>
- `KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF`: <production read-only RBAC can-i evidence ref>
- `KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF`: <production Kubernetes MCP READ_ONLY smoke evidence ref>
- `KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF`: <production rollback drill evidence ref>
- `KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF`: <production native verification evidence ref>
- `KUBERNETES_OPS_READY_FOR_SIDEBAR`: true only after production_ready=true
- `KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS`: 86400 or stricter
- `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`: <reviewed restricted credential/RBAC proof before any production interactive transport>
- `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`: <reviewed network policy/egress proof before production port-forward tunnel>
- `KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF`: <reviewed production live-smoke proof before enabling production interactive streams>

## Missing Production Refs
- none

## External Evidence Required
- Non-local Rancher/Fleet/Devtron provider endpoints and successful live probes.
- Fresh successful provider sync dry-run and running sync worker.
- Live read-only Kubernetes RBAC can-i proof on the target cluster.
- External evidence bundle with reviewed production refs for approval, providers, RBAC, SSO, MCP, rollback, native verification and interactive gates.
- Production rollback drill evidence for restart/scale/apply/patch/delete request classes before sidebar enablement.
- Production native verification evidence proving post-action read-only checks close requests without weak or stale evidence.
- Fresh interactive transport prerequisite artifact proving recording, restricted credential and provider-contract gates.
- Fresh interactive live-smoke artifact proving provider opener contracts and external production live-stream evidence refs.
- Fresh interactive production controls artifact proving restricted credential, recording, provider-contract and port-forward network-policy contracts.
- Owned production Kubernetes MCP binding with READ_ONLY diagnosis smoke.
- Production SSO/Keycloak runtime gate and explicit approval reference.
- Reviewed restricted credential evidence before production exec, port-forward, cluster terminal, or node debug transport.
- Reviewed port-forward network policy evidence, exact target allowlist, protected namespace denylist, and short TTL before production port-forward tunnel.

## Safety Guards
- Native exec/attach/port-forward/apply/delete/scale/restart remain disabled.
- Provider-native interactive transports require recording gates plus restricted credential evidence in production.
- Provider-native port-forward additionally requires network policy evidence and an exact target allowlist in production.
- Provider secrets stay behind managed/external secret references.
- Release evidence must pass artifact safety self-scan before sidebar enablement.
