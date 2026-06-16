from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

FALLBACK_SKILLS = [
    {
        "slug": "frontend-design",
        "name": "frontend-design",
        "description": "Frontend design and product UI polish.",
        "path": "",
    },
    {
        "slug": "frontend-dev",
        "name": "frontend-dev",
        "description": "Full-stack frontend implementation.",
        "path": "",
    },
    {
        "slug": "react-best-practices",
        "name": "react-best-practices",
        "description": "React performance and implementation best practices.",
        "path": "",
    },
    {
        "slug": "frontend-testing-debugging",
        "name": "frontend-testing-debugging",
        "description": "Browser, Playwright, and rendered frontend QA.",
        "path": "",
    },
]


def _frontmatter_value(body: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", body, re.I | re.M)
    if not match:
        return ""
    return match.group(1).strip().strip("'\"")


def _read_skill_file(path: Path) -> dict[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    frontmatter = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
    name = _frontmatter_value(frontmatter, "name") or path.parent.name
    description = _frontmatter_value(frontmatter, "description")
    slug = name.strip() or path.parent.name
    if not slug:
        return None
    return {
        "slug": slug,
        "name": name,
        "description": description,
        "path": str(path),
    }


def _configured_roots() -> list[Path]:
    raw_roots = getattr(settings, "MARS_SKILL_ROOTS", None)
    roots: list[Path] = []
    if isinstance(raw_roots, (list, tuple)):
        roots.extend(Path(str(root)).expanduser() for root in raw_roots if str(root).strip())
    elif isinstance(raw_roots, str) and raw_roots.strip():
        roots.extend(Path(root.strip()).expanduser() for root in raw_roots.split(os.pathsep) if root.strip())

    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    roots.extend(
        [
            codex_home / "skills",
            codex_home / "plugins" / "cache",
            Path.home() / ".codex" / "skills",
            Path.home() / ".codex" / "plugins" / "cache",
        ]
    )
    wsl_users_root = Path("/mnt/c/Users")
    if wsl_users_root.exists():
        try:
            user_homes = list(wsl_users_root.iterdir())
        except OSError:
            user_homes = []
        for user_home in user_homes:
            try:
                is_dir = user_home.is_dir()
            except OSError:
                is_dir = False
            if not is_dir:
                continue
            roots.extend(
                [
                    user_home / ".codex" / "skills",
                    user_home / ".codex" / "plugins" / "cache",
                ]
            )
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve(strict=False))
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


@lru_cache(maxsize=1)
def discover_skill_catalog() -> tuple[dict[str, str], ...]:
    skills_by_slug: dict[str, dict[str, str]] = {}
    limit = int(getattr(settings, "MARS_SKILL_CATALOG_LIMIT", 600))
    for root in _configured_roots():
        if not _path_exists(root):
            continue
        try:
            skill_paths = root.rglob("SKILL.md")
            for skill_path in skill_paths:
                item = _read_skill_file(skill_path)
                if item is None:
                    continue
                skills_by_slug.setdefault(item["slug"], item)
                if len(skills_by_slug) >= limit:
                    break
        except OSError:
            continue
        if len(skills_by_slug) >= limit:
            break

    for item in FALLBACK_SKILLS:
        skills_by_slug.setdefault(item["slug"], dict(item))

    return tuple(sorted(skills_by_slug.values(), key=lambda item: item["slug"].lower()))


def available_skill_slugs() -> list[str]:
    return [item["slug"] for item in discover_skill_catalog()]


def skill_catalog_summary() -> dict[str, Any]:
    catalog = discover_skill_catalog()
    return {
        "mode": "automatic",
        "available_count": len(catalog),
        "hidden_from_user": True,
    }


def recommend_task_skills(task_brief: str, *, limit: int | None = None) -> list[str]:
    catalog = list(discover_skill_catalog())
    max_items = limit if limit is not None else int(getattr(settings, "MARS_RECOMMENDED_SKILL_LIMIT", 24))
    text = (task_brief or "").lower()
    tokens = set(re.findall(r"[\wа-яА-ЯёЁ-]{3,}", text, re.U))
    weighted_terms = {
        "frontend": ("frontend", "react", "ui", "ux", "web", "browser", "vite", "shadcn", "design"),
        "backend": ("api", "django", "server", "database", "postgres", "security", "validation"),
        "game": ("game", "three", "3d", "canvas", "playwright", "web-game"),
        "data": ("data", "analytics", "dashboard", "report", "visualization", "spreadsheet"),
        "video": ("video", "remotion", "hyperframes", "audio", "sora"),
        "docs": ("doc", "pdf", "presentation", "ppt", "notion"),
    }
    active_terms = []
    for markers in weighted_terms.values():
        if any(marker in text for marker in markers):
            active_terms.extend(markers)

    scored: list[tuple[int, str]] = []
    for item in catalog:
        searchable = f"{item.get('slug', '')} {item.get('name', '')} {item.get('description', '')}".lower()
        score = sum(3 for token in tokens if token in searchable)
        score += sum(2 for marker in active_terms if marker in searchable)
        if item["slug"] in {"frontend-design", "frontend-dev", "react-best-practices", "frontend-testing-debugging"}:
            score += 1
        if score > 0:
            scored.append((score, item["slug"]))

    scored.sort(key=lambda pair: (-pair[0], pair[1].lower()))
    selected = [slug for _, slug in scored[:max_items]]
    if selected:
        return selected
    return available_skill_slugs()[:max_items]


def format_skill_list_for_prompt(skills: list[str]) -> str:
    catalog = {item["slug"]: item for item in discover_skill_catalog()}
    lines: list[str] = []
    for slug in skills:
        item = catalog.get(slug)
        if item is None:
            lines.append(f"- {slug}")
            continue
        description = item.get("description") or ""
        lines.append(f"- {slug}: {description[:160]}")
    return "\n".join(lines) or "- No dedicated skills selected."
