#!/usr/bin/env python3
"""Verify the canonical WebTerm brand and synchronized public version."""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.2.0"
TEXT_SUFFIXES = {
    ".css",
    ".example",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
FORBIDDEN_DISPLAY_BRANDS = ("WebTermAI", "WEU AI")
LEGACY_DISPLAY = "WebTrerm"
LEGACY_LINE_TOKENS = (
    "C:\\WebTrerm",
    "C:\\\\WebTrerm",
    "C:/WebTrerm",
    "/mnt/c/WebTrerm",
    "WebTrermPluginBundle",
)
BRAND_COMPATIBILITY_DOC = "docs/releases/BRAND_COMPATIBILITY.md"
VERIFIER_PATH = "scripts/verify_release_identity.py"


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _tracked_text_files(root: Path) -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    paths: list[Path] = []
    for raw in output.decode("utf-8").split("\0"):
        if not raw:
            continue
        path = Path(raw)
        if path.as_posix() in {BRAND_COMPATIBILITY_DOC, VERIFIER_PATH}:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name.endswith("Dockerfile"):
            paths.append(path)
    return paths


def _version_errors(root: Path) -> list[str]:
    errors: list[str] = []
    version = _read(root, "VERSION").strip()
    if version != EXPECTED_VERSION:
        errors.append(f"VERSION must be {EXPECTED_VERSION}, got {version!r}")

    pyproject = tomllib.loads(_read(root, "pyproject.toml"))
    project = pyproject.get("project", {})
    if project.get("name") != "webterm":
        errors.append("pyproject project name must be webterm")
    if project.get("version") != version:
        errors.append("pyproject version does not match VERSION")

    package = json.loads(_read(root, "frontend/package.json"))
    package_lock = json.loads(_read(root, "frontend/package-lock.json"))
    if package.get("version") != version:
        errors.append("frontend/package.json version does not match VERSION")
    if package_lock.get("version") != version:
        errors.append("frontend/package-lock.json version does not match VERSION")
    if package_lock.get("packages", {}).get("", {}).get("version") != version:
        errors.append("frontend lockfile root package version does not match VERSION")

    for relative in ("docker/backend.Dockerfile", "docker/frontend.Dockerfile"):
        dockerfile = _read(root, relative)
        if f"ARG WEBTERM_VERSION={version}" not in dockerfile:
            errors.append(f"{relative} does not declare WEBTERM_VERSION={version}")
        if "org.opencontainers.image.version=${WEBTERM_VERSION}" not in dockerfile:
            errors.append(f"{relative} does not label the container version")

    public_api = json.loads(_read(root, "config/public-api-v0.1.json"))
    if public_api.get("version") != "0.1.0":
        errors.append("public API v0.1 inventory must remain version 0.1.0")
    return errors


def _brand_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in _tracked_text_files(root):
        try:
            text = _read(root, relative.as_posix())
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for old_brand in FORBIDDEN_DISPLAY_BRANDS:
                if old_brand in line:
                    errors.append(f"legacy display brand {old_brand!r}: {relative.as_posix()}:{line_number}")
            if LEGACY_DISPLAY not in line:
                continue
            remaining = line
            for token in LEGACY_LINE_TOKENS:
                remaining = remaining.replace(token, "")
            if LEGACY_DISPLAY in remaining:
                errors.append(f"legacy display brand {LEGACY_DISPLAY!r}: {relative.as_posix()}:{line_number}")
    return errors


def verify(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        errors.extend(_version_errors(root))
    except (FileNotFoundError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"release identity file is missing or invalid: {exc}")
    try:
        errors.extend(_brand_errors(root))
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        errors.append(f"cannot inspect tracked brand files: {exc}")
    return errors


def main() -> int:
    errors = verify(ROOT)
    if errors:
        print("Release identity: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Release identity: PASS (WebTerm {EXPECTED_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
