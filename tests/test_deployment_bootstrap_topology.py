from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_backend_start_only_starts_asgi_server():
    script = (ROOT / "docker" / "render-backend-start.sh").read_text(encoding="utf-8")
    assert "manage.py migrate" not in script
    assert "collectstatic" not in script
    assert "load_pipeline_templates" not in script
    assert "exec daphne" in script


def test_static_assets_are_collected_during_image_build():
    dockerfile = (ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
    assert "python manage.py collectstatic --noinput" in dockerfile


def test_production_migration_is_one_shot_and_backend_is_scalable():
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    migration = services["migrate"]
    backend = services["backend"]
    command = " ".join(migration["command"])

    assert migration["restart"] == "no"
    assert "manage.py migrate --noinput" in command
    assert "load_pipeline_templates" in command
    assert "--force" not in command
    assert backend["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert "container_name" not in backend
    assert "ports" not in backend
    assert backend["expose"] == ["9000"]
