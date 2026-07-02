from __future__ import annotations

from io import StringIO

from django.core.management import call_command

from kubernetes_ops.services.readonly_rbac import (
    build_kubernetes_readonly_rbac_bundle,
    build_kubernetes_readonly_rbac_report,
    render_kubernetes_readonly_rbac_yaml,
    validate_kubernetes_readonly_rbac_bundle,
)


def test_readonly_rbac_bundle_contains_only_read_verbs_and_no_exec_subresources():
    bundle = build_kubernetes_readonly_rbac_bundle()
    validation = validate_kubernetes_readonly_rbac_bundle(bundle)

    assert validation["status"] == "ready", validation["errors"]
    cluster_role = next(item for item in bundle["manifests"] if item["kind"] == "ClusterRole")
    for rule in cluster_role["rules"]:
        assert set(rule["verbs"]) == {"get", "list", "watch"}
        assert not {"pods/exec", "pods/attach", "pods/portforward"} & set(rule["resources"])
    yaml_payload = render_kubernetes_readonly_rbac_yaml(bundle)
    assert "kind: ServiceAccount" in yaml_payload
    assert "kind: ClusterRole" in yaml_payload
    assert "rules:\n  - apiGroups:" in yaml_payload
    assert "delete" not in yaml_payload


def test_readonly_rbac_validation_fails_closed_for_write_verbs():
    bundle = build_kubernetes_readonly_rbac_bundle()
    cluster_role = next(item for item in bundle["manifests"] if item["kind"] == "ClusterRole")
    cluster_role["rules"][0]["verbs"].append("delete")

    validation = validate_kubernetes_readonly_rbac_bundle(bundle)

    assert validation["status"] == "missing"
    assert any("write_verbs:delete" in item for item in validation["errors"])


def test_readonly_rbac_report_can_include_manifest():
    report = build_kubernetes_readonly_rbac_report(include_manifest=True)

    assert report["status"] == "ready"
    assert report["service_account_name"] == "webterm-kubernetes-readonly"
    assert report["validation"]["errors"] == []
    assert "ClusterRoleBinding" in report["manifest_yaml"]


def test_render_kubernetes_ops_readonly_rbac_command_validates_and_renders_yaml():
    stdout = StringIO()
    call_command("render_kubernetes_ops_readonly_rbac", stdout=stdout)
    payload = stdout.getvalue()

    assert "kind: ServiceAccount" in payload
    assert "webterm-kubernetes-readonly" in payload
    assert "pods/exec" not in payload


def test_render_kubernetes_ops_readonly_rbac_command_validate_only():
    stdout = StringIO()
    call_command("render_kubernetes_ops_readonly_rbac", "--validate-only", stdout=stdout)

    assert "manifest is valid" in stdout.getvalue()
