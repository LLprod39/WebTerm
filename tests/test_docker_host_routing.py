"""Loopback → Docker host routing for SSH and local model endpoints in containers."""

from __future__ import annotations

from types import SimpleNamespace

import asyncssh
import pytest

from app.core import docker_host_routing as routing


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (routing.ROUTE_ENV, routing.ALIAS_ENV, "WEBTERM_ANSIBLE_DOCKER_HOST_ALIAS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(routing, "running_in_container", lambda: False)
    monkeypatch.setattr(routing, "_LOGGED_ROUTES", set())


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.0.1.1", True),
        ("::1", True),
        ("[::1]", True),
        ("localhost", True),
        ("LOCALHOST.", True),
        ("10.0.0.5", False),
        ("prom-01.example.com", False),
        ("", False),
    ],
)
def test_is_loopback_host(host, expected):
    assert routing.is_loopback_host(host) is expected


def test_no_routing_outside_container_by_default():
    assert routing.route_loopback_host("127.0.0.1") == "127.0.0.1"
    assert routing.route_loopback_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"


def test_auto_routing_inside_container(monkeypatch):
    monkeypatch.setattr(routing, "running_in_container", lambda: True)
    assert routing.route_loopback_host("127.0.0.1") == "host.docker.internal"
    assert routing.route_loopback_host("localhost") == "host.docker.internal"
    assert routing.route_loopback_host("10.1.2.3") == "10.1.2.3"


def test_env_opt_out_wins_inside_container(monkeypatch):
    monkeypatch.setattr(routing, "running_in_container", lambda: True)
    monkeypatch.setenv(routing.ROUTE_ENV, "0")
    assert routing.route_loopback_host("127.0.0.1") == "127.0.0.1"


def test_env_opt_in_and_custom_alias(monkeypatch):
    monkeypatch.setenv(routing.ROUTE_ENV, "true")
    monkeypatch.setenv(routing.ALIAS_ENV, "host.containers.internal")
    assert routing.route_loopback_host("127.0.0.1") == "host.containers.internal"


def test_force_bypasses_container_check():
    assert routing.route_loopback_host("127.0.0.1", force=True) == "host.docker.internal"


@pytest.mark.parametrize("alias", ["", "bad alias!", "127.0.0.1"])
def test_empty_invalid_or_loopback_alias_disables_routing(monkeypatch, alias):
    monkeypatch.setenv(routing.ROUTE_ENV, "1")
    monkeypatch.setenv(routing.ALIAS_ENV, alias)
    assert routing.route_loopback_host("127.0.0.1") == "127.0.0.1"


def test_route_url_preserves_scheme_port_path_and_userinfo(monkeypatch):
    monkeypatch.setenv(routing.ROUTE_ENV, "1")
    assert routing.route_loopback_url("http://127.0.0.1:11434") == "http://host.docker.internal:11434"
    assert (
        routing.route_loopback_url("https://u:p@localhost:8443/v1?x=1")
        == "https://u:p@host.docker.internal:8443/v1?x=1"
    )
    assert routing.route_loopback_url("http://[::1]/api") == "http://host.docker.internal/api"
    assert routing.route_loopback_url("http://192.168.0.16:11434") == "http://192.168.0.16:11434"
    assert routing.route_loopback_url("127.0.0.1:11434") == "127.0.0.1:11434"  # no scheme: untouched


# --- SSH connect kwargs -------------------------------------------------------


def _server(**overrides):
    values = {
        "pk": 17,
        "id": 17,
        "host": "127.0.0.1",
        "port": 22,
        "username": "root",
        "auth_method": "password",
        "key_path": "",
        "network_config": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_connect_kwargs_route_loopback_and_keep_host_key_alias(monkeypatch):
    from servers.ssh_host_keys import build_server_connect_kwargs

    monkeypatch.setattr(routing, "running_in_container", lambda: True)
    known_hosts = object()
    kwargs = build_server_connect_kwargs(_server(), secret="pw", known_hosts=known_hosts)
    assert kwargs["host"] == "host.docker.internal"
    assert kwargs["host_key_alias"] == "127.0.0.1"
    assert kwargs["port"] == 22
    assert kwargs["known_hosts"] is known_hosts


def test_connect_kwargs_unchanged_outside_container():
    from servers.ssh_host_keys import build_server_connect_kwargs

    kwargs = build_server_connect_kwargs(_server(), secret="pw", known_hosts=object())
    assert kwargs["host"] == "127.0.0.1"
    assert "host_key_alias" not in kwargs


def test_connect_kwargs_not_routed_through_bastion(monkeypatch):
    from servers.ssh_host_keys import build_server_connect_kwargs

    monkeypatch.setattr(routing, "running_in_container", lambda: True)
    server = _server(network_config={"network": {"bastion_host": "bastion.example.com"}})
    kwargs = build_server_connect_kwargs(server, secret="pw", known_hosts=object())
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["tunnel"] == "bastion.example.com"
    assert "host_key_alias" not in kwargs


def test_trusted_key_for_loopback_matches_via_host_key_alias():
    """asyncssh verifies the alias (configured host) against our known_hosts entries."""
    from asyncssh.known_hosts import match_known_hosts

    from servers.ssh_host_keys import _serialize_host_key, build_known_hosts

    key = asyncssh.generate_private_key("ssh-ed25519")
    record = _serialize_host_key(key.convert_to_public())
    known_hosts = build_known_hosts("127.0.0.1", 22, [record])
    trusted_via_alias = match_known_hosts(known_hosts, "127.0.0.1", "192.168.65.254", None)[0]
    trusted_via_routed_host = match_known_hosts(known_hosts, "host.docker.internal", "192.168.65.254", None)[0]
    assert trusted_via_alias and not trusted_via_routed_host


# --- Agent command runner (separate bridge container) -------------------------


def test_agent_runner_routes_loopback_even_outside_container(monkeypatch, settings):
    from servers.services import agent_command_runner

    settings.AGENT_COMMAND_DOCKER_NETWORK = "bridge"
    monkeypatch.setattr(agent_command_runner, "agent_command_uses_docker", lambda: True)
    original = {"host": "127.0.0.1", "port": 22}
    routed = agent_command_runner._route_for_runner_container(original)
    assert routed["host"] == "host.docker.internal"
    assert original["host"] == "127.0.0.1"  # caller's dict untouched
    server = _server()
    monkeypatch.setattr(
        agent_command_runner,
        "get_server_trusted_host_keys",
        lambda _server: [{"public_key": "ssh-ed25519 AAAA"}],
    )
    assert agent_command_runner._known_hosts_text(server, routed) == (
        "host.docker.internal ssh-ed25519 AAAA\n[host.docker.internal]:22 ssh-ed25519 AAAA\n"
    )


@pytest.mark.parametrize(
    ("network", "kwargs"),
    [
        ("host", {"host": "127.0.0.1"}),
        ("none", {"host": "127.0.0.1"}),
        ("bridge", {"host": "127.0.0.1", "tunnel": "bastion.example.com"}),
        ("bridge", {"host": "10.0.0.5"}),
    ],
)
def test_agent_runner_skips_routing(monkeypatch, settings, network, kwargs):
    from servers.services import agent_command_runner

    settings.AGENT_COMMAND_DOCKER_NETWORK = network
    monkeypatch.setattr(agent_command_runner, "agent_command_uses_docker", lambda: True)
    assert agent_command_runner._route_for_runner_container(kwargs) == kwargs


# --- Model endpoints ----------------------------------------------------------


def _aux_config(provider="ollama", base="http://127.0.0.1:11434"):
    return SimpleNamespace(aux_llm_provider=provider, aux_llm_model="qwen2.5:3b", aux_llm_base_url=base)


@pytest.fixture
def _no_llm_keys(monkeypatch):
    monkeypatch.setattr("app.core.llm_secrets.get_managed_llm_api_key", lambda *_a, **_k: "")


@pytest.mark.usefixtures("_no_llm_keys")
def test_aux_endpoint_routes_loopback_in_container(monkeypatch):
    from app.core.aux_model_roles import _resolve_aux_endpoint

    monkeypatch.setattr(routing, "running_in_container", lambda: True)
    _p, _m, url, _k = _resolve_aux_endpoint(_aux_config())
    assert url == "http://host.docker.internal:11434/v1/chat/completions"
    _p, _m, url, _k = _resolve_aux_endpoint(_aux_config("openai_compatible", "http://localhost:8000"))
    assert url == "http://host.docker.internal:8000/v1/chat/completions"


@pytest.mark.usefixtures("_no_llm_keys")
def test_aux_endpoint_unchanged_outside_container():
    from app.core.aux_model_roles import _resolve_aux_endpoint

    _p, _m, url, _k = _resolve_aux_endpoint(_aux_config())
    assert url == "http://127.0.0.1:11434/v1/chat/completions"


def test_ollama_candidates_prefer_docker_host_in_container(monkeypatch):
    from app.core import ollama_config

    monkeypatch.setattr(ollama_config, "_sticky_ollama_url", lambda: None)
    monkeypatch.setattr(ollama_config, "_tcp_open", lambda *_a, **_k: False)
    monkeypatch.setattr(ollama_config, "is_wsl_runtime", lambda: False)

    assert ollama_config.get_ollama_base_urls("http://127.0.0.1:11434")[0] == "http://127.0.0.1:11434"
    monkeypatch.setattr(routing, "running_in_container", lambda: True)
    urls = ollama_config.get_ollama_base_urls("http://127.0.0.1:11434")
    assert urls[:2] == ["http://host.docker.internal:11434", "http://127.0.0.1:11434"]
