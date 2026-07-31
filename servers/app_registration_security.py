"""Register SSH, secret, and runtime-limit adapters for the servers application."""


def register_security_adapters() -> None:
    from app.pipeline_ssh_provider import register_pipeline_ssh_provider
    from app.runtime_limits import register_terminal_session_limit_provider
    from app.tools.server_secret_provider import (
        register_server_auth_secret_provider,
        register_server_sudo_secret_provider,
    )
    from app.tools.server_tool_gateway import register_server_tool_gateway
    from app.tools.ssh_host_key_provider import register_ssh_host_key_provider
    from servers.pipeline_ssh_provider import DjangoPipelineSshProvider
    from servers.runtime_limit_provider import DjangoTerminalSessionLimitProvider
    from servers.secret_utils import get_server_auth_secret, get_server_sudo_secret
    from servers.ssh_host_keys import (
        ensure_server_known_hosts,
        parse_host_port_value,
        verified_known_hosts_for_host,
    )
    from servers.tool_gateway import DjangoServerToolGateway

    register_pipeline_ssh_provider(DjangoPipelineSshProvider())
    register_terminal_session_limit_provider(DjangoTerminalSessionLimitProvider())
    register_server_tool_gateway(DjangoServerToolGateway())
    register_server_auth_secret_provider(get_server_auth_secret)
    register_server_sudo_secret_provider(get_server_sudo_secret)
    register_ssh_host_key_provider(
        ensure_server_known_hosts=ensure_server_known_hosts,
        verified_known_hosts_for_host=verified_known_hosts_for_host,
        parse_host_port_value=parse_host_port_value,
    )
