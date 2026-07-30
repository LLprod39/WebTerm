from __future__ import annotations

import json

from scripts import check_kubernetes_ops_v01_scope as scope_check


def _manifest() -> dict[str, object]:
    return json.loads(scope_check.MANIFEST_PATH.read_text(encoding="utf-8"))


def test_kubernetes_ops_v01_scope_matches_repository() -> None:
    assert scope_check.check_scope(_manifest()) == []


def test_kubernetes_ops_v01_route_snapshot_is_frozen() -> None:
    manifest = _manifest()
    routes = scope_check.route_surface()

    assert len(routes) == manifest["route_count"]
    assert scope_check.route_digest(routes) == manifest["route_sha256"]


def test_kubernetes_ops_v01_scope_rejects_route_drift(monkeypatch) -> None:
    routes = scope_check.route_surface()
    routes.append({"name": "unreviewed-mutation", "route": "mutate/"})
    monkeypatch.setattr(scope_check, "route_surface", lambda: routes)

    errors = scope_check.check_scope(_manifest())

    assert any("route surface changed" in error for error in errors)
    assert any("route surface digest changed" in error for error in errors)


def test_kubernetes_ops_v01_scope_rejects_enabled_runtime_default(monkeypatch) -> None:
    defaults = scope_check.env_bool_defaults()
    defaults["KUBERNETES_ADMIN_MODE_ENABLED"] = True
    monkeypatch.setattr(scope_check, "env_bool_defaults", lambda: defaults)

    errors = scope_check.check_scope(_manifest())

    assert "KUBERNETES_ADMIN_MODE_ENABLED must be declared with a false runtime default" in errors
