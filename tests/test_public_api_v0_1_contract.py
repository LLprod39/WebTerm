import json
from pathlib import Path

from django.urls import resolve, reverse

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_METHODS = {"DELETE", "GET", "PATCH", "POST", "PUT"}


def _inventory():
    return json.loads((ROOT / "config/public-api-v0.1.json").read_text(encoding="utf-8"))


def test_public_api_inventory_has_unique_complete_operations():
    inventory = _inventory()
    assert inventory["version"] == "0.1.0"
    routes = inventory["routes"]
    assert len(routes) == 9
    assert len({route["name"] for route in routes}) == len(routes)
    assert len({route["path"] for route in routes}) == len(routes)
    for route in routes:
        assert route["path"].startswith("/") and route["path"].endswith("/")
        assert route["methods"] and set(route["methods"]) <= ALLOWED_METHODS
        assert route["access"]
        assert route["view"]


def test_public_api_route_names_paths_and_views_do_not_drift():
    for route in _inventory()["routes"]:
        assert reverse(route["name"]) == route["path"]
        match = resolve(route["path"])
        assert match.view_name == route["name"]
        assert f"{match.func.__module__}.{match.func.__name__}" == route["view"]
