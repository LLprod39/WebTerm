from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from studio.demo_mcp_kubernetes_tools import KUBERNETES_TOOLS, kubernetes_describe_workload
except ModuleNotFoundError:  # pragma: no cover - supports `python studio/demo_mcp_server.py`.
    from demo_mcp_kubernetes_tools import KUBERNETES_TOOLS, kubernetes_describe_workload

ROOT_DIR = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
TEXT_EXTENSIONS = {
    ".css",
    ".env",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TOOLS = [
    {
        "name": "workspace_snapshot",
        "description": "Scan the repository and return a compact workspace summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "default": "."},
                "max_files": {"type": "integer", "default": 2500, "minimum": 1, "maximum": 20000},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "todo_scan",
        "description": "Find TODO/FIXME/HACK comments in text files under the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "default": "."},
                "max_matches": {"type": "integer", "default": 40, "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "build_action_cards",
        "description": "Create a deterministic execution brief from workspace and TODO summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "workspace_summary": {"type": "string"},
                "todo_summary": {"type": "string"},
                "ai_brief": {"type": "string"},
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compose_manifest",
        "description": "Build a JSON manifest string for the generated delivery pack.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "workspace_summary": {"type": "string"},
                "todo_summary": {"type": "string"},
                "action_plan": {"type": "string"},
                "ai_brief": {"type": "string"},
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_artifact",
        "description": "Write text content to a file under the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean", "default": True},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "artifact_status",
        "description": "Check whether an artifact exists and report its size and checksum.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_artifact",
        "description": "Read a preview from an artifact file under the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "default": 1800, "minimum": 100, "maximum": 12000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    *KUBERNETES_TOOLS,
]


class ToolError(RuntimeError):
    pass


def _is_allowed(path: Path) -> bool:
    return path == ROOT_DIR or path.is_relative_to(ROOT_DIR)


def _resolve_path(raw_path: str, *, allow_missing: bool = False) -> Path:
    candidate = Path(raw_path or ".")
    path = candidate if candidate.is_absolute() else (ROOT_DIR / candidate)
    path = path.resolve()
    if not _is_allowed(path):
        raise ToolError(f"Path must stay inside the workspace: {raw_path}")
    if not allow_missing and not path.exists():
        raise ToolError(f"Path does not exist: {raw_path}")
    return path


def _iter_workspace_files(root: Path):
    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(name for name in dir_names if name not in SKIP_DIRS)
        base = Path(current_root)
        for file_name in sorted(file_names):
            path = base / file_name
            if path.is_file():
                yield path


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _extract_number(label: str, text: str) -> int | None:
    match = re.search(rf"{re.escape(label)}:\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _workspace_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    root = _resolve_path(str(arguments.get("root") or "."))
    max_files = max(1, min(int(arguments.get("max_files") or 2500), 20000))
    extension_counts: Counter[str] = Counter()
    directory_counts: Counter[str] = Counter()
    samples: list[str] = []
    total_files = 0

    for path in _iter_workspace_files(root):
        total_files += 1
        rel_path = path.relative_to(ROOT_DIR).as_posix()
        extension = path.suffix.lower() or "<none>"
        extension_counts[extension] += 1
        parent = rel_path.split("/", 1)[0]
        directory_counts[parent] += 1
        if len(samples) < 12:
            samples.append(rel_path)
        if total_files >= max_files:
            break

    top_extensions = extension_counts.most_common(8)
    top_directories = directory_counts.most_common(8)
    summary = {
        "root": root.relative_to(ROOT_DIR).as_posix() or ".",
        "scanned_files": total_files,
        "top_extensions": top_extensions,
        "top_directories": top_directories,
        "sample_files": samples,
    }
    lines = [
        f"ROOT: {summary['root']}",
        f"SCANNED_FILES: {total_files}",
        "TOP_EXTENSIONS:",
    ]
    lines.extend(f"- {name}: {count}" for name, count in top_extensions)
    lines.append("TOP_DIRECTORIES:")
    lines.extend(f"- {name}: {count}" for name, count in top_directories)
    lines.append("SAMPLE_FILES:")
    lines.extend(f"- {item}" for item in samples)
    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "structuredContent": summary,
    }


def _todo_scan(arguments: dict[str, Any]) -> dict[str, Any]:
    root = _resolve_path(str(arguments.get("root") or "."))
    max_matches = max(1, min(int(arguments.get("max_matches") or 40), 200))
    matches: list[dict[str, Any]] = []

    for path in _iter_workspace_files(root):
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line_number, line in enumerate(handle, start=1):
                    upper_line = line.upper()
                    tag = next((item for item in ("TODO", "FIXME", "HACK") if item in upper_line), None)
                    if not tag:
                        continue
                    matches.append(
                        {
                            "path": path.relative_to(ROOT_DIR).as_posix(),
                            "line": line_number,
                            "tag": tag,
                            "text": line.strip()[:180],
                        }
                    )
                    if len(matches) >= max_matches:
                        break
        except OSError:
            continue
        if len(matches) >= max_matches:
            break

    hotspot = "yes" if len(matches) >= 5 else "no"
    lines = [
        f"TODO_MATCHES: {len(matches)}",
        f"HOTSPOT: {hotspot}",
        "MATCHES:",
    ]
    lines.extend(f"- {item['path']}:{item['line']} [{item['tag']}] {item['text']}" for item in matches)
    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "structuredContent": {"count": len(matches), "hotspot": hotspot == "yes", "matches": matches},
    }


def _sanitize_ai_brief(raw_brief: str) -> str:
    brief = (raw_brief or "").strip()
    if not brief or brief.lower().startswith("error:"):
        return "No external AI brief was available for this run."
    return brief[:2400]


def _build_action_cards(arguments: dict[str, Any]) -> dict[str, Any]:
    objective = str(arguments.get("objective") or "").strip() or "Validate the local MCP pipeline."
    workspace_summary = str(arguments.get("workspace_summary") or "").strip()
    todo_summary = str(arguments.get("todo_summary") or "").strip()
    ai_brief = _sanitize_ai_brief(str(arguments.get("ai_brief") or ""))
    scanned_files = _extract_number("SCANNED_FILES", workspace_summary) or 0
    todo_count = _extract_number("TODO_MATCHES", todo_summary) or 0
    hotspot = "yes" if "HOTSPOT: yes" in todo_summary else "no"

    lines = [
        "# MCP Workspace Forge",
        "",
        "## Objective",
        objective,
        "",
        "## Repository Signal",
        f"- Scanned files: {scanned_files}",
        f"- TODO matches: {todo_count}",
        f"- Hotspot: {hotspot}",
        "",
        "## Action Cards",
        "1. Inspect the workspace snapshot and validate that the MCP server can read repository state.",
        "2. Review TODO hotspots and decide whether they represent real technical debt or placeholders.",
        "3. Confirm that the generated artifacts under `.tmp_mcp_demo/` contain the expected data.",
        "4. Re-run the pipeline after edits to compare artifact hashes and file previews.",
        "",
        "## Optional AI Brief",
        ai_brief,
        "",
        "## Verification Checklist",
        "- Artifact plan file exists.",
        "- Artifact manifest file exists.",
        "- Preview node shows markdown and JSON content.",
        f"HOTSPOT: {hotspot}",
        "STATUS: READY",
    ]
    text = "\n".join(lines)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": {
            "objective": objective,
            "scanned_files": scanned_files,
            "todo_matches": todo_count,
            "hotspot": hotspot == "yes",
            "ai_brief": ai_brief,
        },
    }


def _compose_manifest(arguments: dict[str, Any]) -> dict[str, Any]:
    objective = str(arguments.get("objective") or "").strip() or "Validate the local MCP pipeline."
    workspace_summary = str(arguments.get("workspace_summary") or "")
    todo_summary = str(arguments.get("todo_summary") or "")
    action_plan = str(arguments.get("action_plan") or "")
    ai_brief = _sanitize_ai_brief(str(arguments.get("ai_brief") or ""))
    payload = {
        "objective": objective,
        "workspace": {
            "scanned_files": _extract_number("SCANNED_FILES", workspace_summary) or 0,
            "summary_hash": _sha1_text(workspace_summary),
        },
        "todos": {
            "count": _extract_number("TODO_MATCHES", todo_summary) or 0,
            "hotspot": "HOTSPOT: yes" in todo_summary,
            "summary_hash": _sha1_text(todo_summary),
        },
        "artifacts": [
            {"name": "plan", "path": ".tmp_mcp_demo/mcp_workspace_forge_plan.md"},
            {"name": "manifest", "path": ".tmp_mcp_demo/mcp_workspace_forge_manifest.json"},
        ],
        "action_plan_hash": _sha1_text(action_plan),
        "ai_brief_excerpt": ai_brief[:320],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
    }


def _write_artifact(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_path = str(arguments.get("path") or "").strip()
    if not raw_path:
        raise ToolError("path is required")
    content = str(arguments.get("content") or "")
    overwrite = bool(arguments.get("overwrite", True))
    path = _resolve_path(raw_path, allow_missing=True)
    if path.exists() and not overwrite:
        raise ToolError(f"Artifact already exists: {raw_path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    rel_path = path.relative_to(ROOT_DIR).as_posix()
    summary = {
        "path": rel_path,
        "size": len(content.encode("utf-8")),
        "sha1": _sha1_text(content),
    }
    text = "\n".join(
        [
            f"ARTIFACT_PATH: {rel_path}",
            f"BYTES_WRITTEN: {summary['size']}",
            f"SHA1: {summary['sha1']}",
        ]
    )
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": summary,
    }


def _artifact_status(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_path = str(arguments.get("path") or "").strip()
    if not raw_path:
        raise ToolError("path is required")
    path = _resolve_path(raw_path, allow_missing=True)
    exists = path.exists()
    content = path.read_text(encoding="utf-8", errors="ignore") if exists and path.is_file() else ""
    rel_path = path.relative_to(ROOT_DIR).as_posix()
    summary = {
        "path": rel_path,
        "exists": exists,
        "size": len(content.encode("utf-8")) if content else 0,
        "sha1": _sha1_text(content) if content else "",
    }
    text = "\n".join(
        [
            f"ARTIFACT_PATH: {rel_path}",
            f"EXISTS: {'yes' if exists else 'no'}",
            f"BYTES: {summary['size']}",
            f"SHA1: {summary['sha1']}",
        ]
    )
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": summary,
    }


def _read_artifact(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_path = str(arguments.get("path") or "").strip()
    if not raw_path:
        raise ToolError("path is required")
    max_chars = max(100, min(int(arguments.get("max_chars") or 1800), 12000))
    path = _resolve_path(raw_path)
    content = path.read_text(encoding="utf-8", errors="ignore")
    preview = content[:max_chars]
    rel_path = path.relative_to(ROOT_DIR).as_posix()
    text = "\n".join([f"ARTIFACT_PATH: {rel_path}", "", preview])
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": {"path": rel_path, "preview": preview, "truncated": len(content) > len(preview)},
    }


def _kubernetes_describe_workload(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        return kubernetes_describe_workload(arguments)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]
TOOL_HANDLERS: dict[str, ToolHandler] = {
    "workspace_snapshot": _workspace_snapshot,
    "todo_scan": _todo_scan,
    "build_action_cards": _build_action_cards,
    "compose_manifest": _compose_manifest,
    "write_artifact": _write_artifact,
    "artifact_status": _artifact_status,
    "read_artifact": _read_artifact,
    "kubernetes_describe_workload": _kubernetes_describe_workload,
}
