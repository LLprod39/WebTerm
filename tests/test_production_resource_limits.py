from __future__ import annotations

from pathlib import Path

import yaml
from django.conf import settings

ROOT = Path(__file__).resolve().parents[1]


def test_django_rejects_large_data_and_spools_large_files():
    assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 5 * 1024 * 1024
    assert settings.FILE_UPLOAD_MAX_MEMORY_SIZE == 5 * 1024 * 1024


def test_nginx_has_small_default_and_explicit_upload_exceptions():
    config = (ROOT / "docker" / "nginx" / "production.conf").read_text(encoding="utf-8")

    assert config.count("client_max_body_size 2m;") == 1
    assert config.count("location = /servers/api/playbooks/import/preview/") == 2
    assert config.count("location = /servers/api/playbooks/import/commit/") == 2
    assert config.count("location = /api/plugins/packages/install-local-upload/") == 2
    assert config.count("client_max_body_size 12m;") == 6
    assert config.count("location ~ ^/servers/api/[0-9]+/files/upload/$") == 2
    assert config.count("client_max_body_size 52m;") == 2


def test_backend_and_every_worker_have_runtime_resource_limits():
    config = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    services = config["services"]
    worker_names = (
        "scheduled-pipelines",
        "scheduled-agents",
        "history-pruner",
        "playbook-execution-worker",
        "monitor",
        "ops-supervisor",
        "kubernetes-ops-sync",
        "celery-worker",
        "telegram-bot",
    )

    assert services["backend"]["mem_limit"] == "${WEBTERM_BACKEND_MEMORY:-1g}"
    assert services["backend"]["cpus"] == "${WEBTERM_BACKEND_CPUS:-2.0}"
    assert services["backend"]["pids_limit"] == "${WEBTERM_BACKEND_PIDS_LIMIT:-512}"
    proxy = services["playbook-docker-proxy"]
    assert proxy["mem_limit"] == "128m"
    assert proxy["cpus"] == 0.5
    assert proxy["pids_limit"] == 64
    for service_name in worker_names:
        service = services[service_name]
        assert service["mem_limit"] == "${WEBTERM_BACKEND_WORKER_MEMORY:-768m}"
        assert service["cpus"] == "${WEBTERM_BACKEND_WORKER_CPUS:-1.0}"
        assert service["pids_limit"] == "${WEBTERM_BACKEND_WORKER_PIDS_LIMIT:-256}"
