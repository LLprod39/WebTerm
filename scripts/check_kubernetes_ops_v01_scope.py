#!/usr/bin/env python3
"""Enforce the frozen read-only Kubernetes Ops v0.1 product boundary."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "kubernetes-ops-v0.1-scope.json"
URLS_PATH = ROOT / "kubernetes_ops" / "urls.py"
RUNTIME_SETTINGS_PATH = ROOT / "web_ui" / "settings" / "runtime_services.py"
PERMISSIONS_PATH = ROOT / "kubernetes_ops" / "permissions.py"
PRODUCTION_ENV_PATH = ROOT / ".env.production.example"
SCOPE_DOC_PATH = ROOT / "docs" / "architecture" / "KUBERNETES_OPS_V01_SCOPE.md"
CODEOWNERS_PATH = ROOT / ".github" / "CODEOWNERS"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "architecture-fitness.yml"


def _constant(value: ast.AST | None) -> Any:
    return value.value if isinstance(value, ast.Constant) else None


def route_surface() -> list[dict[str, str]]:
    tree = ast.parse(URLS_PATH.read_text(encoding="utf-8"), filename=str(URLS_PATH))
    routes: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "path":
            continue
        route = _constant(node.args[0]) if node.args else None
        name = next((_constant(item.value) for item in node.keywords if item.arg == "name"), None)
        if not isinstance(route, str) or not isinstance(name, str):
            raise RuntimeError(f"Kubernetes URL path at line {node.lineno} must use literal route and name values")
        routes.append({"name": name, "route": route})
    return sorted(routes, key=lambda item: (item["route"], item["name"]))


def route_digest(routes: list[dict[str, str]]) -> str:
    canonical = json.dumps(routes, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def env_bool_defaults() -> dict[str, bool]:
    tree = ast.parse(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"), filename=str(RUNTIME_SETTINGS_PATH))
    defaults: dict[str, bool] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "env_bool":
            continue
        if len(node.args) < 2:
            continue
        name = _constant(node.args[0])
        default = _constant(node.args[1])
        if isinstance(name, str) and isinstance(default, bool):
            defaults[name] = default
    return defaults


def permission_fallbacks() -> dict[str, bool]:
    tree = ast.parse(PERMISSIONS_PATH.read_text(encoding="utf-8"), filename=str(PERMISSIONS_PATH))
    fallbacks: dict[str, bool] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "getattr":
            continue
        if len(node.args) < 3:
            continue
        owner = node.args[0]
        name = _constant(node.args[1])
        fallback = _constant(node.args[2])
        if (
            isinstance(owner, ast.Name)
            and owner.id == "settings"
            and isinstance(name, str)
            and isinstance(fallback, bool)
        ):
            fallbacks[name] = fallback
    return fallbacks


def blocked_capabilities() -> set[str]:
    tree = ast.parse(PERMISSIONS_PATH.read_text(encoding="utf-8"), filename=str(PERMISSIONS_PATH))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "BLOCKED_CAPABILITIES" for target in node.targets):
            continue
        if not isinstance(node.value, (ast.Tuple, ast.List)):
            break
        return {value for item in node.value.elts if isinstance((value := _constant(item)), str)}
    raise RuntimeError("BLOCKED_CAPABILITIES must be a literal tuple/list")


def production_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in PRODUCTION_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def check_scope(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    routes = route_surface()
    if manifest.get("decision") != "frozen-read-only":
        errors.append("manifest decision must remain frozen-read-only")
    if manifest.get("owner") != "@LLprod39":
        errors.append("manifest owner must be @LLprod39")
    if manifest.get("route_count") != len(routes):
        errors.append(f"route surface changed: expected {manifest.get('route_count')}, found {len(routes)}")
    current_digest = route_digest(routes)
    if manifest.get("route_sha256") != current_digest:
        errors.append(f"route surface digest changed: expected {manifest.get('route_sha256')}, found {current_digest}")

    defaults = env_bool_defaults()
    fallbacks = permission_fallbacks()
    prod_values = production_env()
    for setting_name in manifest.get("runtime_default_false", []):
        if defaults.get(setting_name) is not False:
            errors.append(f"{setting_name} must be declared with a false runtime default")
        if prod_values.get(setting_name, "").lower() != "false":
            errors.append(f"{setting_name} must be false in .env.production.example")
    for setting_name in manifest.get("permission_fallback_false", []):
        if fallbacks.get(setting_name) is not False:
            errors.append(f"{setting_name} permission fallback must be false")

    blocked = blocked_capabilities()
    for capability in manifest.get("blocked_capabilities", []):
        if capability not in blocked:
            errors.append(f"blocked capability removed from fail-closed policy: {capability}")

    scope_doc = SCOPE_DOC_PATH.read_text(encoding="utf-8")
    if "Status: **frozen-read-only for v0.1**" not in scope_doc:
        errors.append("Kubernetes v0.1 scope document no longer declares frozen-read-only status")
    if "/kubernetes_ops/ @LLprod39" not in CODEOWNERS_PATH.read_text(encoding="utf-8"):
        errors.append("CODEOWNERS must assign the complete kubernetes_ops package")
    if "python scripts/check_kubernetes_ops_v01_scope.py" not in CI_WORKFLOW_PATH.read_text(encoding="utf-8"):
        errors.append("architecture CI must run the Kubernetes v0.1 scope check")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-route-snapshot", action="store_true")
    args = parser.parse_args()
    routes = route_surface()
    if args.print_route_snapshot:
        print(json.dumps({"route_count": len(routes), "route_sha256": route_digest(routes)}, indent=2))
        return 0

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        errors = check_scope(manifest)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        errors = [f"scope check could not run: {exc}"]
    if errors:
        print("Kubernetes Ops v0.1 scope: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Kubernetes Ops v0.1 scope: PASS ({len(routes)} frozen routes, read-only defaults enforced)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
