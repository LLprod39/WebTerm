import json

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sProvider
from kubernetes_ops.services.security_review import build_kubernetes_security_review


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _csrf_token(client: Client) -> str:
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 200
    return client.cookies["csrftoken"].value


@pytest.fixture()
def k8s_staff_user(db):
    user = User.objects.create_user(username="k8s-csrf-admin", password="password-123", is_staff=True)
    UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
    UserAppPermission.objects.create(user=user, feature="studio_pipelines", allowed=True)
    return user


@pytest.fixture()
def k8s_inventory(db):
    provider = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.example.test",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", rancher_provider=provider)
    app = K8sAppRef.objects.create(
        name="payments-api",
        cluster=cluster,
        namespace="payments",
        owner=K8sAppRef.OWNER_DEVTRON,
        health=K8sCluster.HEALTH_WARNING,
    )
    return {"provider": provider, "cluster": cluster, "app": app}


@pytest.mark.django_db
def test_kubernetes_security_review_reports_current_posture(client, k8s_staff_user):
    client.force_login(k8s_staff_user)

    response = client.get(reverse("api_kubernetes_readiness"))

    assert response.status_code == 200
    payload = response.json()
    checks = {item["id"]: item for item in payload["checks"]}
    missing = [item for item in payload["security_review"]["checks"] if item["status"] == "missing"]
    assert checks["security_review"]["status"] == "ready", missing
    review_checks = {item["id"]: item for item in payload["security_review"]["checks"]}
    assert review_checks["csrf_middleware"]["status"] == "ready"
    assert review_checks["cors_credentials_scope"]["status"] == "ready"
    assert review_checks["clickjacking_middleware"]["status"] == "ready"
    assert review_checks["native_deeplink_csp_mode"]["status"] == "ready"


@override_settings(MIDDLEWARE=[])
def test_kubernetes_security_review_detects_missing_csrf_and_clickjacking_middleware():
    review = build_kubernetes_security_review()
    checks = {item["id"]: item for item in review["checks"]}

    assert review["status"] == "missing"
    assert checks["csrf_middleware"]["status"] == "missing"
    assert checks["clickjacking_middleware"]["status"] == "missing"


@override_settings(CORS_ALLOW_CREDENTIALS=True, CORS_ALLOWED_ORIGINS=["*"], CSRF_TRUSTED_ORIGINS=["*"])
def test_kubernetes_security_review_rejects_wildcard_trusted_origins_with_credentials():
    review = build_kubernetes_security_review()
    checks = {item["id"]: item for item in review["checks"]}

    assert review["status"] == "missing"
    assert checks["cors_credentials_scope"]["status"] == "missing"
    assert checks["csrf_trusted_origins_scope"]["status"] == "missing"


@pytest.mark.django_db
def test_kubernetes_unsafe_endpoints_require_csrf_token(k8s_staff_user, k8s_inventory):
    client = Client(enforce_csrf_checks=True)
    client.force_login(k8s_staff_user)
    provider = k8s_inventory["provider"]
    app = k8s_inventory["app"]
    unsafe_requests = [
        (
            "post",
            "api_kubernetes_providers",
            {},
            {
                "name": "devtron-main",
                "kind": "devtron",
                "base_url": "https://devtron.example.test",
                "auth_mode": "none",
            },
        ),
        ("patch", "api_kubernetes_provider_detail", {"provider_id": provider.id}, {"enabled": False}),
        ("delete", "api_kubernetes_provider_detail", {"provider_id": provider.id}, {}),
        ("post", "api_kubernetes_sync", {}, {"dry_run": True}),
        ("post", "api_kubernetes_provider_sync", {"provider_id": provider.id}, {"dry_run": True}),
        ("post", "api_kubernetes_provider_probe", {"provider_id": provider.id}, {}),
        (
            "post",
            "api_kubernetes_deeplink_audit",
            {},
            {
                "target_type": "app",
                "target_id": f"app_{app.id}",
                "link_key": "logs",
                "url": "https://devtron.example.test/logs",
            },
        ),
        ("post", "api_kubernetes_diagnose_action", {}, {"app_id": f"app_{app.id}"}),
        (
            "post",
            "api_kubernetes_action_request_approval",
            {},
            {"action": "k8s.rollout.restart", "reason": "test", "target": {"cluster_id": "cluster_1"}},
        ),
        ("post", "api_kubernetes_action_execute_approved", {}, {"request_id": "00000000-0000-0000-0000-000000000000"}),
    ]

    for method, route_name, kwargs, payload in unsafe_requests:
        response = getattr(client, method)(
            reverse(route_name, kwargs=kwargs),
            data=_json(payload),
            content_type="application/json",
        )
        assert response.status_code == 403, route_name


@pytest.mark.django_db
def test_kubernetes_unsafe_endpoint_accepts_valid_csrf_token(k8s_staff_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(k8s_staff_user)

    token = _csrf_token(client)
    response = client.post(
        reverse("api_kubernetes_providers"),
        data=_json(
            {
                "name": "devtron-main",
                "kind": K8sProvider.KIND_DEVTRON,
                "base_url": "https://devtron.example.test",
                "auth_mode": K8sProvider.AUTH_NONE,
            }
        ),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == 201
    assert response.json()["provider"]["name"] == "devtron-main"
