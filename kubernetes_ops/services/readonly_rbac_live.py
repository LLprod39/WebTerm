from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from kubernetes_ops.services.readonly_rbac import READONLY_SERVICE_ACCOUNT_CONTRACT

KubectlRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

ALLOWED_CAN_I_CHECKS: tuple[tuple[str, str, bool], ...] = (
    ("get", "namespaces", False),
    ("list", "pods", True),
    ("watch", "pods", True),
    ("get", "services", True),
    ("list", "deployments.apps", True),
    ("get", "ingresses.networking.k8s.io", True),
    ("list", "events", True),
)

DENIED_CAN_I_CHECKS: tuple[tuple[str, str, bool], ...] = (
    ("create", "pods", True),
    ("delete", "pods", True),
    ("patch", "deployments.apps", True),
    ("create", "pods/exec", True),
    ("create", "pods/attach", True),
    ("create", "pods/portforward", True),
    ("escalate", "clusterroles.rbac.authorization.k8s.io", False),
)


@dataclass(frozen=True)
class KubectlProbeOptions:
    manifest_path: Path
    apply_manifest: bool = False
    context: str = ""
    kubectl: str = "kubectl"
    service_account_namespace: str = READONLY_SERVICE_ACCOUNT_CONTRACT["namespace"]
    service_account_name: str = READONLY_SERVICE_ACCOUNT_CONTRACT["name"]
    probe_namespace: str = "default"


def verify_kubernetes_readonly_rbac_live(
    options: KubectlProbeOptions,
    *,
    runner: KubectlRunner | None = None,
) -> dict[str, Any]:
    runner = runner or _default_runner(options)
    errors: list[str] = []
    applied = False
    subject = f"system:serviceaccount:{options.service_account_namespace}:{options.service_account_name}"

    context_result = _kubectl(runner, ["config", "current-context"])
    context = options.context or _stdout(context_result)
    if context_result.returncode != 0:
        errors.append("kubectl_context_unavailable:" + _stderr(context_result))

    if not options.manifest_path.exists():
        errors.append(f"manifest_missing:{options.manifest_path}")
    elif options.apply_manifest:
        apply_result = _kubectl(runner, _context_args(options) + ["apply", "-f", str(options.manifest_path)])
        applied = apply_result.returncode == 0
        if apply_result.returncode != 0:
            errors.append("kubectl_apply_failed:" + _stderr(apply_result))

    allowed = [_can_i(runner, options, subject, verb, resource, namespaced) for verb, resource, namespaced in ALLOWED_CAN_I_CHECKS]
    denied = [_can_i(runner, options, subject, verb, resource, namespaced) for verb, resource, namespaced in DENIED_CAN_I_CHECKS]
    errors.extend(_can_i_errors(allowed, expected=True))
    errors.extend(_can_i_errors(denied, expected=False))

    return {
        "status": "ready" if not errors else "missing",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "kubectl": options.kubectl,
        "manifest_path": str(options.manifest_path),
        "applied": applied,
        "service_account": subject,
        "probe_namespace": options.probe_namespace,
        "allowed": allowed,
        "denied": denied,
        "errors": errors,
    }


def write_live_rbac_evidence(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _can_i(runner: KubectlRunner, options: KubectlProbeOptions, subject: str, verb: str, resource: str, namespaced: bool) -> dict[str, Any]:
    args = _context_args(options) + ["auth", "can-i", verb, resource, f"--as={subject}"]
    if namespaced:
        args.append(f"--namespace={options.probe_namespace}")
    result = _kubectl(runner, args)
    decision = _stdout(result).lower()
    allowed = decision == "yes"
    return {
        "verb": verb,
        "resource": resource,
        "namespaced": namespaced,
        "allowed": allowed,
        "decision": decision if decision in {"yes", "no"} else "unknown",
        "returncode": result.returncode,
        "stdout": _stdout(result),
        "stderr": _stderr(result),
    }


def _can_i_errors(items: list[dict[str, Any]], *, expected: bool) -> list[str]:
    errors: list[str] = []
    for item in items:
        if item.get("decision") in {"yes", "no"}:
            if bool(item["allowed"]) is not expected:
                prefix = "missing_allowed" if expected else "unexpected_allowed"
                errors.append(f"{prefix}:{item['verb']}:{item['resource']}")
        elif item["returncode"] != 0:
            errors.append(f"can_i_error:{item['verb']}:{item['resource']}:{item['stderr']}")
        elif bool(item["allowed"]) is not expected:
            prefix = "missing_allowed" if expected else "unexpected_allowed"
            errors.append(f"{prefix}:{item['verb']}:{item['resource']}")
    return errors


def _context_args(options: KubectlProbeOptions) -> list[str]:
    return [f"--context={options.context}"] if options.context else []


def _kubectl(runner: KubectlRunner, args: list[str]) -> subprocess.CompletedProcess[str]:
    return runner(args)


def _default_runner(options: KubectlProbeOptions) -> KubectlRunner:
    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        command = [options.kubectl, *args]
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)

    return run


def _stdout(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "").strip()


def _stderr(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or "").strip()
