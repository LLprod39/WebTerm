"""
Shared helpers for Studio skill endpoints and agent skill payloads.
"""

import contextlib
from pathlib import Path, PurePosixPath

from django.contrib.auth.models import User

from studio.models import StudioSkillAccess
from studio.skill_authoring import validate_skill_dir
from studio.skill_registry import SkillNotFoundError, get_skill, normalise_skill_slugs
from studio.views.common import (
    STUDIO_FEATURE_SKILLS,
    _access_mode,
    _is_admin,
    _owner_payload,
    _shared_user_payloads,
    _user_has_feature,
)


def _skill_access_map(slugs: list[str]) -> dict[str, StudioSkillAccess]:
    if not slugs:
        return {}
    rows = StudioSkillAccess.objects.filter(slug__in=slugs).select_related("owner").prefetch_related("shared_with")
    return {row.slug.lower(): row for row in rows}


def _get_skill_access(slug: str) -> StudioSkillAccess | None:
    return StudioSkillAccess.objects.filter(slug=slug).select_related("owner").prefetch_related("shared_with").first()


def _ensure_skill_access(slug: str, owner: User | None = None) -> StudioSkillAccess:
    access, _created = StudioSkillAccess.objects.get_or_create(slug=slug, defaults={"owner": owner})
    if owner is not None and access.owner_id is None:
        access.owner = owner
        access.save()
    return StudioSkillAccess.objects.filter(pk=access.pk).select_related("owner").prefetch_related("shared_with").get()


def _can_read_skill(user, access: StudioSkillAccess | None) -> bool:
    if _is_admin(user):
        return True
    if access is None or not user or not getattr(user, "is_authenticated", False):
        return False
    if access.owner_id == user.id or access.is_shared:
        return True
    return any(shared_user.id == user.id for shared_user in access.shared_with.all())


def _can_edit_skill(user, access: StudioSkillAccess | None) -> bool:
    if _is_admin(user):
        return True
    return bool(access and user and getattr(user, "is_authenticated", False) and access.owner_id == user.id)


def _skill_to_summary_dict(skill, viewer, access: StudioSkillAccess | None) -> dict:
    shared_users = _shared_user_payloads(access.shared_with.all()) if access else []
    data = skill.to_summary_dict()
    data.update(
        {
            "path": skill.path,
            "owner": _owner_payload(access.owner) if access else None,
            "owner_username": access.owner.username if access and access.owner_id else "",
            "is_owner": bool(access and access.owner_id == getattr(viewer, "id", None)),
            "can_edit": _can_edit_skill(viewer, access),
            "can_share": _is_admin(viewer),
            "is_shared": bool(access and (access.is_shared or shared_users)),
            "shared_user_ids": [item["id"] for item in shared_users],
            "shared_users": shared_users,
            "access_mode": _access_mode(owner_id=access.owner_id if access else None, viewer=viewer),
        }
    )
    return data


def _skill_to_detail_dict(skill, viewer, access: StudioSkillAccess | None) -> dict:
    data = skill.to_detail_dict()
    data.update(_skill_to_summary_dict(skill, viewer, access))
    return data


def _normalise_skill_payload(raw_values) -> list[str]:
    return normalise_skill_slugs(raw_values)


def _sanitize_accessible_skill_slugs(user, slugs: list[str]) -> list[str]:
    if not slugs or not _user_has_feature(user, STUDIO_FEATURE_SKILLS):
        return []

    access_map = _skill_access_map(slugs)
    sanitized: list[str] = []
    for slug in slugs:
        skill = None
        with contextlib.suppress(SkillNotFoundError):
            skill = get_skill(slug)
        if skill is None:
            continue
        access = access_map.get(skill.slug.lower())
        if _is_admin(user) or _can_read_skill(user, access):
            sanitized.append(skill.slug)
    return sanitized


_SKILL_WORKSPACE_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".csv",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".js",
    ".ts",
}
_SKILL_WORKSPACE_DIRS = {"references", "scripts", "assets"}
_SKILL_WORKSPACE_MAX_BYTES = 500_000


def _skill_dir_from_slug(slug: str) -> Path:
    skill = get_skill(slug)
    return Path(skill.path).resolve().parent


def _skill_workspace_kind(path: str) -> str:
    if path == "SKILL.md":
        return "skill"
    if path.startswith("references/"):
        return "reference"
    if path.startswith("scripts/"):
        return "script"
    if path.startswith("assets/"):
        return "asset"
    return "file"


def _skill_workspace_language(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".md"):
        return "markdown"
    if lowered.endswith((".yml", ".yaml")):
        return "yaml"
    if lowered.endswith(".json"):
        return "json"
    if lowered.endswith(".py"):
        return "python"
    if lowered.endswith((".sh", ".bash", ".zsh")):
        return "shell"
    if lowered.endswith(".ts"):
        return "typescript"
    if lowered.endswith(".js"):
        return "javascript"
    if lowered.endswith(".sql"):
        return "sql"
    if lowered.endswith(".csv"):
        return "csv"
    return "text"


def _normalise_skill_workspace_path(raw_path: str) -> tuple[str | None, str | None]:
    candidate = str(raw_path or "").strip().replace("\\", "/")
    if not candidate:
        return None, "path is required"
    pure = PurePosixPath(candidate)
    if pure.is_absolute():
        return None, "absolute paths are not allowed"
    parts = [part for part in pure.parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None, "invalid path"
    if any(part.startswith(".") for part in parts):
        return None, "hidden paths are not allowed"
    if parts == ["SKILL.md"]:
        return "SKILL.md", None
    if parts[0] not in _SKILL_WORKSPACE_DIRS:
        return None, "path must live under references/, scripts/, or assets/"
    if len(parts) < 2:
        return None, "file name is required"
    filename = parts[-1]
    suffix = Path(filename).suffix.lower()
    if suffix and suffix not in _SKILL_WORKSPACE_TEXT_EXTENSIONS:
        return None, f"unsupported file type: {suffix}"
    return "/".join(parts), None


def _resolve_skill_workspace_file(skill_dir: Path, raw_path: str) -> tuple[Path | None, str | None, str | None]:
    normalized, error = _normalise_skill_workspace_path(raw_path)
    if error:
        return None, None, error
    file_path = (skill_dir / normalized).resolve()
    try:
        file_path.relative_to(skill_dir)
    except ValueError:
        return None, None, "path escapes the skill directory"
    return file_path, normalized, None


def _skill_workspace_file_payload(
    skill_dir: Path,
    relative_path: str,
    *,
    include_content: bool = False,
    editable: bool = True,
) -> dict:
    file_path = (skill_dir / relative_path).resolve()
    payload = {
        "path": relative_path,
        "name": file_path.name,
        "kind": _skill_workspace_kind(relative_path),
        "language": _skill_workspace_language(relative_path),
        "size": file_path.stat().st_size if file_path.exists() else 0,
        "editable": bool(editable),
    }
    if include_content:
        try:
            payload["content"] = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Only UTF-8 text files can be edited in the web workspace: {relative_path}") from exc
    return payload


def _list_skill_workspace_files(skill_dir: Path, *, editable: bool = True) -> list[dict]:
    files: list[dict] = []
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        files.append(_skill_workspace_file_payload(skill_dir, "SKILL.md", editable=editable))
    for folder in ("references", "scripts", "assets"):
        folder_path = skill_dir / folder
        if not folder_path.exists() or not folder_path.is_dir():
            continue
        for file_path in sorted(folder_path.rglob("*"), key=lambda item: str(item).lower()):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(skill_dir).as_posix()
            try:
                files.append(_skill_workspace_file_payload(skill_dir, relative_path, editable=editable))
            except ValueError:
                continue
    return files


def _skill_workspace_response(slug: str, viewer, access: StudioSkillAccess | None) -> dict:
    skill = get_skill(slug)
    skill_dir = Path(skill.path).resolve().parent
    validation = validate_skill_dir(skill_dir)
    can_edit = _can_edit_skill(viewer, access)
    return {
        "skill": _skill_to_detail_dict(skill, viewer, access),
        "files": _list_skill_workspace_files(skill_dir, editable=can_edit),
        "validation": validation.to_dict(),
    }
