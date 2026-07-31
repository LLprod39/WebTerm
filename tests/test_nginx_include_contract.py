from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_production_servers_share_one_common_include() -> None:
    config = (ROOT / "docker" / "nginx" / "production.conf").read_text(encoding="utf-8")
    common = ROOT / "docker" / "nginx" / "webterm-server-common.conf"

    assert common.is_file()
    assert config.count("include /etc/nginx/webterm-server-common.conf;") == 2
    assert config.count("location ") == 0
    assert config.count("listen ") == 2
    assert "listen 8080;" in config
    assert "listen 8443 ssl http2;" in config


def test_production_compose_mounts_common_include_read_only() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    volumes = compose["services"]["nginx"]["volumes"]

    assert "./docker/nginx/webterm-server-common.conf:/etc/nginx/webterm-server-common.conf:ro" in volumes
