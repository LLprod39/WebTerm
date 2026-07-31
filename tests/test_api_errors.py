from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.db import DataError
from django.test import RequestFactory
from loguru import logger

from core_ui.models.audit import UserActivityLog
from servers.models_inventory import Server
from servers.views.server_crud import server_create

pytestmark = pytest.mark.django_db(transaction=True)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PACKAGES = ("app", "core_ui", "kubernetes_ops", "plugin_marketplace", "servers", "studio", "web_ui")


def test_server_create_data_error_uses_safe_contract_and_safe_activity(monkeypatch):
    user = User.objects.create_superuser(username="api-error-admin", password="x", email="admin@example.com")
    request = RequestFactory().post(
        "/servers/api/create/",
        data=json.dumps(
            {
                "name": "database-overflow",
                "host": "db.internal",
                "port": 22,
                "username": "ops",
                "auth_method": "password",
            }
        ),
        content_type="application/json",
    )
    request.user = user
    request.request_id = "request-data-error-123"
    leaked_detail = 'value too long for type character varying(200) in table "servers_server" column "name"'

    def raise_data_error(*_args, **_kwargs):
        raise DataError(leaked_detail)

    monkeypatch.setattr(Server.objects, "create", raise_data_error)
    log_lines: list[str] = []
    sink_id = logger.add(log_lines.append, format="{message}|{extra[request_id]}|{exception}")
    try:
        response = server_create(request)
    finally:
        logger.remove(sink_id)

    payload = json.loads(response.content)
    assert response.status_code == 500
    assert payload == {
        "success": False,
        "error": "An internal error occurred. Please retry or contact support.",
        "code": "internal_error",
        "request_id": "request-data-error-123",
    }
    assert response["X-Request-ID"] == "request-data-error-123"
    assert leaked_detail not in response.content.decode("utf-8")
    assert any("request-data-error-123" in line and "DataError" in line for line in log_lines)
    activity = UserActivityLog.objects.get(user=user, action="server_create", status=UserActivityLog.STATUS_ERROR)
    assert activity.description == "Server create failed (internal_error)"
    assert "servers_server" not in activity.description


def test_no_json_5xx_response_interpolates_caught_exception():
    findings: list[str] = []
    for package in PRODUCTION_PACKAGES:
        for path in (REPOSITORY_ROOT / package).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and node.name):
                for call in (node for node in ast.walk(handler) if isinstance(node, ast.Call)):
                    if not isinstance(call.func, ast.Name) or call.func.id != "JsonResponse":
                        continue
                    status = next(
                        (
                            keyword.value.value
                            for keyword in call.keywords
                            if keyword.arg == "status"
                            and isinstance(keyword.value, ast.Constant)
                            and isinstance(keyword.value.value, int)
                        ),
                        None,
                    )
                    if status is None or status < 500:
                        continue
                    if any(isinstance(node, ast.Name) and node.id == handler.name for node in ast.walk(call)):
                        findings.append(f"{path.relative_to(REPOSITORY_ROOT)}:{call.lineno}")

    assert findings == []
