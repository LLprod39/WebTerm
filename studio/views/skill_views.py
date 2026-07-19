"""
Studio skill catalog and workspace endpoints.
"""

import contextlib
import shutil

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from studio.skill_authoring import (
    KNOWN_SAFETY_LEVELS,
    _render_frontmatter_value,
    scaffold_skill,
    validate_skill_dir,
    validate_skills,
)
from studio.skill_registry import SkillNotFoundError, get_skill, list_skills
from studio.skill_templates import get_skill_template, list_skill_templates
from studio.views.common import (
    _apply_shared_users,
    _err,
    _is_admin,
    _json_body,
    _normalise_related_ids,
    _normalise_string_list,
    _ok,
    _require_admin,
)
from studio.views.skill_helpers import (
    _SKILL_WORKSPACE_MAX_BYTES,
    _can_edit_skill,
    _can_read_skill,
    _ensure_skill_access,
    _get_skill_access,
    _resolve_skill_workspace_file,
    _skill_access_map,
    _skill_dir_from_slug,
    _skill_to_detail_dict,
    _skill_to_summary_dict,
    _skill_workspace_file_payload,
    _skill_workspace_response,
)

STUDIO_FEATURE_SKILLS = "studio_skills"

_SKILL_METADATA_ORDER = (
    "name",
    "description",
    "service",
    "category",
    "safety_level",
    "ui_hint",
    "guardrail_summary",
    "recommended_tools",
    "runtime_policy",
    "tags",
)
_SKILL_METADATA_FIELDS = set(_SKILL_METADATA_ORDER)


def _has_skill_metadata_update(data: dict) -> bool:
    return any(key in data for key in _SKILL_METADATA_FIELDS)


def _normalise_skill_metadata_update(skill, data: dict) -> tuple[dict | None, str | None]:
    metadata = dict(skill.metadata or {})

    def set_text(key: str, *, required: bool = False) -> str | None:
        if key not in data:
            return None
        value = str(data.get(key) or "").strip()
        if required and not value:
            return f"{key} is required"
        if value:
            metadata[key] = value
        else:
            metadata.pop(key, None)
        return None

    for key, required in (("name", True), ("description", True), ("service", False), ("category", False), ("ui_hint", False)):
        error = set_text(key, required=required)
        if error:
            return None, error

    if "safety_level" in data:
        safety_level = str(data.get("safety_level") or "standard").strip() or "standard"
        if safety_level not in KNOWN_SAFETY_LEVELS:
            return None, f"safety_level must be one of: {', '.join(sorted(KNOWN_SAFETY_LEVELS))}"
        metadata["safety_level"] = safety_level

    for key in ("tags", "guardrail_summary", "recommended_tools"):
        if key in data:
            value = _normalise_string_list(data.get(key))
            if value:
                metadata[key] = value
            else:
                metadata.pop(key, None)

    if "runtime_policy" in data:
        raw_runtime_policy = data.get("runtime_policy")
        if raw_runtime_policy in (None, ""):
            metadata.pop("runtime_policy", None)
        elif not isinstance(raw_runtime_policy, dict):
            return None, "runtime_policy must be a JSON object"
        elif raw_runtime_policy:
            metadata["runtime_policy"] = dict(raw_runtime_policy)
        else:
            metadata.pop("runtime_policy", None)

    name = str(metadata.get("name") or skill.name or "").strip()
    description = str(metadata.get("description") or skill.description or "").strip()
    if not name:
        return None, "name is required"
    if not description:
        return None, "description is required"
    metadata["name"] = name
    metadata["description"] = description
    metadata["safety_level"] = str(metadata.get("safety_level") or skill.safety_level or "standard").strip() or "standard"
    return metadata, None


def _render_skill_metadata(metadata: dict) -> str:
    lines = ["---"]
    rendered_keys: set[str] = set()
    for key in _SKILL_METADATA_ORDER:
        if key not in metadata:
            continue
        value = metadata.get(key)
        if value in ("", [], {}):
            continue
        lines.append(f"{key}: {_render_frontmatter_value(value)}")
        rendered_keys.add(key)
    for key in sorted(set(metadata) - rendered_keys):
        value = metadata.get(key)
        if value in ("", [], {}):
            continue
        lines.append(f"{key}: {_render_frontmatter_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def _update_skill_metadata_file(skill, data: dict) -> tuple[object | None, str | None]:
    metadata, error = _normalise_skill_metadata_update(skill, data)
    if error:
        return None, error

    skill_file = _skill_dir_from_slug(skill.slug) / "SKILL.md"
    original_content = skill_file.read_text(encoding="utf-8")
    body = str(skill.content or "").rstrip()
    next_content = f"{_render_skill_metadata(metadata)}\n{body}\n"
    skill_file.write_text(next_content, encoding="utf-8")

    validation = validate_skill_dir(skill_file.parent)
    if validation.errors:
        skill_file.write_text(original_content, encoding="utf-8")
        return None, "; ".join(validation.errors)

    try:
        return get_skill(skill.slug), None
    except SkillNotFoundError:
        skill_file.write_text(original_content, encoding="utf-8")
        return None, "Skill was updated but could not be reloaded"


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["GET"])
def api_skills(request):
    skills = list_skills()
    access_map = _skill_access_map([skill.slug for skill in skills])
    visible = []
    for skill in skills:
        access = access_map.get(skill.slug.lower())
        if not _can_read_skill(request.user, access):
            continue
        visible.append(_skill_to_summary_dict(skill, request.user, access))
    return _ok(visible)


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["GET", "PUT"])
def api_skill_detail(request, slug: str):
    try:
        skill = get_skill(slug)
    except SkillNotFoundError:
        return _err("Skill not found", 404)
    access = _get_skill_access(skill.slug)
    if not _can_read_skill(request.user, access):
        return _err("Skill not found", 404)

    if request.method == "GET":
        return _ok(_skill_to_detail_dict(skill, request.user, access))

    data = _json_body(request)
    if _has_skill_metadata_update(data):
        if not _can_edit_skill(request.user, access):
            return _err("You can edit only your own skills", 403)
        skill, error = _update_skill_metadata_file(skill, data)
        if error:
            return _err(error)

    if "is_shared" in data or "shared_user_ids" in data:
        admin_error = _require_admin(request, message="Only admin can change skill sharing")
        if admin_error:
            return admin_error
        access = _ensure_skill_access(skill.slug, owner=access.owner if access else None)
        if "is_shared" in data:
            access.is_shared = bool(data.get("is_shared"))
            access.save(update_fields=["is_shared"])
        if "shared_user_ids" in data:
            _apply_shared_users(access, _normalise_related_ids(data.get("shared_user_ids")))

    access = _get_skill_access(skill.slug)
    return _ok(_skill_to_detail_dict(skill, request.user, access))


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["GET"])
def api_skill_templates(_request):
    return _ok([item.to_dict() for item in list_skill_templates()])


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["POST"])
def api_skill_scaffold(request):
    data = _json_body(request)
    template_slug = str(data.get("template_slug") or "").strip()
    template = get_skill_template(template_slug) if template_slug else None
    if template_slug and template is None:
        return _err("Unknown skill template")

    defaults = dict(template.defaults) if template else {}
    name = str(data.get("name") or defaults.get("name") or "").strip()
    description = str(data.get("description") or defaults.get("description") or "").strip()
    if not name:
        return _err("name is required")
    if not description:
        return _err("description is required")

    raw_runtime_policy = data.get("runtime_policy")
    if raw_runtime_policy not in (None, "") and not isinstance(raw_runtime_policy, dict):
        return _err("runtime_policy must be a JSON object")

    runtime_policy = dict(defaults.get("runtime_policy") or {})
    runtime_policy.update(dict(raw_runtime_policy or {}))

    requested_slug = str(data.get("slug") or "").strip()
    if bool(data.get("force")) and not _is_admin(request.user):
        if not requested_slug:
            return _err("force requires an explicit slug for non-admin users")
        existing_access = _get_skill_access(requested_slug)
        existing_skill = None
        with contextlib.suppress(SkillNotFoundError):
            existing_skill = get_skill(requested_slug)
        if existing_skill is not None and not _can_edit_skill(request.user, existing_access):
            return _err("You can overwrite only your own skills", 403)

    try:
        skill_dir = scaffold_skill(
            name=name,
            description=description,
            slug=requested_slug or None,
            service=str(data.get("service") or defaults.get("service") or "").strip(),
            category=str(data.get("category") or defaults.get("category") or "").strip(),
            safety_level=str(data.get("safety_level") or defaults.get("safety_level") or "standard").strip()
            or "standard",
            ui_hint=str(data.get("ui_hint") or defaults.get("ui_hint") or "").strip(),
            tags=_normalise_string_list(data.get("tags") or defaults.get("tags")),
            guardrail_summary=_normalise_string_list(data.get("guardrail_summary") or defaults.get("guardrail_summary")),
            recommended_tools=_normalise_string_list(data.get("recommended_tools") or defaults.get("recommended_tools")),
            runtime_policy=runtime_policy,
            with_scripts=bool(data.get("with_scripts")),
            with_references=bool(data.get("with_references")),
            with_assets=bool(data.get("with_assets")),
            force=bool(data.get("force")),
        )
    except (ValueError, FileExistsError) as exc:
        return _err(str(exc))

    validation = validate_skill_dir(skill_dir)
    if validation.errors:
        shutil.rmtree(skill_dir, ignore_errors=True)
        return JsonResponse(
            {
                "error": "Skill scaffold did not pass validation",
                "validation": validation.to_dict(),
            },
            status=400,
        )

    try:
        skill = get_skill(skill_dir.name)
    except SkillNotFoundError:
        return _err("Skill was created but could not be loaded", 500)
    access = _ensure_skill_access(skill.slug, owner=request.user)
    if _is_admin(request.user):
        if "is_shared" in data:
            access.is_shared = bool(data.get("is_shared"))
            access.save(update_fields=["is_shared"])
        if "shared_user_ids" in data:
            _apply_shared_users(access, _normalise_related_ids(data.get("shared_user_ids")))
        access = _get_skill_access(skill.slug)

    return _ok(
        {
            "ok": True,
            "skill": _skill_to_detail_dict(skill, request.user, access),
            "validation": validation.to_dict(),
        },
        status=201,
    )


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["POST"])
def api_skill_validate(request):
    data = _json_body(request)
    slugs = _normalise_string_list(data.get("slugs"))
    strict = bool(data.get("strict"))

    if slugs:
        access_map = _skill_access_map(slugs)
        denied = []
        allowed_slugs = []
        for slug in slugs:
            access = access_map.get(slug.lower())
            if _can_read_skill(request.user, access):
                allowed_slugs.append(slug)
            else:
                denied.append(slug)
        if denied:
            return _err(f"Skills not accessible: {', '.join(denied)}", 403)
        results = validate_skills(allowed_slugs) if allowed_slugs else []
    else:
        all_skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in all_skills])
        visible_slugs = [
            skill.slug
            for skill in all_skills
            if _can_read_skill(request.user, access_map.get(skill.slug.lower()))
        ]
        results = validate_skills(visible_slugs) if visible_slugs else []

    if slugs:
        found = {item.slug.lower() for item in results}
        missing = [slug for slug in slugs if slug.lower() not in found]
        if missing:
            return _err(f"Skills not found: {', '.join(missing)}", 404)

    error_count = sum(len(item.errors) for item in results)
    warning_count = sum(len(item.warnings) for item in results)
    return _ok(
        {
            "results": [item.to_dict() for item in results],
            "summary": {
                "skills": len(results),
                "errors": error_count,
                "warnings": warning_count,
                "is_valid": error_count == 0 and (warning_count == 0 if strict else True),
                "strict": strict,
            },
        }
    )


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["GET"])
def api_skill_workspace(request, slug: str):
    try:
        skill = get_skill(slug)
    except SkillNotFoundError:
        return _err("Skill not found", 404)
    access = _get_skill_access(skill.slug)
    if not _can_read_skill(request.user, access):
        return _err("Skill not found", 404)
    return _ok(_skill_workspace_response(skill.slug, request.user, access))


@require_feature(STUDIO_FEATURE_SKILLS)
def api_skill_workspace_file(request, slug: str):
    try:
        skill = get_skill(slug)
    except SkillNotFoundError:
        return _err("Skill not found", 404)
    access = _get_skill_access(skill.slug)
    if not _can_read_skill(request.user, access):
        return _err("Skill not found", 404)
    can_edit = _can_edit_skill(request.user, access)
    skill_dir = _skill_dir_from_slug(skill.slug)

    if request.method == "GET":
        raw_path = request.GET.get("path", "")
        file_path, relative_path, error = _resolve_skill_workspace_file(skill_dir, raw_path)
        if error:
            return _err(error)
        if file_path is None or relative_path is None or not file_path.exists():
            return _err("File not found", 404)
        try:
            return _ok(_skill_workspace_file_payload(skill_dir, relative_path, include_content=True, editable=can_edit))
        except ValueError as exc:
            return _err(str(exc), 400)

    if not can_edit:
        return _err("Only the owner or admin can edit this skill workspace", 403)

    data = _json_body(request)
    raw_path = data.get("path", "")
    file_path, relative_path, error = _resolve_skill_workspace_file(skill_dir, raw_path)
    if error:
        return _err(error)
    if file_path is None or relative_path is None:
        return _err("invalid path")

    if request.method == "POST":
        if file_path.exists():
            return _err("File already exists", 409)
        content = str(data.get("content", ""))
        if len(content.encode("utf-8")) > _SKILL_WORKSPACE_MAX_BYTES:
            return _err("File is too large", 400)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return _ok(
            {
                "ok": True,
                "file": _skill_workspace_file_payload(skill_dir, relative_path, include_content=True, editable=True),
                "validation": validate_skill_dir(skill_dir).to_dict(),
            },
            status=201,
        )

    if request.method == "PUT":
        if not file_path.exists():
            return _err("File not found", 404)
        content = str(data.get("content", ""))
        if len(content.encode("utf-8")) > _SKILL_WORKSPACE_MAX_BYTES:
            return _err("File is too large", 400)
        file_path.write_text(content, encoding="utf-8")
        return _ok(
            {
                "ok": True,
                "file": _skill_workspace_file_payload(skill_dir, relative_path, include_content=True, editable=True),
                "validation": validate_skill_dir(skill_dir).to_dict(),
            }
        )

    if request.method == "DELETE":
        if relative_path == "SKILL.md":
            return _err("SKILL.md cannot be deleted", 400)
        if not file_path.exists():
            return _err("File not found", 404)
        file_path.unlink()
        with contextlib.suppress(OSError):
            parent = file_path.parent
            while parent != skill_dir and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        return _ok({"ok": True, "validation": validate_skill_dir(skill_dir).to_dict()})

    return _err("Method not allowed", 405)
