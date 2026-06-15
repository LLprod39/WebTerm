from __future__ import annotations

from app.agent_kernel import ops_runtime_registry


def ops_runtime():
    provider = ops_runtime_registry.get()
    if provider is None:
        raise RuntimeError("Server ops runtime provider is not registered.")
    return provider


def log_query_sources() -> set[str]:
    return set(ops_runtime().log_sources()) | {"docker"}


async def run_command_result(server, *, secret: str = "", command: str):
    return await ops_runtime().run_command_result(server, secret=secret, command=command)


async def get_linux_ui_capabilities(server, *, secret: str = ""):
    return await ops_runtime().get_linux_ui_capabilities(server, secret=secret)


async def get_linux_ui_disk(server, *, secret: str = ""):
    return await ops_runtime().get_linux_ui_disk(server, secret=secret)


async def get_linux_ui_docker(server, *, secret: str = ""):
    return await ops_runtime().get_linux_ui_docker(server, secret=secret)


async def get_linux_ui_docker_logs(server, *, secret: str = "", container: str = "", lines: int = 80):
    return await ops_runtime().get_linux_ui_docker_logs(server, secret=secret, container=container, lines=lines)


async def get_linux_ui_logs(server, *, secret: str = "", source: str = "journal", lines: int = 120, service: str = ""):
    return await ops_runtime().get_linux_ui_logs(server, secret=secret, source=source, lines=lines, service=service)


async def get_linux_ui_network(server, *, secret: str = ""):
    return await ops_runtime().get_linux_ui_network(server, secret=secret)


async def get_linux_ui_overview(server, *, secret: str = ""):
    return await ops_runtime().get_linux_ui_overview(server, secret=secret)


async def get_linux_ui_packages(server, *, secret: str = ""):
    return await ops_runtime().get_linux_ui_packages(server, secret=secret)


async def get_linux_ui_processes(server, *, secret: str = "", limit: int = 80):
    return await ops_runtime().get_linux_ui_processes(server, secret=secret, limit=limit)


async def get_linux_ui_service_logs(server, *, secret: str = "", service: str = "", lines: int = 80):
    return await ops_runtime().get_linux_ui_service_logs(server, secret=secret, service=service, lines=lines)


async def get_linux_ui_services(server, *, secret: str = "", limit: int = 120):
    return await ops_runtime().get_linux_ui_services(server, secret=secret, limit=limit)


async def run_linux_ui_docker_action(server, *, secret: str = "", container: str = "", action: str = ""):
    return await ops_runtime().run_linux_ui_docker_action(server, secret=secret, container=container, action=action)


async def run_linux_ui_process_action(server, *, secret: str = "", pid="", action: str = ""):
    return await ops_runtime().run_linux_ui_process_action(server, secret=secret, pid=pid, action=action)


async def run_linux_ui_service_action(server, *, secret: str = "", service: str = "", action: str = ""):
    return await ops_runtime().run_linux_ui_service_action(server, secret=secret, service=service, action=action)


async def read_text_file(server, *, secret: str = "", path: str, max_bytes: int):
    return await ops_runtime().read_text_file(server, secret=secret, path=path, max_bytes=max_bytes)


async def write_text_file(server, *, secret: str = "", path: str, content: str, max_bytes: int):
    return await ops_runtime().write_text_file(server, secret=secret, path=path, content=content, max_bytes=max_bytes)
