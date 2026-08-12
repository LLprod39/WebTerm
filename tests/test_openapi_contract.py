import json
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

from core_ui.schemas.openapi import build_openapi_document, django_api_route_inventory, validate_openapi_routes


@pytest.mark.django_db
def test_published_openapi_is_generated_from_pydantic_and_matches_routes():
    document = build_openapi_document()
    validate_openapi_routes(document)

    assert document["openapi"] == "3.1.0"
    assert set(document["paths"]) == set(django_api_route_inventory())
    transfer = document["paths"]["/servers/api/{server_id}/transfer-owner/"]["post"]
    transfer_media = transfer["requestBody"]["content"]["application/json"]
    assert transfer_media["schema"]["$ref"].endswith("/ServerOwnershipTransferSchema")
    assert transfer_media["example"] == {"target_user_id": 42}
    resume = document["paths"]["/api/studio/runs/{run_id}/resume/"]["post"]
    assert resume["requestBody"]["content"]["application/json"]["example"] == {"confirm_non_idempotent": False}
    auth = document["paths"]["/api/ai/providers/connections/{connection_id}/auth/"]["post"]
    verify = document["paths"]["/api/ai/providers/connections/{connection_id}/verify/"]["post"]
    for operation in (auth, verify):
        assert "200" not in operation["responses"]
        assert {"202", "404"} <= set(operation["responses"])
    ready = document["paths"]["/api/ready/"]["get"]
    assert ready["responses"]["503"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ReadinessResponse"
    }
    readiness_schema = document["components"]["schemas"]["ReadinessResponse"]
    assert "components" in readiness_schema["required"]


def test_committed_openapi_document_matches_generator():
    expected = build_openapi_document()
    published = json.loads((Path(settings.BASE_DIR) / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert published == expected


def test_openapi_endpoint_returns_raw_schema_without_api_envelope():
    response = Client().get("/api/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"] == "3.1.0"
    assert "data" not in payload
