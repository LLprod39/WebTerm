from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.services.access_model import (
    ACCESS_ROLE_MAPPING,
    READ_ONLY_SERVICE_ACCOUNT,
    build_kubernetes_access_model_report,
)
from kubernetes_ops.services.identity_runtime import (
    build_kubernetes_identity_runtime_report,
    kubernetes_identity_runtime_check,
)


def test_kubernetes_access_model_report_documents_oidc_rbac_mapping():
    report = build_kubernetes_access_model_report()

    assert report["status"] == "ready", report["missing_markers"]
    assert report["identity_provider"] == "Keycloak/OIDC"
    assert report["native_mutations_enabled"] is False
    assert report["exec_enabled"] is False
    assert {row["keycloak_group"] for row in report["role_mappings"]} == {row["keycloak_group"] for row in ACCESS_ROLE_MAPPING}
    assert "webterm-kubernetes-readers" in {row["keycloak_group"] for row in report["role_mappings"]}
    assert report["read_only_service_account"]["allowed_verbs"] == ["get", "list", "watch"]
    assert report["read_only_rbac_manifest"]["status"] == "ready"
    assert report["read_only_rbac_manifest"]["validation"]["errors"] == []
    assert set(READ_ONLY_SERVICE_ACCOUNT["denied_subresources"]).issuperset({"pods/exec", "pods/attach", "pods/portforward"})


def test_kubernetes_access_model_report_fails_closed_when_docs_are_missing(tmp_path):
    report = build_kubernetes_access_model_report(base_dir=tmp_path)

    assert report["status"] == "missing"
    assert report["missing_markers"]


def test_kubernetes_identity_runtime_gate_is_ready_outside_production(settings, monkeypatch):
    settings.KUBERNETES_OPS_RELEASE_ENVIRONMENT = "local"
    settings.DOMAIN_AUTH_ENABLED = False
    settings.LDAP_ENABLED = False
    monkeypatch.delenv("KEYCLOAK_PROD_URL", raising=False)
    monkeypatch.delenv("KEYCLOAK_URL", raising=False)

    report = build_kubernetes_identity_runtime_report(use_model_config=False)
    check = kubernetes_identity_runtime_check()

    assert report["status"] == "ready"
    assert report["enforced"] is False
    assert report["webterm_login_gateway"]["mode"] == "local"
    assert report["webterm_login_gateway"]["normal_user_external_platform_login"] is False
    assert report["webterm_login_gateway"]["browser_receives_provider_credentials"] is False
    assert check["status"] == "ready"


def test_kubernetes_identity_runtime_gate_blocks_production_without_sso(settings, monkeypatch):
    settings.KUBERNETES_OPS_RELEASE_ENVIRONMENT = "production"
    settings.DOMAIN_AUTH_ENABLED = False
    settings.LDAP_ENABLED = False
    settings.DOMAIN_AUTH_HEADER = "REMOTE_USER"
    monkeypatch.delenv("KEYCLOAK_PROD_URL", raising=False)
    monkeypatch.delenv("KEYCLOAK_URL", raising=False)
    monkeypatch.delenv("KEYCLOAK_PROD_REALM", raising=False)
    monkeypatch.delenv("KEYCLOAK_REALM", raising=False)

    report = build_kubernetes_identity_runtime_report(use_model_config=False)

    assert report["status"] == "missing"
    assert report["webterm_login_gateway"]["mode"] == "local"
    assert "Production Kubernetes login gateway must use Domain SSO/OIDC or LDAP" in report["errors"]


def test_kubernetes_identity_runtime_gate_accepts_production_sso(settings, monkeypatch):
    settings.KUBERNETES_OPS_RELEASE_ENVIRONMENT = "production"
    settings.DOMAIN_AUTH_ENABLED = True
    settings.LDAP_ENABLED = False
    settings.DOMAIN_AUTH_HEADER = "X-Forwarded-User"
    settings.DOMAIN_AUTH_AUTO_CREATE = True
    settings.DOMAIN_AUTH_DEFAULT_PROFILE = "server_only"
    monkeypatch.setenv("KEYCLOAK_PROD_URL", "https://keycloak.company.example")
    monkeypatch.setenv("KEYCLOAK_PROD_REALM", "webterm")
    monkeypatch.setenv("KEYCLOAK_PROD_VERIFY_SSL", "true")

    report = build_kubernetes_identity_runtime_report(use_model_config=False)

    assert report["status"] == "ready"
    assert report["enforced"] is True
    assert report["identity_provider"] == "WebTerm Domain SSO/OIDC"
    assert report["webterm_login_gateway"]["mode"] == "domain_sso"
    assert report["keycloak"]["url"] == "https://keycloak.company.example"
    assert report["domain_auth"]["auto_create_profile_safe"] is True


def test_kubernetes_identity_runtime_gate_accepts_production_ldap(settings):
    settings.KUBERNETES_OPS_RELEASE_ENVIRONMENT = "production"
    settings.DOMAIN_AUTH_ENABLED = False
    settings.LDAP_ENABLED = True
    settings.LDAP_SERVER = "ldaps://ldap.company.example"
    settings.LDAP_SEARCH_BASE = "dc=company,dc=example"
    settings.LDAP_BIND_DN = ""
    settings.LDAP_BIND_PASSWORD = ""
    settings.LDAP_START_TLS = False
    settings.LDAP_IGNORE_CERT = False
    settings.AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.ModelBackend",
        "django_auth_ldap.backend.LDAPBackend",
    ]

    report = build_kubernetes_identity_runtime_report(use_model_config=False)

    assert report["status"] == "ready"
    assert report["identity_provider"] == "WebTerm LDAP"
    assert report["webterm_login_gateway"]["mode"] == "ldap"
    assert report["webterm_login_gateway"]["provider_access_strategy"] == "backend_held_service_credentials"
    assert report["ldap"]["tls_ready"] is True


def test_kubernetes_identity_runtime_gate_blocks_insecure_production_ldap(settings):
    settings.KUBERNETES_OPS_RELEASE_ENVIRONMENT = "production"
    settings.DOMAIN_AUTH_ENABLED = False
    settings.LDAP_ENABLED = True
    settings.LDAP_SERVER = "ldap://ldap.company.example"
    settings.LDAP_SEARCH_BASE = "dc=company,dc=example"
    settings.LDAP_BIND_DN = "cn=reader,dc=company,dc=example"
    settings.LDAP_BIND_PASSWORD = ""
    settings.LDAP_START_TLS = False
    settings.LDAP_IGNORE_CERT = True
    settings.AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

    report = build_kubernetes_identity_runtime_report(use_model_config=False)

    assert report["status"] == "missing"
    assert report["webterm_login_gateway"]["mode"] == "ldap"
    assert "LDAP_BIND_PASSWORD" in report["errors"]
    assert "django_auth_ldap backend is not loaded" in report["errors"]
    assert "LDAP production connection must use ldaps or START_TLS" in report["errors"]
    assert "LDAP production TLS certificate verification is disabled" in report["errors"]


@pytest.mark.django_db
def test_kubernetes_readiness_exposes_access_model_gate(client):
    user = User.objects.create_user(username="k8s-access-model", password="password-123")
    UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
    client.force_login(user)

    response = client.get(reverse("api_kubernetes_readiness"))

    assert response.status_code == 200
    payload = response.json()
    checks = {item["id"]: item for item in payload["checks"]}
    assert checks["access_model"]["status"] == "ready"
    assert checks["access_model"]["required"] is True
    assert checks["identity_runtime"]["status"] == "ready"
    assert checks["identity_runtime"]["required"] is True
    assert payload["access_model"]["status"] == "ready"
    assert payload["identity_runtime"]["status"] == "ready"
    assert payload["identity_runtime"]["webterm_login_gateway"]["webterm_is_primary_login"] is True
    assert payload["access_model"]["read_only_service_account"]["allowed_verbs"] == ["get", "list", "watch"]
    assert payload["access_model"]["read_only_rbac_manifest"]["status"] == "ready"
