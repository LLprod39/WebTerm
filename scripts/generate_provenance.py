#!/usr/bin/env python3
"""Generate a SLSA-inspired provenance attestation for release artifacts.

Outputs an in-toto Statement (JSON) with a SLSA Provenance v1 predicate *shape*.

Signature status values:

- ``unsigned_scaffold`` — local/dev default; inventory only
- ``github_attestation_pending`` — statement ready for ``actions/attest-build-provenance``
- ``github_attestation`` — CI recorded a GitHub artifact attestation (see sidecar)

GitHub Actions signs subjects via OIDC + Sigstore (``actions/attest-build-provenance``).
Local runs remain unsigned unless ``--signature-status`` is overridden after external signing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VALID_SIGNATURE_STATUSES = frozenset(
    {
        "unsigned_scaffold",
        "github_attestation_pending",
        "github_attestation",
        "cosign_signed",
    }
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    return sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix().lower())


def subject_for(path: Path, repo: Path) -> dict[str, Any]:
    try:
        name = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        name = path.name
    return {
        "name": name,
        "digest": {"sha256": sha256_file(path)},
    }


def notes_for_status(signature_status: str) -> str:
    if signature_status == "github_attestation":
        return (
            "Subjects are signed via GitHub artifact attestations (Sigstore). "
            "Verify with: gh attestation verify <path> --repo <owner/repo>"
        )
    if signature_status == "github_attestation_pending":
        return "Statement inventory ready for GitHub Actions actions/attest-build-provenance (OIDC + Sigstore)."
    if signature_status == "cosign_signed":
        return "Subjects signed with cosign; verify with cosign verify-blob / verify-attestation."
    return (
        "Unsigned Stage 1 scaffold. CI security workflow attaches a GitHub "
        "artifact attestation for the same subjects before release evidence is trusted."
    )


def build_statement(
    *,
    repo: Path,
    subjects: list[dict[str, Any]],
    build_invocation_id: str | None,
    builder_id: str,
    signature_status: str,
    attestation_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    commit = git(repo, "rev-parse", "HEAD") or "unknown"
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    remote = git(repo, "config", "--get", "remote.origin.url") or ""
    internal: dict[str, Any] = {
        "generator": "scripts/generate_provenance.py",
        "signature_status": signature_status,
    }
    if attestation_meta:
        internal["attestation"] = attestation_meta
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://webterm.local/stage1/sbom-and-checksums@v1",
                "externalParameters": {
                    "repository": remote,
                    "ref": branch,
                    "commit": commit,
                },
                "internalParameters": internal,
                "resolvedDependencies": [],
            },
            "runDetails": {
                "builder": {"id": builder_id},
                "metadata": {
                    "invocationId": build_invocation_id or f"local-{commit[:12]}-{utc_now()}",
                    "startedOn": utc_now(),
                    "finishedOn": utc_now(),
                },
            },
        },
        "webterm": {
            "schema_version": 1,
            "signature_status": signature_status,
            "notes": notes_for_status(signature_status),
            "verification": {
                "checksums": "scripts/generate_release_checksums.py",
                "sbom": "scripts/generate_sbom.py",
                "evidence": "scripts/collect_release_evidence.py",
                "github_attestation": "gh attestation verify <artifact> --repo <owner/repo>",
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts-dir",
        action="append",
        default=[],
        type=Path,
        help="Artifact directory/file to attest (repeatable). Default: .ci-artifacts/sbom",
    )
    parser.add_argument(
        "--checksums",
        type=Path,
        default=None,
        help="Optional checksums.json or SHA256SUMS.txt to include as subject",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".ci-artifacts/provenance/provenance.intoto.json"),
    )
    parser.add_argument(
        "--builder-id",
        default="https://github.com/LLprod39/WebTerm/security-scaffold@v1",
    )
    parser.add_argument(
        "--invocation-id",
        default=None,
        help="CI run id / invocation id",
    )
    parser.add_argument(
        "--signature-status",
        default="unsigned_scaffold",
        choices=sorted(VALID_SIGNATURE_STATUSES),
        help="Signing state recorded in the statement (default: unsigned_scaffold)",
    )
    parser.add_argument(
        "--attestation-id",
        default=None,
        help="Optional GitHub attestation id to embed after signing",
    )
    parser.add_argument(
        "--attestation-url",
        default=None,
        help="Optional GitHub attestation URL to embed after signing",
    )
    parser.add_argument(
        "--bundle-path",
        default=None,
        help="Optional path to Sigstore bundle produced by the attest action",
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
    roots = args.artifacts_dir or [Path(".ci-artifacts/sbom")]
    files: list[Path] = []
    for raw in roots:
        path = raw if raw.is_absolute() else repo / raw
        files.extend(iter_files(path))
    if args.checksums:
        checksums = args.checksums if args.checksums.is_absolute() else repo / args.checksums
        if checksums.is_file():
            files.append(checksums)
        elif checksums.is_dir():
            files.extend(iter_files(checksums))
    # stable unique; exclude prior provenance / attestation sidecars from subjects
    skip_names = {
        "provenance.intoto.json",
        "github-attestation.json",
        "provenance.signing.json",
    }
    uniq: list[Path] = []
    seen: set[str] = set()
    for path in files:
        if path.name in skip_names:
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(path)
    if not uniq:
        print("No artifacts found for provenance", file=sys.stderr)
        return 2
    subjects = [subject_for(path, repo) for path in uniq]
    attestation_meta: dict[str, Any] | None = None
    if args.attestation_id or args.attestation_url or args.bundle_path:
        attestation_meta = {
            k: v
            for k, v in {
                "id": args.attestation_id,
                "url": args.attestation_url,
                "bundle_path": args.bundle_path,
                "recorded_at": utc_now(),
            }.items()
            if v
        }
    statement = build_statement(
        repo=repo,
        subjects=subjects,
        build_invocation_id=args.invocation_id,
        builder_id=args.builder_id,
        signature_status=args.signature_status,
        attestation_meta=attestation_meta,
    )
    output = args.output if args.output.is_absolute() else repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(statement, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sidecar = output.parent / "github-attestation.json"
    if attestation_meta is not None or args.signature_status.startswith("github_"):
        sidecar.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signature_status": args.signature_status,
                    "subjects": subjects,
                    "attestation": attestation_meta or {},
                    "verify": "gh attestation verify <artifact> --repo <owner/repo>",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(sidecar)

    print(output)
    print(f"Attested {len(subjects)} subjects (signature_status={args.signature_status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
