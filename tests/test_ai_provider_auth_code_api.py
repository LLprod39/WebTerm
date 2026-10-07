from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from core_ui.models import UserAppPermission
from core_ui.models.ai_providers import AIConnectionAuthFlow, AIProviderConnection

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _enable_ai_cli_provider_api(monkeypatch):
    monkeypatch.setenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "true")


def _personal_antigravity(user: User) -> AIProviderConnection:
    UserAppPermission.objects.update_or_create(user=user, feature="settings", defaults={"allowed": True})
    UserAppPermission.objects.update_or_create(user=user, feature="ai_connections_personal", defaults={"allowed": True})
    return AIProviderConnection.objects.create(
        target_id="antigravity_subscription",
        scope="personal",
        owner=user,
        name="ANTI",
        status=AIProviderConnection.STATUS_AUTH_REQUIRED,
        credential_ref="connection_4e8e2587f6dd43d893a0044f0235b0a9",
        created_by=user,
    )


def test_authorization_code_requires_owner_and_pending_antigravity(client, monkeypatch) -> None:
    owner = User.objects.create_user("anti-owner", password="pw")
    stranger = User.objects.create_user("anti-stranger", password="pw")
    UserAppPermission.objects.update_or_create(user=stranger, feature="settings", defaults={"allowed": True})
    UserAppPermission.objects.update_or_create(
        user=stranger, feature="ai_connections_personal", defaults={"allowed": True}
    )
    connection = _personal_antigravity(owner)
    flow = AIConnectionAuthFlow.objects.create(
        connection=connection,
        verification_uri="https://accounts.google.com/o/oauth2/auth?client_id=1&scope=openid",
    )

    client.force_login(stranger)
    denied = client.post(
        f"/api/ai/providers/auth-flows/{flow.public_id}/authorization-code/",
        data='{"authorization_code":"4/0AXlqoi5-TESTCODEVALUE"}',
        content_type="application/json",
    )
    assert denied.status_code == 403

    captured: dict[str, str] = {}

    async def fake_submit(
        self,
        invocation_id: str,
        authorization_code: str,
        *,
        oauth_state: str = "",
    ) -> bool:
        captured["invocation_id"] = invocation_id
        captured["code"] = authorization_code
        captured["oauth_state"] = oauth_state
        return True

    monkeypatch.setattr(
        "app.core.ai_cli_runner_client.AiCliRunnerClient.submit_auth_input",
        fake_submit,
    )

    client.force_login(owner)
    accepted = client.post(
        f"/api/ai/providers/auth-flows/{flow.public_id}/authorization-code/",
        data='{"authorization_code":"4/0AXlqoi5-TESTCODEVALUE"}',
        content_type="application/json",
    )
    assert accepted.status_code == 202
    assert accepted.json()["accepted"] is True
    assert captured["invocation_id"] == f"auth_{flow.public_id.hex}"
    assert captured["code"] == "4/0AXlqoi5-TESTCODEVALUE"

    # Code must not be persisted on the flow row.
    flow.refresh_from_db()
    assert "4/0AXlqoi5" not in flow.user_code
    assert "4/0AXlqoi5" not in flow.verification_uri
    assert "4/0AXlqoi5" not in flow.error_code


def test_authorization_code_rejected_without_verification_uri(client) -> None:
    owner = User.objects.create_user("anti-owner-2", password="pw")
    connection = _personal_antigravity(owner)
    flow = AIConnectionAuthFlow.objects.create(connection=connection, verification_uri="")
    client.force_login(owner)
    response = client.post(
        f"/api/ai/providers/auth-flows/{flow.public_id}/authorization-code/",
        data='{"authorization_code":"4/0AXlqoi5-TESTCODEVALUE"}',
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "provider_auth_not_ready"


def test_authorization_code_session_not_ready_is_actionable(client, monkeypatch) -> None:
    owner = User.objects.create_user("anti-owner-3", password="pw")
    connection = _personal_antigravity(owner)
    flow = AIConnectionAuthFlow.objects.create(
        connection=connection,
        verification_uri="https://accounts.google.com/o/oauth2/auth?client_id=1&scope=openid",
    )

    async def fake_submit(
        self,
        invocation_id: str,
        authorization_code: str,
        *,
        oauth_state: str = "",
    ) -> bool:
        return False

    monkeypatch.setattr(
        "app.core.ai_cli_runner_client.AiCliRunnerClient.submit_auth_input",
        fake_submit,
    )
    client.force_login(owner)
    response = client.post(
        f"/api/ai/providers/auth-flows/{flow.public_id}/authorization-code/",
        data='{"authorization_code":"4/0AXlqoi5-TESTCODEVALUE"}',
        content_type="application/json",
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "provider_auth_session_not_ready"
    assert "expired" in body["error"].lower()
