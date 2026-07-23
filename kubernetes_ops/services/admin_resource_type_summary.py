from __future__ import annotations

from typing import Any


def type_specific_resource_summaries(
    resource: dict[str, Any], spec: dict[str, Any], status: dict[str, Any]
) -> dict[str, Any]:
    return {
        "storage": _storage_summary(resource, spec, status),
        "ingress": _ingress_summary(resource, spec),
        "config": _config_summary(resource),
        "batch": _batch_summary(resource, spec, status),
        "autoscaling": _autoscaling_summary(resource, spec, status),
        "policy": _policy_summary(resource, spec, status),
        "rbac": _rbac_summary(resource),
        "endpoints": _endpoints_summary(resource),
        "quota": _quota_summary(resource, spec, status),
        "service_account": _service_account_summary(resource),
    }


def _storage_summary(resource: dict[str, Any], spec: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    kind = str(resource.get("kind") or "").lower()
    if kind not in {"persistentvolumeclaim", "persistentvolume", "storageclass"}:
        return {}
    requests = spec.get("resources", {}).get("requests", {}) if isinstance(spec.get("resources"), dict) else {}
    capacity = status.get("capacity") if isinstance(status.get("capacity"), dict) else spec.get("capacity")
    claim_ref = spec.get("claimRef") if isinstance(spec.get("claimRef"), dict) else {}
    return {
        "storage_class": _text(spec.get("storageClassName") or resource.get("provisioner"), 160),
        "volume_name": _text(spec.get("volumeName"), 180),
        "volume_mode": _text(spec.get("volumeMode"), 80),
        "access_modes": _string_list(spec.get("accessModes"), 12, 80),
        "requested": _text(requests.get("storage") if isinstance(requests, dict) else "", 80),
        "capacity": _text(capacity.get("storage") if isinstance(capacity, dict) else "", 80),
        "reclaim_policy": _text(spec.get("persistentVolumeReclaimPolicy") or resource.get("reclaimPolicy"), 80),
        "binding_mode": _text(resource.get("volumeBindingMode"), 80),
        "claim_ref": {"namespace": _text(claim_ref.get("namespace"), 120), "name": _text(claim_ref.get("name"), 180)}
        if claim_ref
        else {},
    }


def _ingress_summary(resource: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    if str(resource.get("kind") or "").lower() != "ingress":
        return {}
    rules = spec.get("rules") if isinstance(spec.get("rules"), list) else []
    tls = spec.get("tls") if isinstance(spec.get("tls"), list) else []
    hosts = [_text(rule.get("host"), 180) for rule in rules[:20] if isinstance(rule, dict) and rule.get("host")]
    return {
        "class_name": _text(spec.get("ingressClassName"), 120),
        "host_count": len(hosts),
        "hosts": hosts,
        "rule_count": len(rules),
        "tls_host_count": sum(len(item.get("hosts") or []) for item in tls if isinstance(item, dict)),
        "backend_services": _ingress_backend_names(rules),
    }


def _config_summary(resource: dict[str, Any]) -> dict[str, Any]:
    kind = str(resource.get("kind") or "").lower()
    if kind not in {"configmap", "secret"}:
        return {}
    data = resource.get("data") if isinstance(resource.get("data"), dict) else {}
    binary_data = resource.get("binaryData") if isinstance(resource.get("binaryData"), dict) else {}
    string_data = resource.get("stringData") if isinstance(resource.get("stringData"), dict) else {}
    return {
        "type": _text(resource.get("type"), 120),
        "data_key_count": len(data),
        "binary_data_key_count": len(binary_data),
        "string_data_key_count": len(string_data),
        "data_keys": _keys(data),
        "binary_data_keys": _keys(binary_data),
        "string_data_keys": _keys(string_data),
    }


def _batch_summary(resource: dict[str, Any], spec: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    kind = str(resource.get("kind") or "").lower()
    if kind == "job":
        return {
            "completions": spec.get("completions"),
            "parallelism": spec.get("parallelism"),
            "backoff_limit": spec.get("backoffLimit"),
            "active": status.get("active"),
            "succeeded": status.get("succeeded"),
            "failed": status.get("failed"),
            "completion_time": _text(status.get("completionTime"), 80),
        }
    if kind == "cronjob":
        job_template = spec.get("jobTemplate") if isinstance(spec.get("jobTemplate"), dict) else {}
        job_spec = job_template.get("spec") if isinstance(job_template.get("spec"), dict) else {}
        active = status.get("active") if isinstance(status.get("active"), list) else []
        return {
            "schedule": _text(spec.get("schedule"), 120),
            "suspend": bool(spec.get("suspend")),
            "concurrency_policy": _text(spec.get("concurrencyPolicy"), 80),
            "successful_history_limit": spec.get("successfulJobsHistoryLimit"),
            "failed_history_limit": spec.get("failedJobsHistoryLimit"),
            "job_completions": job_spec.get("completions"),
            "job_parallelism": job_spec.get("parallelism"),
            "last_schedule_time": _text(status.get("lastScheduleTime"), 80),
            "last_successful_time": _text(status.get("lastSuccessfulTime"), 80),
            "active_count": len(active),
        }
    return {}


def _autoscaling_summary(resource: dict[str, Any], spec: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    if str(resource.get("kind") or "").lower() != "horizontalpodautoscaler":
        return {}
    target = spec.get("scaleTargetRef") if isinstance(spec.get("scaleTargetRef"), dict) else {}
    metrics = spec.get("metrics") if isinstance(spec.get("metrics"), list) else []
    return {
        "target": {
            "api_version": _text(target.get("apiVersion"), 80),
            "kind": _text(target.get("kind"), 80),
            "name": _text(target.get("name"), 180),
        },
        "min_replicas": spec.get("minReplicas"),
        "max_replicas": spec.get("maxReplicas"),
        "current_replicas": status.get("currentReplicas"),
        "desired_replicas": status.get("desiredReplicas"),
        "metric_count": len(metrics),
        "metrics": [_hpa_metric(item) for item in metrics[:8] if isinstance(item, dict)],
    }


def _policy_summary(resource: dict[str, Any], spec: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    kind = str(resource.get("kind") or "").lower()
    if kind == "poddisruptionbudget":
        return {
            "min_available": _int_or_text(spec.get("minAvailable")),
            "max_unavailable": _int_or_text(spec.get("maxUnavailable")),
            "selector_keys": _keys(_selector_from_spec(spec)),
            "current_healthy": status.get("currentHealthy"),
            "desired_healthy": status.get("desiredHealthy"),
            "disruptions_allowed": status.get("disruptionsAllowed"),
            "expected_pods": status.get("expectedPods"),
        }
    if kind == "networkpolicy":
        ingress = spec.get("ingress") if isinstance(spec.get("ingress"), list) else []
        egress = spec.get("egress") if isinstance(spec.get("egress"), list) else []
        return {
            "pod_selector_keys": _keys(_network_policy_selector(spec)),
            "policy_types": _string_list(spec.get("policyTypes"), 8, 80),
            "ingress_rule_count": len(ingress),
            "egress_rule_count": len(egress),
        }
    return {}


def _rbac_summary(resource: dict[str, Any]) -> dict[str, Any]:
    kind = str(resource.get("kind") or "").lower()
    if kind in {"role", "clusterrole"}:
        rules = resource.get("rules") if isinstance(resource.get("rules"), list) else []
        verbs = _unique_from_rules(rules, "verbs")
        raw_resources = _raw_unique_from_rules(rules, "resources")
        resources = _unique_from_rules(rules, "resources")
        return {
            "rule_count": len(rules),
            "verbs": verbs,
            "resources": resources,
            "api_groups": _unique_from_rules(rules, "apiGroups"),
            "grants_write": _grants_write(verbs),
            "grants_secret_access": "*" in raw_resources or "secrets" in raw_resources,
            "has_wildcard": "*" in verbs or "*" in raw_resources,
        }
    if kind in {"rolebinding", "clusterrolebinding"}:
        subjects = resource.get("subjects") if isinstance(resource.get("subjects"), list) else []
        role_ref = resource.get("roleRef") if isinstance(resource.get("roleRef"), dict) else {}
        return {
            "role_ref": {
                "api_group": _text(role_ref.get("apiGroup"), 120),
                "kind": _text(role_ref.get("kind"), 80),
                "name": _text(role_ref.get("name"), 180),
            },
            "subject_count": len(subjects),
            "subject_kinds": sorted(
                {_text(item.get("kind"), 80) for item in subjects if isinstance(item, dict) and item.get("kind")}
            )[:20],
            "has_service_account_subject": any(
                isinstance(item, dict) and item.get("kind") == "ServiceAccount" for item in subjects
            ),
            "has_group_subject": any(isinstance(item, dict) and item.get("kind") == "Group" for item in subjects),
        }
    return {}


def _endpoints_summary(resource: dict[str, Any]) -> dict[str, Any]:
    kind = str(resource.get("kind") or "").lower()
    if kind == "endpoints":
        subsets = resource.get("subsets") if isinstance(resource.get("subsets"), list) else []
        addresses = sum(len(item.get("addresses") or []) for item in subsets if isinstance(item, dict))
        not_ready = sum(len(item.get("notReadyAddresses") or []) for item in subsets if isinstance(item, dict))
        ports = [
            port
            for item in subsets
            if isinstance(item, dict)
            for port in item.get("ports") or []
            if isinstance(port, dict)
        ]
        return {
            "subset_count": len(subsets),
            "address_count": addresses,
            "not_ready_address_count": not_ready,
            "ports": _port_summaries(ports),
        }
    if kind == "endpointslice":
        endpoints = resource.get("endpoints") if isinstance(resource.get("endpoints"), list) else []
        ports = resource.get("ports") if isinstance(resource.get("ports"), list) else []
        return {
            "address_type": _text(resource.get("addressType"), 80),
            "endpoint_count": len(endpoints),
            "ready_count": _endpoint_condition_count(endpoints, "ready"),
            "serving_count": _endpoint_condition_count(endpoints, "serving"),
            "terminating_count": _endpoint_condition_count(endpoints, "terminating"),
            "ports": _port_summaries([item for item in ports if isinstance(item, dict)]),
        }
    return {}


def _quota_summary(resource: dict[str, Any], spec: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    kind = str(resource.get("kind") or "").lower()
    if kind == "resourcequota":
        hard = status.get("hard") if isinstance(status.get("hard"), dict) else spec.get("hard")
        used = status.get("used") if isinstance(status.get("used"), dict) else {}
        scopes = spec.get("scopes") if isinstance(spec.get("scopes"), list) else []
        return {
            "scope_count": len(scopes),
            "scopes": _string_list(scopes, 20, 120),
            "hard_keys": _keys(hard),
            "used_keys": _keys(used),
            "hard": _safe_string_map(hard),
            "used": _safe_string_map(used),
        }
    if kind == "limitrange":
        limits = spec.get("limits") if isinstance(spec.get("limits"), list) else []
        return {
            "limit_count": len(limits),
            "types": sorted(
                {_text(item.get("type"), 80) for item in limits if isinstance(item, dict) and item.get("type")}
            )[:20],
            "default_keys": _merged_nested_keys(limits, "default"),
            "default_request_keys": _merged_nested_keys(limits, "defaultRequest"),
            "min_keys": _merged_nested_keys(limits, "min"),
            "max_keys": _merged_nested_keys(limits, "max"),
        }
    return {}


def _service_account_summary(resource: dict[str, Any]) -> dict[str, Any]:
    if str(resource.get("kind") or "").lower() != "serviceaccount":
        return {}
    secrets = resource.get("secrets") if isinstance(resource.get("secrets"), list) else []
    image_pull_secrets = resource.get("imagePullSecrets") if isinstance(resource.get("imagePullSecrets"), list) else []
    return {
        "secret_ref_count": len(secrets),
        "image_pull_secret_ref_count": len(image_pull_secrets),
        "automount_service_account_token": resource.get("automountServiceAccountToken"),
    }


def _ingress_backend_names(rules: list[Any]) -> list[str]:
    names: list[str] = []
    for rule in rules[:20]:
        http = rule.get("http") if isinstance(rule, dict) and isinstance(rule.get("http"), dict) else {}
        paths = http.get("paths") if isinstance(http.get("paths"), list) else []
        for path in paths[:20]:
            service = (
                path.get("backend", {}).get("service", {})
                if isinstance(path, dict) and isinstance(path.get("backend"), dict)
                else {}
            )
            name = _text(service.get("name") if isinstance(service, dict) else "", 180)
            if name and name not in names:
                names.append(name)
    return names[:20]


def _hpa_metric(metric: dict[str, Any]) -> dict[str, Any]:
    metric_type = _text(metric.get("type"), 80)
    source = metric.get(metric_type.lower()) if metric_type else None
    source = source if isinstance(source, dict) else {}
    target = source.get("target") if isinstance(source.get("target"), dict) else {}
    return {
        "type": metric_type,
        "name": _text(source.get("name") or source.get("metric", {}).get("name"), 160),
        "target_type": _text(target.get("type"), 80),
        "average_utilization": target.get("averageUtilization"),
        "average_value": _text(target.get("averageValue"), 80),
        "value": _text(target.get("value"), 80),
    }


def _selector_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    selector = spec.get("selector") if isinstance(spec.get("selector"), dict) else {}
    if isinstance(selector.get("matchLabels"), dict):
        return selector["matchLabels"]
    return selector


def _network_policy_selector(spec: dict[str, Any]) -> dict[str, Any]:
    selector = spec.get("podSelector") if isinstance(spec.get("podSelector"), dict) else {}
    if isinstance(selector.get("matchLabels"), dict):
        return selector["matchLabels"]
    return selector


def _unique_from_rules(rules: list[Any], key: str) -> list[str]:
    values = {
        _safe_key(item) if key == "resources" else _text(item, 120) for item in _raw_unique_from_rules(rules, key)
    }
    return sorted(item for item in values if item)[:40]


def _raw_unique_from_rules(rules: list[Any], key: str) -> list[str]:
    values: set[str] = set()
    for rule in rules[:40]:
        if not isinstance(rule, dict):
            continue
        for item in rule.get(key) or []:
            values.add(_text(item, 120))
    return sorted(item for item in values if item)[:40]


def _grants_write(verbs: list[str]) -> bool:
    write_verbs = {"*", "create", "update", "patch", "delete", "deletecollection", "bind", "escalate", "impersonate"}
    return bool(write_verbs.intersection({verb.lower() for verb in verbs}))


def _port_summaries(ports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": _text(port.get("name"), 80),
            "port": port.get("port"),
            "protocol": _text(port.get("protocol"), 20),
        }
        for port in ports[:20]
    ]


def _endpoint_condition_count(endpoints: list[Any], name: str) -> int:
    total = 0
    for endpoint in endpoints:
        conditions = (
            endpoint.get("conditions")
            if isinstance(endpoint, dict) and isinstance(endpoint.get("conditions"), dict)
            else {}
        )
        if conditions.get(name) is True:
            total += 1
    return total


def _safe_string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {_safe_key(key): _text(item, 80) for key, item in list(value.items())[:40]}


def _merged_nested_keys(items: list[Any], key: str) -> list[str]:
    values: set[str] = set()
    for item in items[:20]:
        nested = item.get(key) if isinstance(item, dict) and isinstance(item.get(key), dict) else {}
        values.update(_keys(nested))
    return sorted(values)[:40]


def _keys(value: Any) -> list[str]:
    return sorted(_safe_key(key) for key in value)[:40] if isinstance(value, dict) else []


def _string_list(value: Any, limit: int, text_limit: int) -> list[str]:
    return [_text(item, text_limit) for item in value[:limit]] if isinstance(value, list) else []


def _int_or_text(value: Any) -> Any:
    if value is None or isinstance(value, (int, float)):
        return value
    return _text(value, 80)


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _safe_key(value: Any) -> str:
    key = str(value or "")[:120]
    normalized = key.replace("-", "_").lower()
    if any(
        part in normalized
        for part in ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")
    ):
        return "[redacted]"
    return key
