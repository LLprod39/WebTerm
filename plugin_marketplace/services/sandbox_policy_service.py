from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from django.conf import settings

from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.dependency_policy_service import dependency_policy_blockers
from plugin_marketplace.services.egress_policy_service import egress_policy_blockers
from plugin_marketplace.services.frontend_bundle_policy_service import frontend_bundle_policy_for_package

EXECUTABLE_SUFFIXES = (".py", ".pyc", ".pyd", ".ps1", ".bat", ".cmd", ".sh", ".exe", ".dll", ".so", ".dylib")
INSTALL_SCRIPT_NAMES = {"install.sh", "postinstall.sh", "setup.py", "manage.py"}
DEPENDENCY_MANIFEST_NAMES = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
}
DYNAMIC_RENDERERS = {"html", "javascript", "remote", "iframe", "iframe_sandbox", "web_worker"}


def sandbox_settings() -> dict[str, bool]:
    return {
        "backend_sandbox_enabled": bool(getattr(settings, "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED", False)),
        "frontend_sandbox_enabled": bool(getattr(settings, "PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED", False)),
        "allow_sandboxed_code_packages": bool(
            getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False)
        ),
    }


def _files_from_package(package: PluginPackage) -> list[dict[str, Any]]:
    sbom = package.sbom if isinstance(package.sbom, dict) else {}
    files = sbom.get("files") if isinstance(sbom.get("files"), list) else []
    return [item for item in files if isinstance(item, dict)]


def _manifest_surfaces(package: PluginPackage) -> dict[str, list[dict[str, Any]]]:
    manifest = package.manifest if isinstance(package.manifest, dict) else {}
    surfaces = manifest.get("surfaces") if isinstance(manifest.get("surfaces"), dict) else {}
    return {
        str(kind): [item for item in items if isinstance(item, dict)]
        for kind, items in surfaces.items()
        if isinstance(items, list)
    }


def _classify_files(files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    requirements: list[dict[str, Any]] = []
    blockers: list[str] = []
    for file_record in files:
        path = str(file_record.get("path") or "")
        name = PurePosixPath(path).name.lower()
        parts = PurePosixPath(path).parts
        if not path:
            continue
        if name in INSTALL_SCRIPT_NAMES:
            blockers.append(f"Install script is not allowed: {path}.")
            requirements.append({"kind": "install_script", "path": path, "supported": False})
            continue
        if name in DEPENDENCY_MANIFEST_NAMES:
            requirements.append({"kind": "dependency_manifest", "path": path, "supported": True})
        if name.endswith(EXECUTABLE_SUFFIXES):
            sandbox_kind = "frontend" if parts and parts[0] == "frontend" else "backend"
            requirements.append({"kind": f"{sandbox_kind}_code", "path": path, "supported": True})
    return requirements, blockers


def _classify_surfaces(surfaces: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[str]]:
    requirements: list[dict[str, Any]] = []
    blockers: list[str] = []
    for kind, items in surfaces.items():
        for index, item in enumerate(items):
            renderer = str(item.get("renderer") or "").lower()
            if renderer in DYNAMIC_RENDERERS:
                requirements.append(
                    {
                        "kind": "frontend_dynamic_renderer",
                        "surface": kind,
                        "index": index,
                        "renderer": renderer,
                        "supported": True,
                    }
                )
            executor_ref = str(item.get("executor_ref") or item.get("executor") or "").strip()
            if executor_ref and not executor_ref.startswith("plugin_marketplace.demo."):
                requirements.append(
                    {
                        "kind": "backend_executor",
                        "surface": kind,
                        "index": index,
                        "executor_ref": executor_ref,
                        "supported": True,
                    }
                )
    return requirements, blockers


def sandbox_policy_for_package(package: PluginPackage) -> dict[str, Any]:
    current = sandbox_settings()
    manifest = package.manifest if isinstance(package.manifest, dict) else {}
    files = _files_from_package(package)
    file_requirements, file_blockers = _classify_files(files)
    surface_requirements, surface_blockers = _classify_surfaces(_manifest_surfaces(package))
    requirements = file_requirements + surface_requirements
    blockers = file_blockers + surface_blockers
    blockers.extend(egress_policy_blockers(manifest))
    frontend_bundle_policy = frontend_bundle_policy_for_package(package)
    blockers.extend(f"Frontend bundle policy: {item}" for item in frontend_bundle_policy["blockers"])
    requires_backend = any(str(item.get("kind", "")).startswith("backend") for item in requirements)
    requires_frontend = any(str(item.get("kind", "")).startswith("frontend") for item in requirements) or bool(
        frontend_bundle_policy["required"]
    )
    if (requires_backend or requires_frontend) and not current["allow_sandboxed_code_packages"]:
        blockers.append("Sandboxed code packages are not allowed by policy.")
    if requires_backend and not current["backend_sandbox_enabled"]:
        blockers.append("Backend sandbox runtime is not enabled.")
    if requires_frontend and not current["frontend_sandbox_enabled"]:
        blockers.append("Frontend sandbox runtime is not enabled.")
    dependency_scan = package.dependency_scan if isinstance(package.dependency_scan, dict) else {}
    scan_blockers = dependency_scan.get("blockers") if isinstance(dependency_scan.get("blockers"), list) else []
    if scan_blockers:
        for blocker in scan_blockers:
            code = str(blocker.get("code") or "dependency_policy_blocker")
            detail = str(blocker.get("dependency") or blocker.get("path") or blocker.get("source") or "").strip()
            blockers.append(f"Dependency policy {code}: {detail}".rstrip(": "))
    else:
        sbom = package.sbom if isinstance(package.sbom, dict) else {}
        dependencies = sbom.get("components") if isinstance(sbom.get("components"), list) else []
        dependency_manifests = (
            sbom.get("dependency_manifests") if isinstance(sbom.get("dependency_manifests"), list) else []
        )
        for blocker in dependency_policy_blockers(
            dependencies=[item for item in dependencies if isinstance(item, dict)],
            dependency_manifests=[item for item in dependency_manifests if isinstance(item, dict)],
            allow_sandboxed_code=current["allow_sandboxed_code_packages"],
        ):
            code = str(blocker.get("code") or "dependency_policy_blocker")
            detail = str(blocker.get("dependency") or blocker.get("path") or blocker.get("source") or "").strip()
            blockers.append(f"Dependency policy {code}: {detail}".rstrip(": "))
    return {
        "required": bool(requirements),
        "requires_backend_sandbox": requires_backend,
        "requires_frontend_sandbox": requires_frontend,
        "settings": current,
        "requirements": requirements,
        "frontend_bundle_policy": frontend_bundle_policy,
        "blockers": blockers,
        "allowed": not blockers,
    }


def sandbox_enable_blockers(package: PluginPackage) -> list[str]:
    return [f"Sandbox policy: {item}" for item in sandbox_policy_for_package(package)["blockers"]]
