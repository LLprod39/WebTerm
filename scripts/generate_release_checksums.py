#!/usr/bin/env python3
"""Write SHA-256 checksums for release artifacts (SBOM, bundles, images metadata).

Produces:

- ``SHA256SUMS.txt`` — GNU coreutils compatible lines: ``<hex>  <relative-path>``
- ``checksums.json`` — machine-readable map for CI evidence

Does not sign anything; pair with ``generate_provenance.py`` for attestations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    files = [path for path in root.rglob("*") if path.is_file()]
    return sorted(files, key=lambda p: p.as_posix().lower())


def build_records(input_paths: list[Path], repo: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in input_paths:
        try:
            rel = path.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            rel = path.name
        records.append(
            {
                "path": rel,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def write_outputs(records: list[dict[str, Any]], output: Path) -> tuple[Path, Path]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        json_path = output
        text_path = output.with_name("SHA256SUMS.txt")
    else:
        text_path = output
        json_path = output.with_suffix(".json") if output.suffix else output.with_name(output.name + ".json")
        if text_path.suffix.lower() != ".txt":
            text_path = output.with_name("SHA256SUMS.txt")

    text_lines = [f"{item['sha256']}  {item['path']}" for item in records]
    text_path.write_text("\n".join(text_lines) + ("\n" if text_lines else ""), encoding="utf-8")

    payload = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "algorithm": "SHA-256",
        "files": records,
        "count": len(records),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return text_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        action="append",
        default=[],
        type=Path,
        help="Directory or file to include (repeatable). Default: .ci-artifacts/sbom",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".ci-artifacts/checksums/SHA256SUMS.txt"),
        help="Checksum output path (txt or json)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    inputs = args.input_dir or [Path(".ci-artifacts/sbom")]
    files: list[Path] = []
    for raw in inputs:
        path = raw if raw.is_absolute() else repo / raw
        files.extend(iter_files(path))
    # exclude previous checksum outputs if regenerating inside same tree
    files = [f for f in files if f.name not in {"SHA256SUMS.txt", "checksums.json"}]
    if not files:
        print("No input files found for checksums", file=sys.stderr)
        return 2
    records = build_records(files, repo)
    output = args.output if args.output.is_absolute() else repo / args.output
    text_path, json_path = write_outputs(records, output)
    print(text_path)
    print(json_path)
    print(f"Hashed {len(records)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
