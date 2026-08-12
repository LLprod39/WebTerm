#!/usr/bin/env python3
"""Generate CycloneDX SBOMs for backend, frontend, and container Dockerfile inventory.

Prefers external generators when available:

- Python: ``cyclonedx-py`` / ``cyclonedx-bom`` (optional)
- npm: ``npx @cyclonedx/cyclonedx-npm`` (optional)

Falls back to a pure-stdlib CycloneDX 1.5 document built from lockfiles so CI and
local Stage 1 gates remain hermetic without global tool installs.

Container layer SBOMs (Syft/Trivy) are optional via ``--image``:

- Always emits a Dockerfile inventory document
- When ``--image`` is set and Syft (or Trivy) is on PATH, writes
  ``sbom-image-<safe-name>.cdx.json`` per reference
- When tools are missing, writes a ``IMAGE_SBOM_PENDING.md`` note instead of failing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.5"
TOOL_NAME = "webterm-generate-sbom"
TOOL_VERSION = "1.0.0"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root_from(script: Path) -> Path:
    return script.resolve().parents[1]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bom_ref(name: str, version: str) -> str:
    return f"pkg:generic/{name}@{version}"


def component(
    *,
    name: str,
    version: str,
    purl: str | None = None,
    component_type: str = "library",
    hashes: list[dict[str, str]] | None = None,
    properties: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": component_type,
        "name": name,
        "version": version,
        "bom-ref": purl or bom_ref(name, version),
    }
    if purl:
        item["purl"] = purl
    if hashes:
        item["hashes"] = hashes
    if properties:
        item["properties"] = properties
    return item


def base_bom(*, name: str, version: str, components: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": SCHEMA_VERSION,
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": utc_now(),
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": TOOL_NAME,
                        "version": TOOL_VERSION,
                    }
                ]
            },
            "component": {
                "type": "application",
                "name": name,
                "version": version,
                "bom-ref": f"pkg:generic/{name}@{version}",
            },
        },
        "components": components,
    }


_REQ_LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\\\s#]+)"
    r"(?:\s*\\)?(?:\s*--hash=(?P<algo>sha256):(?P<digest>[A-Fa-f0-9]+))?"
)


def parse_requirements_lock(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    components: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        if line.startswith("--"):
            # Continuation hash lines: --hash=sha256:...
            if current and line.startswith("--hash=sha256:"):
                digest = line.split("sha256:", 1)[1].strip()
                current.setdefault("hashes", []).append({"alg": "SHA-256", "content": digest})
            continue
        match = _REQ_LINE.match(line.replace("\\", "").strip())
        if not match:
            continue
        name = match.group("name")
        version = match.group("version")
        purl = f"pkg:pypi/{name.lower()}@{version}"
        current = component(name=name, version=version, purl=purl)
        if match.group("digest"):
            current["hashes"] = [{"alg": "SHA-256", "content": match.group("digest")}]
        components.append(current)
    # de-dupe by purl keeping first
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in components:
        ref = item["bom-ref"]
        if ref in seen:
            continue
        seen.add(ref)
        unique.append(item)
    return unique


def parse_package_lock(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    packages = data.get("packages")
    if not isinstance(packages, dict):
        return []
    components: list[dict[str, Any]] = []
    for key, meta in packages.items():
        if not isinstance(meta, dict):
            continue
        if key in ("", None):
            continue
        name = meta.get("name")
        if not name:
            # node_modules/@scope/pkg → @scope/pkg
            name = key.removeprefix("node_modules/")
        version = meta.get("version")
        if not isinstance(name, str) or not isinstance(version, str) or not version:
            continue
        if meta.get("dev") and meta.get("optional"):
            # still include; inventory should be complete for release scope
            pass
        # CycloneDX npm purl uses name as-is with @scope
        purl = f"pkg:npm/{name}@{version}"
        integrity = meta.get("integrity")
        hashes = None
        if isinstance(integrity, str) and integrity.startswith("sha512-"):
            hashes = [{"alg": "SHA-512", "content": integrity.removeprefix("sha512-")}]
        components.append(
            component(
                name=name,
                version=version,
                purl=purl,
                hashes=hashes,
                properties=[{"name": "webterm:lock_path", "value": key}],
            )
        )
    return components


def list_dockerfiles(repo: Path) -> list[dict[str, Any]]:
    docker_dir = repo / "docker"
    components: list[dict[str, Any]] = []
    paths = sorted(docker_dir.glob("*.Dockerfile")) if docker_dir.is_dir() else []
    paths += sorted(docker_dir.glob("**/Dockerfile")) if docker_dir.is_dir() else []
    compose_paths = (repo / "docker-compose.yml", repo / "docker-compose.production.yml")
    for path in paths:
        rel = path.relative_to(repo).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        version = sha256_text(text)[:12]
        components.append(
            component(
                name=rel,
                version=version,
                component_type="file",
                purl=f"pkg:generic/dockerfile/{rel.replace('/', '.')}@{version}",
                hashes=[{"alg": "SHA-256", "content": sha256_text(text)}],
                properties=[{"name": "webterm:artifact_kind", "value": "dockerfile"}],
            )
        )
    for compose in compose_paths:
        if not compose.is_file():
            continue
        text = compose.read_text(encoding="utf-8", errors="replace")
        version = sha256_text(text)[:12]
        relative = compose.relative_to(repo).as_posix()
        components.append(
            component(
                name=relative,
                version=version,
                component_type="file",
                purl=f"pkg:generic/compose/{relative.replace('/', '.')}@{version}",
                hashes=[{"alg": "SHA-256", "content": sha256_text(text)}],
                properties=[{"name": "webterm:artifact_kind", "value": "compose"}],
            )
        )
    return components


def try_external_python_sbom(repo: Path, output: Path) -> bool:
    candidates = [
        [sys.executable, "-m", "cyclonedx_py", "environment", "-o", str(output)],
        [sys.executable, "-m", "cyclonedx_py", "requirements", str(repo / "requirements-dev.lock"), "-o", str(output)],
    ]
    for cmd in candidates:
        try:
            result = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, encoding="utf-8", check=False)
        except OSError:
            continue
        if result.returncode == 0 and output.is_file() and output.stat().st_size > 0:
            return True
    return False


def try_external_npm_sbom(repo: Path, output: Path) -> bool:
    frontend = repo / "frontend"
    if not (frontend / "package-lock.json").is_file():
        return False
    npx = shutil.which("npx")
    if not npx:
        return False
    cmd = [
        npx,
        "--yes",
        "@cyclonedx/cyclonedx-npm@1.19.3",
        "--output-file",
        str(output),
        "--output-format",
        "JSON",
        "--ignore-npm-errors",
    ]
    result = subprocess.run(cmd, cwd=frontend, capture_output=True, text=True, encoding="utf-8", check=False)
    return result.returncode == 0 and output.is_file() and output.stat().st_size > 0


def safe_image_filename(image_ref: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", image_ref.strip())
    cleaned = cleaned.strip("._-") or "image"
    return cleaned[:120]


def try_syft_image_sbom(image: str, output: Path) -> bool:
    syft = shutil.which("syft")
    if not syft:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [syft, image, "-o", f"cyclonedx-json={output}"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    return result.returncode == 0 and output.is_file() and output.stat().st_size > 0


def try_trivy_image_sbom(image: str, output: Path) -> bool:
    trivy = shutil.which("trivy")
    if not trivy:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        trivy,
        "image",
        "--quiet",
        "--format",
        "cyclonedx",
        "--output",
        str(output),
        image,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    return result.returncode == 0 and output.is_file() and output.stat().st_size > 0


def generate_image_sboms(output_dir: Path, images: list[str]) -> list[Path]:
    if not images:
        return []
    written: list[Path] = []
    pending: list[str] = []
    for image in images:
        image = image.strip()
        if not image:
            continue
        out = output_dir / f"sbom-image-{safe_image_filename(image)}.cdx.json"
        if try_syft_image_sbom(image, out) or try_trivy_image_sbom(image, out):
            written.append(out)
            continue
        pending.append(image)
    if pending:
        note = output_dir / "IMAGE_SBOM_PENDING.md"
        lines = [
            "# Image-layer SBOM pending",
            "",
            "The following image references were requested but Syft/Trivy was unavailable",
            "or failed. Install Syft (`curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh`)",
            "or Trivy, then re-run with `--image <ref>` against an **immutable digest**.",
            "",
        ]
        for image in pending:
            lines.append(f"- `{image}`")
        lines.extend(
            [
                "",
                "```bash",
                "syft <image>@sha256:<digest> -o cyclonedx-json=sbom-image.cdx.json",
                "```",
                "",
            ]
        )
        note.write_text("\n".join(lines), encoding="utf-8")
        written.append(note)
    return written


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate(
    repo: Path,
    output_dir: Path,
    *,
    prefer_external: bool,
    images: list[str] | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    backend_path = output_dir / "sbom-backend.cdx.json"
    if not (prefer_external and try_external_python_sbom(repo, backend_path)):
        comps = parse_requirements_lock(repo / "requirements-dev.lock")
        if not comps:
            comps = parse_requirements_lock(repo / "requirements-mini.txt")
        write_json(backend_path, base_bom(name="webterm-backend", version="0.0.0-dev", components=comps))
    written.append(backend_path)

    for artifact_name, component_name, lock_path in (
        ("sbom-ai-cli-manager.cdx.json", "webterm-ai-cli-manager", "ai_cli_runner_manager/requirements.lock"),
        (
            "sbom-ai-cli-provider.cdx.json",
            "webterm-ai-cli-provider",
            "ai_cli_runner_manager/provider-requirements.lock",
        ),
    ):
        artifact_path = output_dir / artifact_name
        components = parse_requirements_lock(repo / lock_path)
        write_json(
            artifact_path,
            base_bom(name=component_name, version="0.0.0-dev", components=components),
        )
        written.append(artifact_path)

    frontend_path = output_dir / "sbom-frontend.cdx.json"
    if not (prefer_external and try_external_npm_sbom(repo, frontend_path)):
        comps = parse_package_lock(repo / "frontend" / "package-lock.json")
        write_json(frontend_path, base_bom(name="webterm-frontend", version="0.0.0-dev", components=comps))
    written.append(frontend_path)

    containers_path = output_dir / "sbom-containers.cdx.json"
    write_json(
        containers_path,
        base_bom(
            name="webterm-containers-inventory",
            version="0.0.0-dev",
            components=list_dockerfiles(repo),
        ),
    )
    written.append(containers_path)

    readme = output_dir / "CONTAINERS_SBOM.md"
    readme.write_text(
        "\n".join(
            [
                "# Container SBOM notes",
                "",
                "`sbom-containers.cdx.json` inventories Dockerfiles and compose inputs",
                "with content hashes. For a published release image, generate a full",
                "layer SBOM with Syft or Trivy against the immutable image digest:",
                "",
                "```bash",
                "python scripts/generate_sbom.py --output-dir .ci-artifacts/sbom \\",
                "  --image ghcr.io/org/webterm-backend@sha256:<digest>",
                "# or:",
                "syft <image>@sha256:<digest> -o cyclonedx-json=sbom-image.cdx.json",
                "```",
                "",
                "Attach image SBOMs to the release evidence bundle alongside checksums",
                "and provenance. CI may pass `IMAGE_SBOM_REFS` (comma-separated) on release jobs.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written.append(readme)
    written.extend(generate_image_sboms(output_dir, images or []))
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".ci-artifacts/sbom"),
        help="Directory for CycloneDX JSON outputs",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--prefer-external",
        action="store_true",
        help="Try cyclonedx-py / cyclonedx-npm before lockfile fallback",
    )
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Container image ref for layer SBOM via Syft/Trivy (repeatable)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = (args.repo_root or repo_root_from(Path(__file__))).resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    paths = generate(
        repo,
        output_dir,
        prefer_external=args.prefer_external,
        images=list(args.image or []),
    )
    for path in paths:
        print(path)
    print(f"Generated {len(paths)} SBOM artifacts under {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
