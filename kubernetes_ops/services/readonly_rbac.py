from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

READONLY_SERVICE_ACCOUNT_CONTRACT = {
    "name": "webterm-kubernetes-readonly",
    "namespace": "webterm-system",
    "scope": "namespace/project scoped per pilot cluster",
    "allowed_verbs": ["get", "list", "watch"],
    "allowed_resources": [
        "namespaces",
        "pods",
        "services",
        "ingresses",
        "events",
        "deployments",
        "statefulsets",
        "daemonsets",
        "replicasets",
    ],
    "denied_verbs": ["create", "update", "patch", "delete", "deletecollection", "escalate", "bind", "impersonate"],
    "denied_subresources": ["pods/exec", "pods/attach", "pods/portforward"],
}

READONLY_VERBS = set(READONLY_SERVICE_ACCOUNT_CONTRACT["allowed_verbs"])
WRITE_VERBS = set(READONLY_SERVICE_ACCOUNT_CONTRACT["denied_verbs"])
FORBIDDEN_SUBRESOURCES = set(READONLY_SERVICE_ACCOUNT_CONTRACT["denied_subresources"])

READONLY_RULES: tuple[dict[str, Any], ...] = (
    {"apiGroups": [""], "resources": ["namespaces", "pods", "services", "events"], "verbs": sorted(READONLY_VERBS)},
    {"apiGroups": ["networking.k8s.io"], "resources": ["ingresses"], "verbs": sorted(READONLY_VERBS)},
    {"apiGroups": ["apps"], "resources": ["deployments", "statefulsets", "daemonsets", "replicasets"], "verbs": sorted(READONLY_VERBS)},
)


def build_kubernetes_readonly_rbac_bundle(
    *,
    namespace: str = READONLY_SERVICE_ACCOUNT_CONTRACT["namespace"],
    service_account_name: str = READONLY_SERVICE_ACCOUNT_CONTRACT["name"],
) -> dict[str, Any]:
    namespace = _safe_name(namespace, fallback=READONLY_SERVICE_ACCOUNT_CONTRACT["namespace"])
    service_account_name = _safe_name(service_account_name, fallback=READONLY_SERVICE_ACCOUNT_CONTRACT["name"])
    role_name = f"{service_account_name}-clusterrole"
    binding_name = f"{service_account_name}-binding"
    manifests = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": namespace, "labels": {"app.kubernetes.io/part-of": "webterm-kubernetes-ops"}},
        },
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"name": service_account_name, "namespace": namespace},
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {"name": role_name},
            "rules": [deepcopy(rule) for rule in READONLY_RULES],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": {"name": binding_name},
            "subjects": [{"kind": "ServiceAccount", "name": service_account_name, "namespace": namespace}],
            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": role_name},
        },
    ]
    return {
        "namespace": namespace,
        "service_account_name": service_account_name,
        "role_name": role_name,
        "binding_name": binding_name,
        "manifests": manifests,
    }


def build_kubernetes_readonly_rbac_report(
    *,
    namespace: str = READONLY_SERVICE_ACCOUNT_CONTRACT["namespace"],
    service_account_name: str = READONLY_SERVICE_ACCOUNT_CONTRACT["name"],
    include_manifest: bool = False,
) -> dict[str, Any]:
    bundle = build_kubernetes_readonly_rbac_bundle(namespace=namespace, service_account_name=service_account_name)
    validation = validate_kubernetes_readonly_rbac_bundle(bundle)
    report = {
        "status": validation["status"],
        "namespace": bundle["namespace"],
        "service_account_name": bundle["service_account_name"],
        "role_name": bundle["role_name"],
        "binding_name": bundle["binding_name"],
        "object_count": len(bundle["manifests"]),
        "allowed_verbs": sorted(READONLY_VERBS),
        "denied_verbs": sorted(WRITE_VERBS),
        "denied_subresources": sorted(FORBIDDEN_SUBRESOURCES),
        "rules": [deepcopy(rule) for rule in READONLY_RULES],
        "validation": validation,
        "apply_command": "kubectl apply -f kubernetes-ops-readonly-rbac.yaml",
    }
    if include_manifest:
        report["manifest_yaml"] = render_kubernetes_readonly_rbac_yaml(bundle)
    return report


def validate_kubernetes_readonly_rbac_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    manifests = bundle.get("manifests") if isinstance(bundle, dict) else None
    if not isinstance(manifests, list):
        return {"status": "missing", "errors": ["manifests_missing"]}

    kinds = {str(item.get("kind") or "") for item in manifests if isinstance(item, dict)}
    errors: list[str] = []
    for required in {"Namespace", "ServiceAccount", "ClusterRole", "ClusterRoleBinding"}:
        if required not in kinds:
            errors.append(f"missing:{required}")

    cluster_roles = [item for item in manifests if isinstance(item, dict) and item.get("kind") == "ClusterRole"]
    if not cluster_roles:
        errors.append("cluster_role_missing")
    for role in cluster_roles:
        for rule in role.get("rules") or []:
            verbs = set(rule.get("verbs") or [])
            resources = set(rule.get("resources") or [])
            if not verbs:
                errors.append("rule:verbs_missing")
            if verbs - READONLY_VERBS:
                errors.append("rule:non_readonly_verbs:" + ",".join(sorted(verbs - READONLY_VERBS)))
            if verbs & WRITE_VERBS:
                errors.append("rule:write_verbs:" + ",".join(sorted(verbs & WRITE_VERBS)))
            if resources & FORBIDDEN_SUBRESOURCES:
                errors.append("rule:forbidden_subresources:" + ",".join(sorted(resources & FORBIDDEN_SUBRESOURCES)))

    binding_errors = _validate_cluster_role_binding(bundle)
    errors.extend(binding_errors)
    return {"status": "ready" if not errors else "missing", "errors": errors}


def render_kubernetes_readonly_rbac_yaml(bundle: dict[str, Any]) -> str:
    return "\n---\n".join(_to_yaml(item) for item in bundle["manifests"]) + "\n"


def render_kubernetes_readonly_rbac_json(bundle: dict[str, Any]) -> str:
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": bundle["manifests"]}, ensure_ascii=False, indent=2) + "\n"


def _validate_cluster_role_binding(bundle: dict[str, Any]) -> list[str]:
    manifests = bundle.get("manifests") or []
    service_account_name = bundle.get("service_account_name")
    namespace = bundle.get("namespace")
    role_name = bundle.get("role_name")
    bindings = [item for item in manifests if isinstance(item, dict) and item.get("kind") == "ClusterRoleBinding"]
    errors: list[str] = []
    if not bindings:
        return ["cluster_role_binding_missing"]
    for binding in bindings:
        subjects = binding.get("subjects") or []
        role_ref = binding.get("roleRef") or {}
        if not any(
            item.get("kind") == "ServiceAccount" and item.get("name") == service_account_name and item.get("namespace") == namespace
            for item in subjects
            if isinstance(item, dict)
        ):
            errors.append("binding:service_account_subject")
        if role_ref.get("kind") != "ClusterRole" or role_ref.get("name") != role_name:
            errors.append("binding:cluster_role_ref")
    return errors


def _to_yaml(value: Any, *, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, dict) or isinstance(item, list):
                lines.append(f"{pad}{key}:")
                lines.append(_to_yaml(item, indent=indent + 2))
            else:
                lines.append(f"{pad}{key}: {_yaml_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                rendered = _to_yaml(item, indent=indent + 2).splitlines()
                lines.append(f"{pad}- {rendered[0].lstrip()}")
                lines.extend(rendered[1:])
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{pad}{_yaml_scalar(value)}"


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    text = str(value)
    if not text or any(char in text for char in ":#{}[]&,*!|>'\"%@`") or text.strip() != text:
        return json.dumps(text)
    return text


def _safe_name(value: str, *, fallback: str) -> str:
    safe = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {"-", "."}).strip("-.")
    return safe or fallback
