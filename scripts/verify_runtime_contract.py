#!/usr/bin/env python3
"""Verify that every supported entry point uses the frozen WebTerm toolchain."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_RANGE = ">=3.11,<3.13"
PYTHON_IMAGE = "python:3.11.15-slim-bookworm"
NODE_VERSION = "22.23.1"
NPM_VERSION = "10.9.8"
NODE_IMAGE = f"node:{NODE_VERSION}-bookworm-slim"
DEV_TOOLS = {"coverage", "import-linter", "pre-commit", "pytest", "pytest-cov", "pytest-django", "ruff"}
RUNTIME_FORBIDDEN = DEV_TOOLS | {"pytest-asyncio", "tomli"}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _locked_versions(text: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for match in re.finditer(r"(?m)^([A-Za-z0-9_.-]+)==([^ \\\r\n]+)", text):
        versions[match.group(1).lower().replace("_", "-")] = match.group(2)
    return versions


def verify(root: Path = ROOT) -> list[str]:
    global ROOT
    previous_root = ROOT
    ROOT = root
    errors: list[str] = []
    try:
        pyproject = tomllib.loads(_read("pyproject.toml"))
        if pyproject.get("project", {}).get("requires-python") != PYTHON_RANGE:
            errors.append(f"pyproject.toml must require Python {PYTHON_RANGE}")
        if pyproject.get("tool", {}).get("ruff", {}).get("target-version") != "py311":
            errors.append("Ruff target-version must be py311")

        runtime_input = _read("requirements-mini.txt")
        runtime_lock_text = _read("requirements.lock")
        dev_input = _read("requirements-dev.in")
        dev_lock_text = _read("requirements-dev.lock")
        runtime_lock = _locked_versions(runtime_lock_text)
        dev_lock = _locked_versions(dev_lock_text)

        if runtime_lock.get("django") != "5.2.16":
            errors.append("requirements.lock must freeze Django 5.2.16")
        if "-c requirements.lock" not in dev_input:
            errors.append("requirements-dev.in must constrain the runtime with requirements.lock")
        for package, version in runtime_lock.items():
            if dev_lock.get(package) != version:
                errors.append(f"dev lock runtime mismatch: {package} {version} != {dev_lock.get(package)}")
        missing_dev = sorted(DEV_TOOLS - dev_lock.keys())
        if missing_dev:
            errors.append(f"requirements-dev.lock is missing tools: {', '.join(missing_dev)}")
        runtime_names = set(_locked_versions(runtime_lock_text))
        forbidden_lock = sorted(runtime_names & RUNTIME_FORBIDDEN)
        if forbidden_lock:
            errors.append(f"production lock contains development tools: {', '.join(forbidden_lock)}")
        for package in RUNTIME_FORBIDDEN:
            if re.search(rf"(?mi)^\s*{re.escape(package)}(?:\[.*?\])?\s*(?:[<>=!~]|$)", runtime_input):
                errors.append(f"requirements-mini.txt contains development tool {package}")

        package_json = json.loads(_read("frontend/package.json"))
        if package_json.get("packageManager") != f"npm@{NPM_VERSION}":
            errors.append(f"frontend packageManager must be npm@{NPM_VERSION}")
        engines = package_json.get("engines", {})
        if engines != {"node": NODE_VERSION, "npm": NPM_VERSION}:
            errors.append("frontend engines must exactly pin the supported Node and npm versions")
        lock_json = json.loads(_read("frontend/package-lock.json"))
        if lock_json.get("packages", {}).get("", {}).get("engines") != engines:
            errors.append("frontend/package-lock.json root engines do not match package.json")
        if _read(".nvmrc").strip() != NODE_VERSION:
            errors.append(f".nvmrc must contain {NODE_VERSION}")
        if _read(".python-version").strip() != "3.11":
            errors.append(".python-version must select Python 3.11")

        backend_docker = _read("docker/backend.Dockerfile")
        frontend_docker = _read("docker/frontend.Dockerfile")
        workflow = _read(".github/workflows/playwright-smoke.yml")
        if not backend_docker.startswith(f"FROM {PYTHON_IMAGE} AS builder\n"):
            errors.append(f"backend builder image must start from {PYTHON_IMAGE}")
        if f"FROM {PYTHON_IMAGE} AS runtime\n" not in backend_docker:
            errors.append(f"backend runtime image must use {PYTHON_IMAGE}")
        if not frontend_docker.startswith(f"FROM {NODE_IMAGE}\n"):
            errors.append(f"frontend image must start from {NODE_IMAGE}")
        if f'node-version: "{NODE_VERSION}"' not in workflow:
            errors.append("Playwright workflow does not use the pinned Node version")

        bootstrap = _read("bootstrap-linux.sh")
        readme = _read("README.md")
        for required in (".venv-wsl", "requirements-dev.lock", "--require-hashes", "npm ci"):
            if required not in bootstrap:
                errors.append(f"bootstrap-linux.sh is missing canonical token: {required}")
            if required not in readme:
                errors.append(f"README.md is missing canonical token: {required}")
        if ".venv-windows" not in _read("scripts/start-backend-windows.ps1"):
            errors.append("native Windows helper must use a separate .venv-windows environment")
    finally:
        ROOT = previous_root
    return errors


def main() -> int:
    errors = verify(ROOT)
    if errors:
        print("Runtime contract: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Runtime contract: PASS")
    print(f"Python {PYTHON_RANGE}; Django 5.2.16; Node {NODE_VERSION}; npm {NPM_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
