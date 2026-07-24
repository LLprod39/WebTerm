from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command

from kubernetes_ops.services.release_handoff import (
    build_kubernetes_release_handoff,
    render_kubernetes_release_handoff_markdown,
)
from tests.kubernetes_ops_release_handoff_helpers import _blocked_evidence


def test_kubernetes_release_handoff_markdown_is_operator_readable(tmp_path):
    evidence_path = tmp_path / "release.json"
    evidence_path.write_text(json.dumps(_blocked_evidence()), encoding="utf-8")

    markdown = render_kubernetes_release_handoff_markdown(build_kubernetes_release_handoff(evidence_path=evidence_path))

    assert markdown.startswith("# Kubernetes Ops Production Handoff")
    assert "- Status: blocked" in markdown
    assert "- Can enable sidebar: no" in markdown
    assert "- release_scope:local" in markdown
    assert "## Completion Audit" in markdown
    assert "- Core backend complete: yes" in markdown
    assert "- Production evidence complete: no" in markdown
    assert "- Remaining: production_evidence, sidebar_enablement" in markdown
    assert "## Backend Workstream" in markdown
    assert "- Status: backend_ready_production_blocked" in markdown
    assert "- Backend complete: yes" in markdown
    assert "- Core backend proofs: 7/7 (100%)" in markdown
    assert "- Remaining backend gaps: 0" in markdown
    assert "- External blocker primary category: production_scope" in markdown
    assert "- Safe to continue frontend: yes" in markdown
    assert "- Next step: select_production_environment" in markdown
    assert "## Operator Command Plan" in markdown
    assert "- Recommended next: select_production_environment (manual)" in markdown
    assert "- Local demo smoke (`local_demo_smoke`)" in markdown
    assert "`local_demo_fixture`: `python .tools/k8s-provider-fixture.py --host 127.0.0.1 --port 18090`" in markdown
    assert "`local_demo_seed`: `python manage.py seed_kubernetes_ops_demo --username admin --admin-write`" in markdown
    assert "## Production Execution Plan" in markdown
    assert "- Recommended next: Select the production release environment." in markdown
    assert "### Blocked Until" in markdown
    assert "`local_indicators`: local/test markers must be removed from evidence (8)" in markdown
    assert "### Phases" in markdown
    assert "Collect production prerequisite evidence" in markdown
    assert (
        "command: `python manage.py verify_kubernetes_ops_external_evidence_bundle "
        "--output artifacts/kubernetes_ops_external_evidence_bundle.json`"
    ) in markdown
    assert "Generate release artifacts" in markdown
    assert (
        "command: `python manage.py verify_kubernetes_ops_release --username <staff-user> "
        "--output artifacts/kubernetes_ops_release_evidence.json`"
    ) in markdown
    assert "## Release Proofs" in markdown
    assert (
        "`post_review_retention`: ready - pending_review=True, deleted_events=1, post_review_redacted=True" in markdown
    )
    assert "`external_evidence_bundle`: ready - refs_missing=0, artifacts=6/6, local_indicators=0" in markdown
    assert (
        "`production_action_evidence`: ready - rollback_actions=5, native_checks=10, blocked_actions=11, blocked_contract=True"
        in markdown
    )
    assert (
        "`interactive_transport_evidence`: ready - enabled=0, blockers=0, dangerous_live_action_started=False"
        in markdown
    )
    assert (
        "`interactive_live_smoke`: ready - simulated_checks=4, live_contracts=4, required=False, production_live_provider_evidence=False"
        in markdown
    )
    assert (
        "`interactive_shell_streams`: ready - actions=2, recordings=2, events=4, provider_requests_safe=True"
        in markdown
    )
    assert "`definition_of_done`: ready - ready=13/13, missing=0, missing_ids=none" in markdown
    assert (
        "`normal_user_surface`: ready - reader_external_links_visible=False, credential_scan=ready, surfaces=16, "
        "secret_ref_serialized=False, forbidden_values=False"
    ) in markdown
    assert (
        "`action_controls`: ready - native_execution_enabled=False, approval_status=approved_external, rollback_plan=required, restart_template=ready, verification_plan=pending, auto_verification=verified, gitops=gitlab, git_write=False, cluster_mutation=False, restricted_write_gate=ready"
        in markdown
    )
    assert (
        "`secret_read_controls`: ready - default_redacted=True, list_metadata_only=True, denied_without_grant=True, denied_without_runtime_flag=True, allowed_all_gates=True"
        in markdown
    )
    assert (
        "`provider_secret_lifecycle`: ready - storage=managed, rotation_supported=True, plaintext_serialized=False, persistent_rows=False"
        in markdown
    )
    assert (
        "`audit_redaction`: ready - api_serializer_redacted=True, cluster_event_redacted=True, credentialed_url_sanitized=True, persistent_rows=False"
        in markdown
    )
    assert (
        "`python manage.py verify_kubernetes_ops_release --username <staff-user> --output artifacts/kubernetes_ops_release_evidence.json`"
        in markdown
    )
    assert (
        "`python manage.py render_kubernetes_ops_release_handoff --output artifacts/kubernetes_ops_release_handoff.md`"
        in markdown
    )
    assert "`KUBERNETES_OPS_READY_FOR_SIDEBAR`" in markdown
    assert "`KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF`" in markdown
    assert "Provider-native interactive transports require recording gates" in markdown


def test_render_kubernetes_ops_release_handoff_command_outputs_summary(tmp_path):
    evidence_path = tmp_path / "release.json"
    output_path = tmp_path / "handoff.md"
    evidence_path.write_text(json.dumps(_blocked_evidence()), encoding="utf-8")
    stdout = StringIO()

    call_command(
        "render_kubernetes_ops_release_handoff",
        "--evidence",
        str(evidence_path),
        "--output",
        str(output_path),
        stdout=stdout,
    )

    assert output_path.exists()
    assert "# Kubernetes Ops Production Handoff" in output_path.read_text(encoding="utf-8")
    output = stdout.getvalue()
    assert "Wrote Kubernetes Ops release handoff:" in output
    assert "status=blocked" in output
    assert "can_enable_sidebar=False" in output
    assert "backend_workstream=backend_ready_production_blocked" in output
    assert "external_primary=production_scope" in output
