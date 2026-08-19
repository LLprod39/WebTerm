#!/usr/bin/env python3
"""Validate the production env example and generate its operator reference."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PATH = ROOT / ".env.production.example"
DOC_PATH = ROOT / "docs" / "ENVIRONMENT_VARIABLES.md"
CATEGORIES = ("required", "common", "expert")
IGNORED_PARTS = {
    ".git",
    ".venv",
    ".venv-wsl",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "docs",
    "htmlcov",
    "media",
    "private",
    "tests",
    "migrations",
    "staticfiles",
}
SOURCE_SUFFIXES = {".py", ".yml", ".yaml", ".sh", ".ps1", ".ts", ".tsx", ".js", ".mjs", ".toml", ".conf"}
SECRET_MARKERS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "PRIVATE_KEY")
VARIABLE_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<default>.*)$")
CATEGORY_RE = re.compile(r"^# CATEGORY: (REQUIRED|COMMON|EXPERT)\b(?:\s*[-—:]\s*(.*))?$", re.IGNORECASE)


@dataclass(frozen=True)
class EnvVariable:
    name: str
    default: str
    category: str
    section: str
    line: int


def parse_example(path: Path = EXAMPLE_PATH) -> list[EnvVariable]:
    variables: list[EnvVariable] = []
    category = ""
    section = "General"
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines, start=1):
        category_match = CATEGORY_RE.match(line.strip())
        if category_match:
            category = category_match.group(1).lower()
            continue
        if line.startswith("# ") and not set(line[2:].strip()) <= {"-", "="}:
            candidate = line[2:].strip()
            if candidate and not candidate.lower().startswith(("copy ", "main ", "category:")):
                section = candidate.rstrip(":")
        match = VARIABLE_RE.match(line)
        if not match:
            continue
        if category not in CATEGORIES:
            raise ValueError(f"{path}:{index}: variable {match.group('name')} is outside a CATEGORY block")
        variables.append(
            EnvVariable(
                name=match.group("name"),
                default=match.group("default"),
                category=category,
                section=section,
                line=index,
            )
        )
    duplicates = sorted({item.name for item in variables if sum(other.name == item.name for other in variables) > 1})
    if duplicates:
        raise ValueError(f"duplicate variables in {path}: {', '.join(duplicates)}")
    present_categories = {item.category for item in variables}
    if present_categories != set(CATEGORIES):
        raise ValueError(f"expected categories {CATEGORIES}, found {sorted(present_categories)}")
    return variables


def _source_files() -> list[Path]:
    files: list[Path] = []
    for directory, child_dirs, child_files in os.walk(ROOT):
        child_dirs[:] = [name for name in child_dirs if name not in IGNORED_PARTS]
        for name in child_files:
            path = Path(directory) / name
            if path in {EXAMPLE_PATH, ROOT / ".env.example", DOC_PATH}:
                continue
            if path.suffix in SOURCE_SUFFIXES or name.startswith("Dockerfile") or name.startswith("docker-compose"):
                files.append(path)
    return files


def unused_variables(variables: list[EnvVariable]) -> list[EnvVariable]:
    names = {item.name for item in variables}
    used: set[str] = set()
    matcher = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)) + r")\b")
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        used.update(matcher.findall(text))
        if used == names:
            break
    return [item for item in variables if item.name not in used]


def _display_default(item: EnvVariable) -> str:
    if item.default.lower() in {"true", "false"}:
        return item.default.lower()
    if any(marker in item.name.upper() for marker in SECRET_MARKERS):
        return "operator supplied" if not item.default else "placeholder; replace"
    return item.default or "empty"


def render_document(variables: list[EnvVariable]) -> str:
    labels = {
        "required": "Required",
        "common": "Frequently changed",
        "expert": "Expert tuning",
    }
    lines = [
        "# Production environment variables",
        "",
        "Generated from `.env.production.example` by `scripts/env_contract.py`. Do not edit this table by hand.",
        "",
        f"Total variables: **{len(variables)}**.",
        "",
    ]
    for category in CATEGORIES:
        lines.extend([f"## {labels[category]}", "", "| Variable | Purpose | Default |", "|---|---|---|"])
        for item in (value for value in variables if value.category == category):
            purpose = item.section.replace("|", "\\|")
            default = _display_default(item).replace("|", "\\|").replace("`", "\\`")
            lines.append(f"| `{item.name}` | {purpose} | `{default}` |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-docs", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        variables = parse_example()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    unused = unused_variables(variables)
    if unused:
        for item in unused:
            print(f"unused env variable: {item.name} ({EXAMPLE_PATH.name}:{item.line})", file=sys.stderr)
        return 1
    rendered = render_document(variables)
    if args.write_docs:
        DOC_PATH.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"wrote {DOC_PATH}")
    if args.check:
        if not DOC_PATH.exists() or DOC_PATH.read_text(encoding="utf-8") != rendered:
            print(
                "environment variable documentation is stale; run scripts/env_contract.py --write-docs", file=sys.stderr
            )
            return 1
        print(f"environment contract ok: {len(variables)} variables")
    if not args.write_docs and not args.check:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
