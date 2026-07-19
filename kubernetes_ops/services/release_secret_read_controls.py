from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import (
    KUBERNETES_ADMIN_READ_FEATURE,
    KUBERNETES_FEATURE,
    KUBERNETES_SECRET_READ_FEATURE,
    kubernetes_permission_policy,
)
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    get_cluster_resource_yaml,
    list_cluster_resources,
)

RAW_SECRET_VALUES = (
    "cmVsZWFzZS1wYXNzd29yZA==",
    "cmVsZWFzZS1hcGk=",
    "postgres://release-secret",
    "raw-annotation-token",
)


def build_kubernetes_release_secret_read_controls_evidence(user, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "Secret-read controls proof skipped"}
    if not user or not getattr(user, "is_staff", False):
        return {"success": False, "status": "missing", "reason": "staff user is required for Secret-read controls proof"}
    try:
        with transaction.atomic():
            _grant(user, KUBERNETES_FEATURE, KUBERNETES_ADMIN_READ_FEATURE)
            suffix = uuid.uuid4().hex[:10]
            provider = K8sProvider.objects.create(
                name=f"release-secret-read-rancher-{suffix}",
                kind=K8sProvider.KIND_RANCHER,
                base_url="https://rancher.release-secret-read.example.test",
                auth_mode=K8sProvider.AUTH_NONE,
            )
            cluster = K8sCluster.objects.create(
                name=f"release-secret-read-{suffix}",
                environment="test",
                rancher_provider=provider,
                rancher_cluster_id=f"c-release-secret-read-{suffix}",
            )
            session = _read_session(user=user, cluster=cluster)
            initial_action_count = K8sAdminAction.objects.count()
            proof = _run_secret_read_checks(user=user, cluster=cluster, session=session, initial_action_count=initial_action_count)
            transaction.set_rollback(True)
            return proof
    except Exception as exc:
        return {"success": False, "status": "error", "error": str(exc)}


def secret_read_controls_blocker(proof: dict[str, Any]) -> str | None:
    if not proof.get("success"):
        return f"secret_read_controls:{proof.get('status') or 'failed'}"
    required_flags = (
        "default_redacted",
        "raw_secret_absent_from_default_response",
        "raw_secret_absent_from_action_summary",
        "secret_read_rejected_without_grant",
        "secret_read_rejected_without_runtime_flag",
        "provider_not_called_for_denied_reveal",
        "secret_read_capability_disabled_by_default",
        "secret_list_metadata_only",
        "secret_list_raw_secret_absent",
        "secret_list_action_summary_raw_secret_absent",
        "secret_list_action_summary_flags_boolean",
        "secret_read_allowed_with_all_gates",
        "allowed_action_summary_raw_secret_absent",
    )
    missing = next((flag for flag in required_flags if not proof.get(flag)), "")
    if missing:
        return f"secret_read_controls:{missing}"
    if proof.get("actions_created") != 3:
        return "secret_read_controls:action_count_invalid"
    return None


def _run_secret_read_checks(*, user, cluster: K8sCluster, session: K8sAdminSession, initial_action_count: int) -> dict[str, Any]:
    default_provider_calls = 0

    def default_transport(*_args, **_kwargs):
        nonlocal default_provider_calls
        default_provider_calls += 1
        return _secret_payload()

    with _temporary_settings(KUBERNETES_ADMIN_SECRET_READ_ENABLED=False):
        _set_feature(user, KUBERNETES_SECRET_READ_FEATURE, False)
        default_payload = get_cluster_resource_yaml(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            api_version="v1",
            kind="Secret",
            namespace="release-secret-read",
            name="db-creds",
            transport=default_transport,
        )
        default_action = K8sAdminAction.objects.order_by("-id").first()
        list_provider_calls = 0

        def list_transport(*_args, **_kwargs):
            nonlocal list_provider_calls
            list_provider_calls += 1
            return _secret_list_payload()

        list_payload = list_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            api_version="v1",
            kind="Secret",
            namespace="release-secret-read",
            include_secret_values=True,
            transport=list_transport,
        )
        list_action = K8sAdminAction.objects.order_by("-id").first()
        no_grant_denied = _expect_secret_read_denied(
            user=user,
            session=session,
            cluster=cluster,
            setting_enabled=True,
            expected_code="secret_read_required",
        )
        _set_feature(user, KUBERNETES_SECRET_READ_FEATURE, True)
        runtime_flag_denied = _expect_secret_read_denied(
            user=user,
            session=session,
            cluster=cluster,
            setting_enabled=False,
            expected_code="secret_read_required",
        )
        policy_with_flag_disabled = kubernetes_permission_policy(user)

    visible_provider_calls = 0

    def visible_transport(*_args, **_kwargs):
        nonlocal visible_provider_calls
        visible_provider_calls += 1
        return _secret_payload()

    with _temporary_settings(KUBERNETES_ADMIN_SECRET_READ_ENABLED=True):
        visible_payload = get_cluster_resource_yaml(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            api_version="v1",
            kind="Secret",
            namespace="release-secret-read",
            name="db-creds",
            include_secret_values=True,
            transport=visible_transport,
        )
        visible_action = K8sAdminAction.objects.order_by("-id").first()
        policy_with_all_gates = kubernetes_permission_policy(user)

    actions_created = K8sAdminAction.objects.count() - initial_action_count
    success = all(
        [
            _is_default_redacted(default_payload),
            _raw_absent(default_payload),
            _raw_absent(default_action.request_payload_sanitized if default_action else {}),
            _raw_absent(default_action.response_summary if default_action else {}),
            no_grant_denied["success"],
            no_grant_denied["provider_called"] is False,
            runtime_flag_denied["success"],
            runtime_flag_denied["provider_called"] is False,
            policy_with_flag_disabled.get("can_view_secret_values") is False,
            _is_secret_list_metadata_only(list_payload),
            _raw_absent(list_payload),
            _raw_absent(list_action.response_summary if list_action else {}),
            _action_secret_flags_are_booleans(list_action.response_summary if list_action else {}),
            _is_visible_payload(visible_payload),
            _raw_absent(visible_action.request_payload_sanitized if visible_action else {}),
            _raw_absent(visible_action.response_summary if visible_action else {}),
            policy_with_all_gates.get("can_view_secret_values") is True,
            actions_created == 3,
        ]
    )
    return {
        "success": success,
        "status": "ready" if success else "failed",
        "mode": "transaction_rollback",
        "default_redacted": _is_default_redacted(default_payload),
        "raw_secret_absent_from_default_response": _raw_absent(default_payload),
        "raw_secret_absent_from_action_summary": _raw_absent(default_action.response_summary if default_action else {}),
        "secret_read_rejected_without_grant": no_grant_denied["success"],
        "secret_read_rejected_without_runtime_flag": runtime_flag_denied["success"],
        "provider_not_called_for_denied_reveal": not no_grant_denied["provider_called"] and not runtime_flag_denied["provider_called"],
        "secret_read_capability_disabled_by_default": policy_with_flag_disabled.get("can_view_secret_values") is False,
        "secret_list_metadata_only": _is_secret_list_metadata_only(list_payload),
        "secret_list_raw_secret_absent": _raw_absent(list_payload),
        "secret_list_action_summary_raw_secret_absent": _raw_absent(list_action.response_summary if list_action else {}),
        "secret_list_action_summary_flags_boolean": _action_secret_flags_are_booleans(list_action.response_summary if list_action else {}),
        "secret_read_allowed_with_all_gates": _is_visible_payload(visible_payload),
        "allowed_action_summary_raw_secret_absent": _raw_absent(visible_action.response_summary if visible_action else {}),
        "default_provider_calls": default_provider_calls,
        "list_provider_calls": list_provider_calls,
        "visible_provider_calls": visible_provider_calls,
        "actions_created": actions_created,
        "persistent_rows": False,
    }


def _expect_secret_read_denied(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    setting_enabled: bool,
    expected_code: str,
) -> dict[str, Any]:
    provider_called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal provider_called
        provider_called = True
        return _secret_payload()

    with _temporary_settings(KUBERNETES_ADMIN_SECRET_READ_ENABLED=setting_enabled):
        try:
            get_cluster_resource_yaml(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{cluster.id}",
                api_version="v1",
                kind="Secret",
                namespace="release-secret-read",
                name="db-creds",
                include_secret_values=True,
                transport=fail_if_called,
            )
        except AdminResourceError as exc:
            return {
                "success": exc.code == expected_code,
                "expected_code": expected_code,
                "actual_code": exc.code,
                "provider_called": provider_called,
            }
    return {"success": False, "expected_code": expected_code, "actual_code": "", "provider_called": provider_called}


def _read_session(*, user, cluster: K8sCluster) -> K8sAdminSession:
    return K8sAdminSession.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        mode=K8sAdminSession.MODE_READ,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_LOW,
        allowed_verbs=["get", "list", "watch", "logs", "yaml"],
        allowed_kinds=["*"],
        allowed_namespaces=["*"],
        reason="release Secret-read controls smoke",
        expires_at=timezone.now() + timedelta(minutes=30),
    )


def _secret_payload() -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "db-creds",
            "namespace": "release-secret-read",
            "annotations": {"token": "raw-annotation-token"},
        },
        "data": {"password": "cmVsZWFzZS1wYXNzd29yZA==", "apiKey": "cmVsZWFzZS1hcGk="},
        "stringData": {"dsn": "postgres://release-secret"},
    }


def _secret_list_payload() -> dict[str, Any]:
    return {"apiVersion": "v1", "kind": "SecretList", "items": [_secret_payload()]}


def _is_default_redacted(payload: dict[str, Any]) -> bool:
    resource = payload.get("resource") if isinstance(payload.get("resource"), dict) else {}
    data = resource.get("data") if isinstance(resource.get("data"), dict) else {}
    string_data = resource.get("stringData") if isinstance(resource.get("stringData"), dict) else {}
    secret_values = payload.get("secret_values") if isinstance(payload.get("secret_values"), dict) else {}
    return (
        data.get("password") == "[redacted]"
        and data.get("apiKey") == "[redacted]"
        and string_data.get("dsn") == "[redacted]"
        and secret_values.get("requested") is False
        and secret_values.get("visible") is False
    )


def _is_secret_list_metadata_only(payload: dict[str, Any]) -> bool:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    first = items[0] if items and isinstance(items[0], dict) else {}
    data = first.get("data") if isinstance(first.get("data"), dict) else {}
    string_data = first.get("stringData") if isinstance(first.get("stringData"), dict) else {}
    secret_values = payload.get("secret_values") if isinstance(payload.get("secret_values"), dict) else {}
    return (
        data.get("password") == "[redacted]"
        and data.get("apiKey") == "[redacted]"
        and string_data.get("dsn") == "[redacted]"
        and secret_values.get("requested") is True
        and secret_values.get("visible") is False
        and secret_values.get("mode") == "list_metadata_only"
    )


def _is_visible_payload(payload: dict[str, Any]) -> bool:
    resource = payload.get("resource") if isinstance(payload.get("resource"), dict) else {}
    data = resource.get("data") if isinstance(resource.get("data"), dict) else {}
    string_data = resource.get("stringData") if isinstance(resource.get("stringData"), dict) else {}
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), dict) else {}
    secret_values = payload.get("secret_values") if isinstance(payload.get("secret_values"), dict) else {}
    return (
        data.get("password") == "cmVsZWFzZS1wYXNzd29yZA=="
        and data.get("apiKey") == "cmVsZWFzZS1hcGk="
        and string_data.get("dsn") == "postgres://release-secret"
        and annotations.get("token") == "[redacted]"
        and secret_values.get("requested") is True
        and secret_values.get("visible") is True
    )


def _raw_absent(value: object) -> bool:
    serialized = str(value)
    return all(raw not in serialized for raw in RAW_SECRET_VALUES)


def _action_secret_flags_are_booleans(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return value.get("secret_values_requested") is True and value.get("secret_values_visible") is False


def _grant(user, *features: str) -> None:
    for feature in features:
        _set_feature(user, feature, True)


def _set_feature(user, feature: str, allowed: bool) -> None:
    UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": allowed})


@contextmanager
def _temporary_settings(**overrides):
    previous = {key: getattr(settings, key, None) for key in overrides}
    missing = {key for key in overrides if not hasattr(settings, key)}
    try:
        for key, value in overrides.items():
            setattr(settings, key, value)
        yield
    finally:
        for key in overrides:
            if key in missing:
                try:
                    delattr(settings, key)
                except AttributeError:
                    pass
            else:
                setattr(settings, key, previous[key])
