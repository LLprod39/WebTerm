from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import Client

from tests.studio_pipeline_v2_harness import json_payload, report_node

Pipeline = django_apps.get_model("studio", "Pipeline", require_ready=False)
PipelineRun = django_apps.get_model("studio", "PipelineRun", require_ready=False)
PipelineWebhookDelivery = django_apps.get_model("studio", "PipelineWebhookDelivery", require_ready=False)


def _webhook_pipeline(username: str, *, signing_secret: str = ""):
    user = User.objects.create_user(username=username, password="x")
    pipeline = Pipeline.objects.create(
        name=f"{username} webhook",
        owner=user,
        nodes=[
            {
                "id": "webhook",
                "type": "trigger/webhook",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Webhook", "webhook_payload_map": {"ref": "git.ref"}},
            },
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "webhook", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(trigger_type="webhook")
    trigger.signing_secret = signing_secret
    trigger.save(update_fields=["signing_secret"])
    return pipeline, trigger


def _signature(secret: str, timestamp: int, body: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("ascii") + body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


@pytest.mark.django_db
def test_delivery_id_is_idempotent_and_header_token_is_supported(monkeypatch):
    _pipeline, trigger = _webhook_pipeline("webhook-idempotent")
    monkeypatch.setattr("studio.views.pipeline_helpers._launch_pipeline_run_async", lambda _run: None)
    client = Client()
    body = json_payload({"git": {"ref": "refs/heads/main"}})
    headers = {
        "HTTP_X_WEBTERM_TRIGGER_TOKEN": trigger.webhook_token,
        "HTTP_X_WEBTERM_DELIVERY_ID": "delivery-42",
    }

    first = client.post("/api/studio/triggers/receive/", data=body, content_type="application/json", **headers)
    second = client.post("/api/studio/triggers/receive/", data=body, content_type="application/json", **headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["data"] == {"ok": True, "run_id": first.json()["run_id"], "duplicate": True}
    assert PipelineRun.objects.filter(trigger=trigger).count() == 1
    assert PipelineWebhookDelivery.objects.filter(trigger=trigger).count() == 1


@pytest.mark.django_db
def test_body_hash_is_fallback_delivery_id_and_url_token_is_deprecated(monkeypatch):
    _pipeline, trigger = _webhook_pipeline("webhook-hash-fallback")
    monkeypatch.setattr("studio.views.pipeline_helpers._launch_pipeline_run_async", lambda _run: None)
    client = Client()
    body = json_payload({"git": {"ref": "refs/heads/release"}})
    url = f"/api/studio/triggers/{trigger.webhook_token}/receive/"

    first = client.post(url, data=body, content_type="application/json")
    second = client.post(url, data=body, content_type="application/json")

    assert first.status_code == 200
    assert first.headers["Deprecation"] == "true"
    assert "successor-version" in first.headers["Link"]
    assert second.json()["duplicate"] is True
    assert second.json()["run_id"] == first.json()["run_id"]


@pytest.mark.django_db
def test_hmac_signature_and_timestamp_are_verified(monkeypatch):
    secret = "webhook-signing-secret"
    _pipeline, trigger = _webhook_pipeline("webhook-signature", signing_secret=secret)
    monkeypatch.setattr("studio.views.pipeline_helpers._launch_pipeline_run_async", lambda _run: None)
    client = Client()
    body = json_payload({"git": {"ref": "refs/heads/signed"}})
    url = "/api/studio/triggers/receive/"
    base_headers = {
        "HTTP_X_WEBTERM_TRIGGER_TOKEN": trigger.webhook_token,
        "HTTP_X_WEBTERM_DELIVERY_ID": "signed-delivery",
    }

    missing = client.post(url, data=body, content_type="application/json", **base_headers)
    assert missing.status_code == 401

    stale_timestamp = int(time.time()) - 3600
    stale = client.post(
        url,
        data=body,
        content_type="application/json",
        HTTP_X_WEBTERM_TIMESTAMP=str(stale_timestamp),
        HTTP_X_WEBTERM_SIGNATURE=_signature(secret, stale_timestamp, body),
        **base_headers,
    )
    assert stale.status_code == 401

    timestamp = int(time.time())
    accepted = client.post(
        url,
        data=body,
        content_type="application/json",
        HTTP_X_WEBTERM_TIMESTAMP=str(timestamp),
        HTTP_X_WEBTERM_SIGNATURE=_signature(secret, timestamp, body),
        **base_headers,
    )
    assert accepted.status_code == 200
    assert PipelineRun.objects.filter(trigger=trigger).count() == 1
