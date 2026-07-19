from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KubectlRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
LOCAL_PLATFORM_SCHEMA_VERSION = "kubernetes_ops.local_platform_evidence.v1"


@dataclass(frozen=True)
class LocalPlatformProbeOptions:
    context: str = "kind-webterm-k8s"
    kubectl: str = "kubectl"
    require_context: bool = True


COMPONENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "rancher",
        "namespace": "cattle-system",
        "services": ["rancher"],
        "deployments": ["rancher", "rancher-webhook"],
        "statefulsets": [],
    },
    {
        "id": "fleet",
        "namespace": "cattle-fleet-system",
        "services": ["gitjob", "monitoring-fleet-controller"],
        "deployments": ["fleet-controller", "gitjob", "helmops"],
        "statefulsets": [],
    },
    {
        "id": "devtron",
        "namespace": "devtroncd",
        "services": ["devtron-service", "dashboard-service"],
        "deployments": ["devtron", "dashboard", "kubelink", "argocd-dex-server"],
        "statefulsets": ["postgresql-postgresql"],
    },
)


def verify_kubernetes_local_platform(
    options: LocalPlatformProbeOptions | None = None,
    *,
    runner: KubectlRunner | None = None,
) -> dict[str, Any]:
    options = options or LocalPlatformProbeOptions()
    runner = runner or _default_runner(options)
    context_result = _kubectl(runner, ["config", "current-context"])
    current_context = _stdout(context_result)
    components = [_component_report(component, options=options, runner=runner) for component in COMPONENTS]
    errors: list[str] = []
    if context_result.returncode != 0:
        errors.append("kubectl_context_unavailable:" + _stderr(context_result))
    if options.require_context and options.context and current_context != options.context:
        errors.append(f"context_mismatch:expected={options.context}:actual={current_context or 'missing'}")
    for component in components:
        errors.extend(f"{component['id']}:{item}" for item in component.get("errors", []))
    return {
        "schema_version": LOCAL_PLATFORM_SCHEMA_VERSION,
        "status": "ready" if not errors else "missing",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "context": current_context,
        "expected_context": options.context,
        "kubectl": options.kubectl,
        "components": components,
        "summary": _summary(components),
        "errors": errors,
    }


def write_local_platform_evidence(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _component_report(component: dict[str, Any], *, options: LocalPlatformProbeOptions, runner: KubectlRunner) -> dict[str, Any]:
    namespace = str(component["namespace"])
    namespace_report = _resource_report(runner, options, "namespace", namespace, namespace="")
    services = [_resource_report(runner, options, "service", name, namespace=namespace) for name in component["services"]]
    deployments = [_workload_report(runner, options, "deployment", name, namespace=namespace) for name in component["deployments"]]
    statefulsets = [_workload_report(runner, options, "statefulset", name, namespace=namespace) for name in component["statefulsets"]]
    errors = []
    if not namespace_report["exists"]:
        errors.append(f"namespace_missing:{namespace}")
    for service in services:
        if not service["exists"]:
            errors.append(f"service_missing:{service['name']}")
    for workload in [*deployments, *statefulsets]:
        if not workload["exists"]:
            errors.append(f"{workload['kind']}_missing:{workload['name']}")
        elif not workload["ready"]:
            errors.append(f"{workload['kind']}_not_ready:{workload['name']}")
    return {
        "id": component["id"],
        "status": "ready" if not errors else "missing",
        "namespace": namespace_report,
        "services": services,
        "deployments": deployments,
        "statefulsets": statefulsets,
        "errors": errors,
    }


def _resource_report(runner: KubectlRunner, options: LocalPlatformProbeOptions, kind: str, name: str, *, namespace: str) -> dict[str, Any]:
    result = _kubectl(runner, _get_args(options, kind, name, namespace=namespace))
    payload = _json(result)
    metadata = payload.get("metadata") if isinstance(payload, dict) else {}
    return {
        "kind": kind,
        "name": name,
        "namespace": namespace,
        "exists": result.returncode == 0,
        "resource_version_present": bool(metadata.get("resourceVersion")) if isinstance(metadata, dict) else False,
        "ports": _service_ports(payload) if kind == "service" else [],
        "error": _stderr(result) if result.returncode != 0 else "",
    }


def _workload_report(runner: KubectlRunner, options: LocalPlatformProbeOptions, kind: str, name: str, *, namespace: str) -> dict[str, Any]:
    result = _kubectl(runner, _get_args(options, kind, name, namespace=namespace))
    payload = _json(result)
    spec = payload.get("spec") if isinstance(payload, dict) else {}
    status = payload.get("status") if isinstance(payload, dict) else {}
    desired = int(spec.get("replicas") or 1) if isinstance(spec, dict) else 1
    ready = int(status.get("readyReplicas") or status.get("availableReplicas") or 0) if isinstance(status, dict) else 0
    return {
        "kind": kind,
        "name": name,
        "namespace": namespace,
        "exists": result.returncode == 0,
        "ready": result.returncode == 0 and ready >= max(1, desired),
        "ready_replicas": ready,
        "desired_replicas": desired,
        "error": _stderr(result) if result.returncode != 0 else "",
    }


def _get_args(options: LocalPlatformProbeOptions, kind: str, name: str, *, namespace: str) -> list[str]:
    args = _context_args(options)
    if namespace:
        args.extend(["-n", namespace])
    return [*args, "get", kind, name, "-o", "json"]


def _context_args(options: LocalPlatformProbeOptions) -> list[str]:
    return [f"--context={options.context}"] if options.context else []


def _kubectl(runner: KubectlRunner, args: list[str]) -> subprocess.CompletedProcess[str]:
    return runner(args)


def _default_runner(options: LocalPlatformProbeOptions) -> KubectlRunner:
    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        command = [options.kubectl, *args]
        try:
            return subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        except FileNotFoundError as exc:
            return subprocess.CompletedProcess(command, 127, stdout="", stderr=str(exc))
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(command, 124, stdout=exc.stdout or "", stderr=exc.stderr or "kubectl command timed out")

    return run


def _json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _service_ports(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = payload.get("spec") if isinstance(payload, dict) else {}
    ports = spec.get("ports") if isinstance(spec, dict) else []
    return [
        {
            "name": str(item.get("name") or ""),
            "port": int(item.get("port") or 0),
            "target_port": str(item.get("targetPort") or ""),
            "node_port": int(item.get("nodePort") or 0),
        }
        for item in ports
        if isinstance(item, dict)
    ]


def _summary(components: list[dict[str, Any]]) -> dict[str, int]:
    ready = sum(1 for item in components if item.get("status") == "ready")
    return {"ready": ready, "missing": len(components) - ready, "total": len(components)}


def _stdout(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "").strip()


def _stderr(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or "").strip()[:1000]
