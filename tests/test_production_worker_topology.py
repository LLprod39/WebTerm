from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_RUNTIME_ENV = {
    "CHANNEL_REDIS_URL",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROK_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
}


def _load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def _service_by_name(blueprint: dict, name: str) -> dict:
    for service in blueprint.get("services", []):
        if service.get("name") == name:
            return service
    raise AssertionError(f"Service {name!r} is missing")


def _env_keys(service: dict) -> set[str]:
    return {
        str(item["key"])
        for item in service.get("envVars", [])
        if isinstance(item, dict) and item.get("key")
    }


def test_render_pipeline_workers_have_runtime_env():
    blueprint = _load_yaml("render.yaml")
    expected = {
        "mini-prod-scheduled-pipelines": "python manage.py run_scheduled_pipelines --daemon --interval 60",
        "mini-prod-monitor": "python manage.py run_monitor --quick-interval 300 --deep-interval 600 --cleanup-interval 86400 --concurrency 5",
        "mini-prod-telegram-bot": "python manage.py run_telegram_bot",
    }

    for name, command in expected.items():
        service = _service_by_name(blueprint, name)
        assert service["type"] == "worker"
        assert service["runtime"] == "docker"
        assert service["dockerCommand"] == command
        assert PIPELINE_RUNTIME_ENV <= _env_keys(service)


def test_compose_production_studio_workers_are_declared():
    compose = _load_yaml("docker-compose.production.yml")
    services = compose["services"]

    assert "scheduled-pipelines" in services
    assert "monitor" in services
    assert "telegram-bot" in services
    assert "python manage.py run_scheduled_pipelines --daemon" in " ".join(services["scheduled-pipelines"]["command"])
    assert "python manage.py run_monitor" in " ".join(services["monitor"]["command"])
    assert services["telegram-bot"]["command"] == ["sh", "-lc", "python manage.py run_telegram_bot"]
    assert services["telegram-bot"]["profiles"] == ["telegram-bot"]
