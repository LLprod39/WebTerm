from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.sudo_policy import enforce_non_interactive_sudo, evaluate_sudo_command, prepare_sudo_command


def _ssh_spec() -> ToolSpec:
    return ToolSpec(
        name="ssh_execute",
        category="ssh",
        risk="exec",
        description="Execute SSH command",
        input_schema={},
        requires_verification=True,
    )


def _server_execute_spec() -> ToolSpec:
    return ToolSpec(
        name="server_execute",
        category="ssh",
        risk="exec",
        description="Execute command on saved server",
        input_schema={},
        requires_verification=True,
    )


def test_sudo_policy_blocks_sudo_by_default():
    engine = PermissionEngine(mode="SAFE")

    decision = engine.evaluate(_ssh_spec(), {"command": "sudo systemctl status nginx"})

    assert not decision.allowed
    assert decision.requires_approval
    assert "Sudo" in decision.reason


def test_sudo_policy_blocks_server_execute_sudo_by_default():
    engine = PermissionEngine(mode="SAFE")

    decision = engine.evaluate(_server_execute_spec(), {"command": "sudo systemctl status nginx"})

    assert not decision.allowed
    assert decision.requires_approval
    assert "Sudo" in decision.reason


def test_sudo_policy_ask_blocks_until_operator_approval():
    decision = evaluate_sudo_command("sudo systemctl restart nginx", "ask")

    assert not decision.allowed
    assert decision.requires_approval
    assert "требует sudo" in decision.reason


def test_sudo_policy_approved_adds_non_interactive_flag():
    command, notes = enforce_non_interactive_sudo("sudo systemctl restart nginx", "approved")

    assert command == "sudo -n systemctl restart nginx"
    assert notes == ("sudo_non_interactive_added",)


def test_sudo_policy_rejects_stdin_password_mode():
    decision = evaluate_sudo_command("printf secret | sudo -S systemctl restart nginx", "approved")

    assert not decision.allowed
    assert "stdin" in decision.reason


def test_sudo_policy_stored_password_uses_backend_stdin_wrapper():
    prepared = prepare_sudo_command(
        "sudo systemctl restart nginx",
        "approved",
        sudo_auth_mode="stored_password",
        sudo_password="secret",
    )

    assert prepared.command == "sudo -S -p '' systemctl restart nginx"
    assert prepared.input_text == "secret\n"
    assert prepared.notes == ("sudo_password_stdin_used",)


def test_sudo_policy_stored_password_strips_noninteractive_flag():
    prepared = prepare_sudo_command(
        "sudo -n systemctl restart nginx",
        "approved",
        sudo_auth_mode="stored_password",
        sudo_password="secret",
    )

    assert prepared.command == "sudo -S -p '' systemctl restart nginx"
