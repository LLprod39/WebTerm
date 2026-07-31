from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.django_db
def test_all_public_inventory_json_routes_return_stable_envelope(client):
    inventory = json.loads(Path("config/public-api-v0.1.json").read_text(encoding="utf-8"))
    for route in inventory["routes"]:
        if route.get("response", "json") != "json" or "<" in route["path"]:
            continue
        method = route["methods"][0].lower()
        kwargs = {"content_type": "application/json"} if method in {"post", "put", "patch"} else {}
        if method in {"post", "put", "patch"}:
            kwargs["data"] = "{}"
        response = getattr(client, method)(route["path"], **kwargs)
        assert response.status_code != 500, route["name"]
        assert response["Content-Type"].startswith("application/json"), route["name"]
        payload = response.json()
        assert isinstance(payload["success"], bool), route["name"]
        assert isinstance(payload["code"], str) and payload["code"], route["name"]
        assert ("data" in payload) if payload["success"] else ("error" in payload), route["name"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "expected_type"),
    [
        ("x" * 201, "string_too_long"),
        ({"nested": 1}, "string_type"),
    ],
)
def test_http_boundary_rejects_invalid_name_with_field_details(client, name, expected_type):
    response = client.post(
        "/servers/api/create/",
        data=json.dumps({"name": name}),
        content_type="application/json",
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"
    assert payload["details"][0]["field"] == "name"
    assert payload["details"][0]["type"] == expected_type


@pytest.mark.django_db
def test_api_login_redirect_is_normalized_to_json_401(client):
    response = client.get("/servers/api/frontend/bootstrap/")
    assert response.status_code == 401
    assert response.json() == {
        "success": False,
        "error": "Authentication required",
        "code": "authentication_required",
    }


@pytest.mark.django_db
def test_api_envelope_preserves_csrf_cookie(client):
    response = client.get("/api/auth/csrf/")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.cookies["csrftoken"].value
