from __future__ import annotations

import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_dry_run import (
    _active_write_session_for_user,
    _parse_manifest,
    _ref_from_manifest,
    manifest_fingerprint,
)
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    cluster_for_value,
    rancher_resource_path,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport

MAX_VALIDATION_ERRORS = 50
MAX_SCHEMA_DEPTH = 8
MAX_CRD_ITEMS = 500


def validate_kubernetes_manifest_schema(
    *,
    user,
    session_id: str,
    cluster_id: str,
    manifest: Any = None,
    manifest_yaml: str = "",
    namespace: str = "",
    resource: str = "",
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    submitted = _parse_manifest(manifest=manifest, manifest_yaml=manifest_yaml)
    ref = _ref_from_manifest(submitted, namespace=namespace, resource=resource)
    session = _active_write_session_for_user(user, session_id, cluster, ref=ref)
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_DRY_RUN_APPLY)
    provider = _required_rancher_provider(cluster)
    sanitized_submitted = sanitize_kubernetes_resource(submitted)
    schema_lookup = _lookup_crd_schema(provider=provider, cluster=cluster, ref=ref, transport=transport)
    validation = _validate_with_schema(submitted, schema_lookup["schema"])
    redacted = "[redacted]" in str(sanitized_submitted)
    action = _record_schema_validation_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        submitted=sanitized_submitted,
        manifest_fingerprint_value=manifest_fingerprint(submitted),
        schema_lookup=schema_lookup,
        validation=validation,
        redacted=redacted,
    )
    return {
        "success": True,
        "mode": "admin_write_preview",
        "operation": "schema_validate",
        "mutates_state": False,
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": _target_payload(ref),
        "path": schema_lookup.get("public_path", ""),
        "schema_available": bool(schema_lookup["available"]),
        "schema_source": schema_lookup["source"],
        "validation": validation,
        "valid": validation["status"] in {"valid", "schema_unavailable"},
        "redacted": redacted,
        "submitted_summary": {
            "top_level_fields": sorted(sanitized_submitted.keys()),
            "manifest_fingerprint_present": True,
            "body_returned": False,
        },
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "requires_write_session": True,
            "requires_approved_session": True,
            "server_side_dry_run": False,
            "blocked_actions": ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
    }


def _lookup_crd_schema(
    *,
    provider: K8sProvider,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    transport: ProviderTransport | None,
) -> dict[str, Any]:
    group, version = _api_group_version(ref.api_version)
    path = _crd_list_path(provider, cluster)
    if not group:
        return _schema_missing(path, reason="built_in_schema_not_available")
    try:
        payload = ProviderJsonClient(provider, transport=transport).get(path)
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc
    crd = _matching_crd(payload_items(payload)[:MAX_CRD_ITEMS], group=group, version=version, kind=ref.kind)
    if crd is None:
        return _schema_missing(path, reason="crd_schema_not_found")
    schema = _schema_for_version(crd, version)
    if not schema:
        return _schema_missing(path, reason="crd_openapi_schema_not_found", crd=crd, version=version)
    return {
        "available": True,
        "schema": schema,
        "path": path,
        "public_path": _public_path(path),
        "source": _schema_source(crd, version=version, available=True, reason=""),
    }


def _validate_with_schema(manifest: dict[str, Any], schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {
            "status": "schema_unavailable",
            "errors": [],
            "warnings": ["crd_schema_unavailable"],
            "checked_paths": [],
            "unsupported_keywords": [],
            "error_count": 0,
            "max_errors": MAX_VALIDATION_ERRORS,
        }
    context = {"errors": [], "checked_paths": [], "unsupported_keywords": set()}
    _validate_node(manifest, schema, path="$", depth=0, context=context)
    errors = context["errors"][:MAX_VALIDATION_ERRORS]
    return {
        "status": "invalid" if errors else "valid",
        "errors": errors,
        "warnings": [],
        "checked_paths": context["checked_paths"][:200],
        "unsupported_keywords": sorted(context["unsupported_keywords"])[:40],
        "error_count": len(errors),
        "max_errors": MAX_VALIDATION_ERRORS,
    }


def _validate_node(value: Any, schema: dict[str, Any], *, path: str, depth: int, context: dict[str, Any]) -> None:
    if len(context["errors"]) >= MAX_VALIDATION_ERRORS or depth > MAX_SCHEMA_DEPTH:
        return
    context["checked_paths"].append(path)
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, str(expected_type)):
        _add_error(context, path=path, code="type_mismatch", expected=str(expected_type), actual=_actual_type(value))
        return
    if "enum" in schema and isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        _add_error(context, path=path, code="enum_mismatch", expected="enum", actual=_actual_type(value))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        _validate_number_bounds(value, schema, path=path, context=context)
    if isinstance(value, dict):
        _validate_object(value, schema, path=path, depth=depth, context=context)
    elif isinstance(value, list):
        _validate_array(value, schema, path=path, depth=depth, context=context)
    _capture_unsupported_keywords(schema, context)


def _validate_object(value: dict[str, Any], schema: dict[str, Any], *, path: str, depth: int, context: dict[str, Any]) -> None:
    required = schema.get("required")
    if isinstance(required, list):
        for field in required:
            key = str(field)
            if key not in value:
                _add_error(context, path=f"{path}.{key}", code="required_missing", expected="present", actual="missing")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    for key, property_schema in properties.items():
        if key not in value or not isinstance(property_schema, dict):
            continue
        _validate_node(value[key], property_schema, path=f"{path}.{key}", depth=depth + 1, context=context)


def _validate_array(value: list[Any], schema: dict[str, Any], *, path: str, depth: int, context: dict[str, Any]) -> None:
    item_schema = schema.get("items")
    if not isinstance(item_schema, dict):
        return
    for index, item in enumerate(value[:100]):
        _validate_node(item, item_schema, path=f"{path}[{index}]", depth=depth + 1, context=context)


def _validate_number_bounds(value: int | float, schema: dict[str, Any], *, path: str, context: dict[str, Any]) -> None:
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, (int, float)) and value < minimum:
        _add_error(context, path=path, code="minimum_violation", expected="minimum", actual="number")
    if isinstance(maximum, (int, float)) and value > maximum:
        _add_error(context, path=path, code="maximum_violation", expected="maximum", actual="number")


def _capture_unsupported_keywords(schema: dict[str, Any], context: dict[str, Any]) -> None:
    for key in ("oneOf", "anyOf", "allOf", "not", "patternProperties", "dependencies"):
        if key in schema:
            context["unsupported_keywords"].add(key)


def _add_error(context: dict[str, Any], *, path: str, code: str, expected: str, actual: str) -> None:
    if len(context["errors"]) >= MAX_VALIDATION_ERRORS:
        return
    context["errors"].append({"path": path[:240], "code": code, "expected": expected[:120], "actual": actual[:120]})


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _actual_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    return type(value).__name__[:80]


def _record_schema_validation_action(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    submitted: dict[str, Any],
    manifest_fingerprint_value: str,
    schema_lookup: dict[str, Any],
    validation: dict[str, Any],
    redacted: bool,
) -> K8sAdminAction:
    return K8sAdminAction.objects.create(
        session=session,
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace=ref.namespace,
        resource_api_version=ref.api_version,
        resource_kind=ref.kind,
        resource_name=ref.name,
        verb=K8sAdminAction.VERB_LIST,
        status=K8sAdminAction.STATUS_COMPLETED,
        request_payload_sanitized={
            "target": _target_payload(ref),
            "schema_validation": True,
            "redacted": redacted,
            "manifest_fingerprint": manifest_fingerprint_value,
            "submitted_top_level_fields": sorted(submitted.keys()),
        },
        response_summary=sanitize_metadata(
            {
                "source": "crd_openapi_schema",
                "schema_validation": True,
                "schema_available": bool(schema_lookup["available"]),
                "schema_source": schema_lookup["source"],
                "validation_status": validation["status"],
                "error_count": validation["error_count"],
                "checked_path_count": len(validation["checked_paths"]),
                "redacted": redacted,
            }
        ),
    )


def _matching_crd(items: list[Any], *, group: str, version: str, kind: str) -> dict[str, Any] | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
        names = spec.get("names") if isinstance(spec.get("names"), dict) else {}
        versions = spec.get("versions") if isinstance(spec.get("versions"), list) else []
        if spec.get("group") == group and names.get("kind") == kind and any(v.get("name") == version for v in versions if isinstance(v, dict)):
            return item
    return None


def _schema_for_version(crd: dict[str, Any], version: str) -> dict[str, Any]:
    spec = crd.get("spec") if isinstance(crd.get("spec"), dict) else {}
    for item in spec.get("versions") or []:
        if not isinstance(item, dict) or item.get("name") != version:
            continue
        schema = item.get("schema") if isinstance(item.get("schema"), dict) else {}
        openapi = schema.get("openAPIV3Schema") if isinstance(schema.get("openAPIV3Schema"), dict) else {}
        return openapi
    return {}


def _schema_missing(path: str, *, reason: str, crd: dict[str, Any] | None = None, version: str = "") -> dict[str, Any]:
    return {
        "available": False,
        "schema": None,
        "path": path,
        "public_path": _public_path(path),
        "source": _schema_source(crd or {}, version=version, available=False, reason=reason),
    }


def _schema_source(crd: dict[str, Any], *, version: str, available: bool, reason: str) -> dict[str, Any]:
    metadata = crd.get("metadata") if isinstance(crd.get("metadata"), dict) else {}
    spec = crd.get("spec") if isinstance(crd.get("spec"), dict) else {}
    return sanitize_metadata(
        {
            "available": available,
            "reason": reason,
            "crd_name": str(metadata.get("name") or "")[:180],
            "group": str(spec.get("group") or "")[:180],
            "version": str(version or "")[:80],
            "kind": str((spec.get("names") or {}).get("kind") or "")[:120] if isinstance(spec.get("names"), dict) else "",
        }
    )


def _crd_list_path(provider: K8sProvider, cluster: K8sCluster) -> str:
    return rancher_resource_path(
        provider,
        cluster,
        KubernetesResourceRef(api_version="apiextensions.k8s.io/v1", kind="CustomResourceDefinition", resource="customresourcedefinitions"),
    )


def _api_group_version(api_version: str) -> tuple[str, str]:
    value = str(api_version or "").strip()
    if "/" not in value:
        return "", value
    group, _, version = value.partition("/")
    return group, version


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for schema validation.", code="rancher_provider_required", status=409)
    return provider


def _cluster_payload(cluster: K8sCluster) -> dict[str, Any]:
    return {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id}


def _provider_payload(provider: K8sProvider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "kind": provider.kind}


def _target_payload(ref: KubernetesResourceRef) -> dict[str, Any]:
    return {
        "api_version": ref.api_version,
        "kind": ref.kind,
        "resource": ref.resource,
        "namespace": ref.namespace,
        "name": ref.name,
    }


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
