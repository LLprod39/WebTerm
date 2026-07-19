"""Pilot sidebar flag waives production-only release checks."""

from __future__ import annotations

import pytest
from django.test import override_settings

from kubernetes_ops.services.readiness import build_kubernetes_readiness_report


@pytest.mark.django_db
@override_settings(KUBERNETES_OPS_PILOT_SIDEBAR=True, KUBERNETES_OPS_READY_FOR_SIDEBAR=False)
def test_pilot_sidebar_waives_production_scope_required():
    report = build_kubernetes_readiness_report()
    assert report.get("pilot_sidebar") is True
    assert report.get("summary", {}).get("pilot_sidebar") is True
    scope = next(c for c in report["checks"] if c["id"] == "sidebar_release_scope")
    assert scope["required"] is False
    # Without READY_FOR_SIDEBAR env, sidebar stays off even in pilot.
    assert report["ready_for_sidebar"] is False


@pytest.mark.django_db
@override_settings(KUBERNETES_OPS_PILOT_SIDEBAR=False, KUBERNETES_OPS_READY_FOR_SIDEBAR=False)
def test_production_scope_required_without_pilot():
    report = build_kubernetes_readiness_report()
    assert report.get("pilot_sidebar") is False
    scope = next(c for c in report["checks"] if c["id"] == "sidebar_release_scope")
    assert scope["required"] is True
