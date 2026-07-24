"""Build and expose the immutable Ansible runner content manifest."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST_PATH = Path("/opt/webterm/runtime-manifest.json")
COLLECTIONS_ROOT = Path("/usr/share/ansible/collections/ansible_collections")
IDENTITY_FILES = (
    Path("/opt/webterm/runtime_metadata.py"),
    Path("/opt/webterm/validator.py"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _installed_python_packages() -> list[dict[str, str]]:
    packages: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = str(distribution.metadata.get("Name") or "").strip().lower()
        if name:
            packages[name] = str(distribution.version)
    return [{"name": name, "version": packages[name]} for name in sorted(packages)]


def _installed_collections() -> list[dict[str, str]]:
    collections: list[dict[str, str]] = []
    if not COLLECTIONS_ROOT.is_dir():
        return collections
    for manifest in sorted(COLLECTIONS_ROOT.glob("*/*/MANIFEST.json")):
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
            info = document.get("collection_info") if isinstance(document, dict) else None
            if not isinstance(info, dict):
                continue
            namespace = str(info.get("namespace") or manifest.parent.parent.name)
            name = str(info.get("name") or manifest.parent.name)
            version = str(info.get("version") or "")
            collections.append({"name": f"{namespace}.{name}", "version": version})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return collections


def _installed_os_packages() -> list[str]:
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}=${Version}\n"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def build_runtime_metadata() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "python_packages": _installed_python_packages(),
        "collections": _installed_collections(),
        "os_packages": _installed_os_packages(),
        "identity_files": {str(path): _sha256(path) for path in IDENTITY_FILES if path.is_file()},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["runtime_digest"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return payload


def load_runtime_metadata(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Ansible runtime manifest is invalid")
    recorded = str(document.get("runtime_digest") or "")
    unsigned = {key: value for key, value in document.items() if key != "runtime_digest"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if not recorded or recorded != expected:
        raise ValueError("Ansible runtime manifest digest is invalid")
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    parser.add_argument("--print", action="store_true", dest="print_manifest")
    options = parser.parse_args()
    if options.write:
        metadata = build_runtime_metadata()
        options.write.write_text(
            json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return 0
    if options.print_manifest:
        print(json.dumps(load_runtime_metadata(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
        return 0
    parser.error("one of --write or --print is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
