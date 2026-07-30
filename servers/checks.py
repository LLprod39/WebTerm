from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Tags, register

from app.agent_kernel.sandbox.ephemeral_runner import agent_command_image_is_immutable
from servers.services.playbooks.bundle_storage import path_is_within


@register(Tags.security, deploy=True)
def playbook_bundle_storage_deploy_check(app_configs, **kwargs):
    if settings.DEBUG:
        return []

    configured = getattr(
        settings,
        "PLAYBOOK_BUNDLE_STORAGE_ROOT",
        Path(settings.BASE_DIR) / "private" / "playbook_bundles",
    )
    if not path_is_within(configured, settings.MEDIA_ROOT):
        return []

    return [
        Error(
            "Playbook bundle storage is inside publicly served MEDIA_ROOT.",
            hint=(
                "Set PLAYBOOK_BUNDLE_STORAGE_ROOT to a private path and mount the "
                "playbook_bundles volume only into backend and playbook-execution-worker."
            ),
            id="servers.E001",
        )
    ]


@register(Tags.security, deploy=True)
def agent_command_runtime_deploy_check(app_configs, **kwargs):
    if settings.DEBUG:
        return []

    runtime = str(getattr(settings, "AGENT_COMMAND_RUNTIME", "docker") or "docker").strip().lower()
    if runtime not in {"docker", "container", "containers"}:
        return [
            Error(
                "Production agent commands are not configured for isolated execution.",
                hint="Set AGENT_COMMAND_RUNTIME=docker; host SSH execution is test-only.",
                id="servers.E002",
            )
        ]
    image = str(getattr(settings, "AGENT_COMMAND_RUNNER_IMAGE", "") or "").strip()
    if not agent_command_image_is_immutable(image):
        return [
            Error(
                "Production agent command runner image is not pinned by digest.",
                hint="Set AGENT_COMMAND_RUNNER_IMAGE to a sha256 image ID or repository@sha256 digest.",
                id="servers.E003",
            )
        ]
    return []
