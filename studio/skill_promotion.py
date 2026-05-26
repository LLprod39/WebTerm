from __future__ import annotations

from app.agent_kernel.domain.specs import (
    PromotedSkill,
    SkillPromotionRequest,
    SkillPromotionResult,
)
from app.agent_kernel.memory.compaction import compact_text


class StudioSkillPromotionGateway:
    """Studio-backed implementation of skill draft promotion."""

    def promote_skill_draft(self, request: SkillPromotionRequest) -> SkillPromotionResult:
        from django.contrib.auth.models import User
        from django.utils import timezone

        from studio.models import StudioSkillAccess
        from studio.skill_authoring import scaffold_skill, slugify_skill_name, validate_skill_dir
        from studio.skill_registry import SkillNotFoundError, get_skill

        user = User.objects.filter(pk=request.actor_user_id, is_active=True).first()
        if user is None:
            raise ValueError("User not found")

        metadata = dict(request.metadata or {})
        existing_slug = str(metadata.get("promoted_skill_slug") or "").strip()
        skill = None
        if existing_slug:
            try:
                skill = get_skill(existing_slug)
            except SkillNotFoundError:
                skill = None

        validation_payload = None
        created = False
        if skill is None:
            suffix = str(request.memory_key or "").split(":", 1)[-1]
            intent = str(metadata.get("intent") or "ops").strip().lower() or "ops"
            skill_name = f"{request.server_name} {intent.replace('_', ' ').title()} Ops"
            requested_slug = slugify_skill_name(f"{request.server_name}-{intent}-{suffix[:8]}")
            description = (
                f"Автосгенерированный operational skill на основе повторяющегося паттерна "
                f"`{metadata.get('display_command') or request.snapshot_title}` для сервера {request.server_name}."
            )
            runtime_policy = {}
            if request.is_mutating:
                runtime_policy = {
                    "mutating_tool_patterns": ["ssh_execute"],
                    "required_preflight_tools": ["read_console"],
                    "auto_inject_pinned_arguments": True,
                }
            skill_dir = scaffold_skill(
                name=skill_name,
                description=description,
                slug=requested_slug,
                service=request.server_name,
                category=intent,
                safety_level="high" if runtime_policy else "standard",
                ui_hint="server_ops",
                tags=["auto-generated", "server-memory", intent],
                guardrail_summary=[
                    "Resolve the target server before mutation.",
                    "Run verification after every change.",
                    "Do not expose secrets from command output.",
                ],
                recommended_tools=["read_console", "ssh_execute", "report"],
                runtime_policy=runtime_policy,
                with_scripts=False,
                with_references=False,
                with_assets=False,
                force=False,
            )
            skill_file = skill_dir / "SKILL.md"
            existing_content = skill_file.read_text(encoding="utf-8")
            skill_file.write_text(
                existing_content.rstrip()
                + "\n\n## Derived Draft\n\n"
                + request.snapshot_content.strip()
                + self._workflow_section(metadata)
                + self._success_signal_section(metadata)
                + self._cwd_section(metadata)
                + "\n\n## Source Signal\n\n"
                + f"- Server: {request.server_name} ({request.server_host})\n"
                + f"- Memory key: {request.memory_key}\n"
                + f"- Display command: {metadata.get('display_command') or 'n/a'}\n"
                + f"- Intent: {metadata.get('intent') or 'ops'}\n",
                encoding="utf-8",
            )
            validation = validate_skill_dir(skill_dir)
            validation_payload = validation.to_dict()
            if validation.errors:
                raise ValueError("Generated skill draft failed validation")
            try:
                skill = get_skill(skill_dir.name)
            except SkillNotFoundError as exc:
                raise ValueError("Generated skill could not be loaded") from exc
            access, _created = StudioSkillAccess.objects.get_or_create(
                slug=skill.slug,
                defaults={"owner": user},
            )
            if access.owner_id is None:
                access.owner = user
                access.save(update_fields=["owner"])
            metadata["promoted_skill_slug"] = skill.slug
            metadata["promoted_skill_path"] = skill.path
            metadata["promoted_to_skill_at"] = timezone.now().isoformat()
            created = True

        promoted = PromotedSkill(
            slug=skill.slug,
            name=skill.name,
            path=skill.path,
            detail=skill.to_detail_dict(),
        )
        validation_payload = validation_payload or {
            "slug": promoted.slug,
            "path": promoted.path,
            "errors": [],
            "warnings": [],
            "is_valid": True,
        }
        return SkillPromotionResult(
            skill=promoted,
            metadata=metadata,
            validation=validation_payload,
            created=created,
        )

    @staticmethod
    def _workflow_section(metadata: dict) -> str:
        commands = [str(item).strip() for item in (metadata.get("commands") or []) if str(item).strip()]
        if not commands:
            return ""
        return "\n\n## Derived Workflow\n\n" + "\n".join(
            f"{index}. `{command}`" for index, command in enumerate(commands[:6], start=1)
        )

    @staticmethod
    def _success_signal_section(metadata: dict) -> str:
        success_signals = [str(item).strip() for item in (metadata.get("sample_outputs") or []) if str(item).strip()]
        if not success_signals:
            return ""
        return "\n\n## Success Signals\n\n" + "\n".join(
            f"- {compact_text(item, limit=180)}" for item in success_signals[:4]
        )

    @staticmethod
    def _cwd_section(metadata: dict) -> str:
        common_cwds = [str(item).strip() for item in (metadata.get("common_cwds") or []) if str(item).strip()]
        if not common_cwds:
            return ""
        return "\n\n## Typical Working Directories\n\n" + "\n".join(
            f"- `{compact_text(item, limit=160)}`" for item in common_cwds[:3]
        )
