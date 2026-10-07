from __future__ import annotations

from urllib.error import URLError

from ai_cli_runner_manager.docker_plane import docker_plane_is_ready, docker_proxy_health_url


def test_docker_proxy_health_url_from_tcp_host() -> None:
    assert docker_proxy_health_url("tcp://ai-cli-docker-proxy:2375") == "http://ai-cli-docker-proxy:2375/health"


def test_docker_proxy_health_url_rejects_non_tcp() -> None:
    assert docker_proxy_health_url("unix:///var/run/docker.sock") is None


def test_docker_plane_ready_when_fake_runtime() -> None:
    assert docker_plane_is_ready(fake_runtime=True) is True


def test_docker_plane_ready_probes_proxy_health(monkeypatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://ai-cli-docker-proxy:2375")

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr("ai_cli_runner_manager.docker_plane.urlopen", lambda *_a, **_k: _Resp())
    assert docker_plane_is_ready(fake_runtime=False) is True


def test_docker_plane_not_ready_when_proxy_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://ai-cli-docker-proxy:2375")

    def _boom(*_a, **_k):
        raise URLError("connection refused")

    monkeypatch.setattr("ai_cli_runner_manager.docker_plane.urlopen", _boom)
    assert docker_plane_is_ready(fake_runtime=False) is False
