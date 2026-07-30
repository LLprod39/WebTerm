import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIGEST = re.compile(r"^[a-z0-9./_-]+:[a-z0-9._-]+@sha256:[0-9a-f]{64}$")


def test_production_registry_images_are_release_bound_by_digest() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))

    expected_repositories = {
        "postgres": "postgres:16-alpine@sha256:",
        "redis": "redis:7-alpine@sha256:",
        "nginx": "nginx:1.27-alpine@sha256:",
    }
    for service, expected_prefix in expected_repositories.items():
        image = compose["services"][service]["image"]
        assert IMAGE_DIGEST.fullmatch(image), f"{service} image is mutable: {image}"
        assert image.startswith(expected_prefix), f"{service} image changed compatibility line: {image}"


def test_mars_profile_has_no_mutable_fallback_image() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))

    image = compose["services"]["mars-agent"]["image"]
    assert "MARS_AGENT_DOCKER_IMAGE" in image
    assert ":latest" not in image
    assert "@sha256:" in image


def test_agent_command_runtime_has_no_mutable_fallback_image() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))

    environment = compose["x-backend-worker-environment"]
    image = environment["AGENT_COMMAND_RUNNER_IMAGE"]
    assert "AGENT_COMMAND_RUNNER_IMAGE" in image
    assert ":latest" not in image
    assert "required" in image
