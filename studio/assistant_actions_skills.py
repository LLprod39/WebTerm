"""Studio skill create / update assistant actions."""

from __future__ import annotations

from typing import Any

from app.assistant_actions import AssistantActionContext, AssistantActionError
from studio.skill_authoring import scaffold_skill, validate_skill_dir
from studio.skill_registry import SkillNotFoundError, get_skill
from studio.views.skill_helpers import (
    _can_edit_skill,
    _ensure_skill_access,
    _get_skill_access,
    _skill_dir_from_slug,
    _skill_to_detail_dict,
)
from studio.views.skill_views import (
    _has_skill_metadata_update,
    _render_skill_metadata,
    _update_skill_metadata_file,
)


def create_studio_skill(ctx: AssistantActionContext) -> dict[str, Any]:
    name = str(ctx.input_payload.get("name") or "").strip()
    description = str(ctx.input_payload.get("description") or "").strip()
    if not name:
        raise AssistantActionError("name is required")
    if not description:
        raise AssistantActionError("description is required")
    if len(description) < 20:
        raise AssistantActionError("description must be at least 20 characters (when to use / trigger)")

    requested_slug = str(ctx.input_payload.get("slug") or "").strip() or None
    force = bool(ctx.input_payload.get("force"))
    if force and not getattr(ctx.user, "is_staff", False):
        if not requested_slug:
            raise AssistantActionError("force requires an explicit slug for non-admin users")
        existing_access = _get_skill_access(requested_slug)
        try:
            existing_skill = get_skill(requested_slug)
        except SkillNotFoundError:
            existing_skill = None
        if existing_skill is not None and not _can_edit_skill(ctx.user, existing_access):
            raise AssistantActionError("You can overwrite only your own skills", status=403)

    runtime_policy = ctx.input_payload.get("runtime_policy")
    if runtime_policy not in (None, "") and not isinstance(runtime_policy, dict):
        raise AssistantActionError("runtime_policy must be a JSON object")

    def _listish(key: str) -> list[str]:
        raw = ctx.input_payload.get(key)
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(raw, str) and raw.strip():
            return [p.strip() for p in raw.split(",") if p.strip()]
        return []

    try:
        skill_dir = scaffold_skill(
            name=name,
            description=description,
            slug=requested_slug,
            service=str(ctx.input_payload.get("service") or "").strip(),
            category=str(ctx.input_payload.get("category") or "").strip(),
            safety_level=str(ctx.input_payload.get("safety_level") or "standard").strip() or "standard",
            ui_hint=str(ctx.input_payload.get("ui_hint") or "").strip(),
            tags=_listish("tags"),
            guardrail_summary=_listish("guardrail_summary"),
            recommended_tools=_listish("recommended_tools"),
            runtime_policy=dict(runtime_policy or {}),
            with_scripts=bool(ctx.input_payload.get("with_scripts")),
            with_references=bool(ctx.input_payload.get("with_references")),
            with_assets=bool(ctx.input_payload.get("with_assets")),
            force=force,
        )
    except (ValueError, FileExistsError) as exc:
        raise AssistantActionError(str(exc)) from exc

    validation = validate_skill_dir(skill_dir)
    if validation.errors:
        import shutil

        shutil.rmtree(skill_dir, ignore_errors=True)
        raise AssistantActionError(
            "Skill scaffold did not pass validation: " + "; ".join(validation.errors),
            details=validation.to_dict(),
        )

    # Optional body override (full SKILL body after frontmatter)
    body = str(ctx.input_payload.get("content") or ctx.input_payload.get("body") or "").strip()
    if body:
        skill_file = skill_dir / "SKILL.md"
        raw = skill_file.read_text(encoding="utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                front = "---" + parts[1] + "---"
                skill_file.write_text(front + "\n" + body.strip() + "\n", encoding="utf-8")
                revalidation = validate_skill_dir(skill_dir)
                if revalidation.errors:
                    skill_file.write_text(raw, encoding="utf-8")
                    raise AssistantActionError(
                        "Skill content invalid: " + "; ".join(revalidation.errors),
                        details=revalidation.to_dict(),
                    )

    try:
        skill = get_skill(skill_dir.name)
    except SkillNotFoundError as exc:
        raise AssistantActionError("Skill was created but could not be loaded", status=500) from exc
    access = _ensure_skill_access(skill.slug, owner=ctx.user)
    return {
        "ok": True,
        "skill": _skill_to_detail_dict(skill, ctx.user, access),
        "validation": validation.to_dict(),
        "target_url": f"/studio/skills/{skill.slug}",
    }


def update_studio_skill(ctx: AssistantActionContext) -> dict[str, Any]:
    slug = str(ctx.input_payload.get("slug") or "").strip()
    if not slug:
        raise AssistantActionError("slug is required")
    try:
        skill = get_skill(slug)
    except SkillNotFoundError as exc:
        raise AssistantActionError("Skill not found", status=404) from exc
    access = _get_skill_access(skill.slug)
    if not _can_edit_skill(ctx.user, access):
        raise AssistantActionError("You can edit only your own skills", status=403)

    data = dict(ctx.input_payload or {})
    updated = False
    if _has_skill_metadata_update(data):
        skill, error = _update_skill_metadata_file(skill, data)
        if error:
            raise AssistantActionError(error)
        updated = True

    body = data.get("content")
    if body is None:
        body = data.get("body")
    if body is not None:
        body_text = str(body)
        skill_file = _skill_dir_from_slug(skill.slug) / "SKILL.md"
        original = skill_file.read_text(encoding="utf-8")
        # Preserve frontmatter; replace body only
        if original.startswith("---"):
            parts = original.split("---", 2)
            if len(parts) >= 3:
                meta = dict(skill.metadata or {})
                # Prefer re-render from current skill metadata if available
                try:
                    front = _render_skill_metadata(meta) if meta else ("---" + parts[1] + "---")
                except Exception:
                    front = "---" + parts[1] + "---"
                next_content = f"{front}\n{body_text.rstrip()}\n"
            else:
                next_content = body_text
        else:
            next_content = body_text
        skill_file.write_text(next_content, encoding="utf-8")
        validation = validate_skill_dir(skill_file.parent)
        if validation.errors:
            skill_file.write_text(original, encoding="utf-8")
            raise AssistantActionError(
                "Skill content invalid: " + "; ".join(validation.errors),
                details=validation.to_dict(),
            )
        try:
            skill = get_skill(skill.slug)
        except SkillNotFoundError as exc:
            skill_file.write_text(original, encoding="utf-8")
            raise AssistantActionError("Skill updated but could not be reloaded") from exc
        updated = True

    if not updated:
        raise AssistantActionError("Nothing to update — pass name/description/content (or other metadata fields)")

    access = _get_skill_access(skill.slug)
    return {
        "ok": True,
        "skill": _skill_to_detail_dict(skill, ctx.user, access),
        "target_url": f"/studio/skills/{skill.slug}",
    }
