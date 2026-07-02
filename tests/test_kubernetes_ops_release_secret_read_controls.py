import pytest
from django.contrib.auth.models import User

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession
from kubernetes_ops.services.release_secret_read_controls import (
    build_kubernetes_release_secret_read_controls_evidence,
    secret_read_controls_blocker,
)


@pytest.mark.django_db
def test_kubernetes_release_secret_read_controls_are_ready_and_rolled_back():
    user = User.objects.create_user(username="release-secret-read-proof", password="x", is_staff=True)
    initial_actions = K8sAdminAction.objects.count()
    initial_sessions = K8sAdminSession.objects.count()

    proof = build_kubernetes_release_secret_read_controls_evidence(user, True)

    assert proof["status"] == "ready"
    assert proof["default_redacted"] is True
    assert proof["raw_secret_absent_from_default_response"] is True
    assert proof["raw_secret_absent_from_action_summary"] is True
    assert proof["secret_read_rejected_without_grant"] is True
    assert proof["secret_read_rejected_without_runtime_flag"] is True
    assert proof["provider_not_called_for_denied_reveal"] is True
    assert proof["secret_read_capability_disabled_by_default"] is True
    assert proof["secret_list_metadata_only"] is True
    assert proof["secret_list_raw_secret_absent"] is True
    assert proof["secret_list_action_summary_raw_secret_absent"] is True
    assert proof["secret_list_action_summary_flags_boolean"] is True
    assert proof["secret_read_allowed_with_all_gates"] is True
    assert proof["allowed_action_summary_raw_secret_absent"] is True
    assert proof["actions_created"] == 3
    assert proof["persistent_rows"] is False
    assert secret_read_controls_blocker(proof) is None
    assert "postgres://release-secret" not in str(proof)
    assert "cmVsZWFzZS1wYXNzd29yZA==" not in str(proof)
    assert K8sAdminAction.objects.count() == initial_actions
    assert K8sAdminSession.objects.count() == initial_sessions


def test_kubernetes_release_secret_read_controls_blocker_names_failed_gate():
    blocker = secret_read_controls_blocker(
        {
            "success": True,
            "status": "ready",
            "default_redacted": True,
            "raw_secret_absent_from_default_response": False,
        }
    )

    assert blocker == "secret_read_controls:raw_secret_absent_from_default_response"
