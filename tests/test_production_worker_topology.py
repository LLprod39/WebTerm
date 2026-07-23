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
    return {str(item["key"]) for item in service.get("envVars", []) if isinstance(item, dict) and item.get("key")}


def _dotenv_values(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


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
        assert _env_keys(service) >= PIPELINE_RUNTIME_ENV


def test_render_kubernetes_ops_sync_worker_is_declared():
    blueprint = _load_yaml("render.yaml")
    backend = _service_by_name(blueprint, "mini-prod-backend")
    worker = _service_by_name(blueprint, "mini-prod-kubernetes-ops-sync")
    env_keys = _env_keys(worker)

    assert any(
        item.get("key") == "MANAGED_SECRET_KEY" and item.get("generateValue") is True for item in backend["envVars"]
    )
    assert worker["type"] == "worker"
    assert worker["runtime"] == "docker"
    assert (
        worker["dockerCommand"]
        == "python manage.py run_kubernetes_ops_sync_worker --daemon --interval 300 --worker-key render"
    )
    assert {
        "DJANGO_SECRET_KEY",
        "MANAGED_SECRET_KEY",
        "CHANNEL_REDIS_URL",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    } <= env_keys


def test_render_common_env_declares_kubernetes_ops_flags():
    blueprint = _load_yaml("render.yaml")
    group = next(item for item in blueprint["envVarGroups"] if item["name"] == "mini-prod-backend-common")
    values = {item["key"]: item.get("value") for item in group["envVars"]}

    assert values["KUBERNETES_OPS_SYNC_INTERVAL_SECONDS"] == "300"
    assert values["KUBERNETES_OPS_STALE_AFTER_SECONDS"] == "900"
    assert values["KUBERNETES_OPS_READY_FOR_SIDEBAR"] == "false"
    assert values["KUBERNETES_OPS_RELEASE_ENVIRONMENT"] == "local"
    assert values["KUBERNETES_OPS_PRODUCTION_APPROVAL_REF"] == ""
    assert values["KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS"] == "86400"
    assert values["KUBERNETES_ADMIN_MODE_ENABLED"] == "false"
    assert values["KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_REQUIRED"] == "false"


def test_env_production_example_declares_kubernetes_production_evidence_refs():
    values = _dotenv_values(".env.production.example")

    assert values["KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_ADMIN_MODE_ENABLED"] == "false"
    assert values["KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF"] == ""
    assert values["KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_REQUIRED"] == "false"


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


def test_compose_production_kubernetes_ops_sync_worker_is_declared():
    compose = _load_yaml("docker-compose.production.yml")
    services = compose["services"]

    assert "kubernetes-ops-sync" in services
    assert services["kubernetes-ops-sync"]["container_name"] == "mini-prod-kubernetes-ops-sync"
    command = " ".join(services["kubernetes-ops-sync"]["command"])
    assert "python manage.py run_kubernetes_ops_sync_worker --daemon" in command
    assert "--interval ${KUBERNETES_OPS_SYNC_INTERVAL_SECONDS:-300}" in command
    assert "--worker-key production" in command
