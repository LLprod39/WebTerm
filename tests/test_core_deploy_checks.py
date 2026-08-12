from django.conf import settings
from django.test import override_settings

from core_ui.checks import production_database_deploy_check, trusted_proxy_hops_deploy_check

_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


def test_production_database_deploy_check_rejects_sqlite(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(
        settings,
        "DATABASES",
        {"default": {"ENGINE": "django.db.backends.sqlite3"}},
    )

    errors = production_database_deploy_check(None)

    assert [error.id for error in errors] == ["core_ui.E006"]


def test_production_database_deploy_check_accepts_postgres(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(
        settings,
        "DATABASES",
        {"default": {"ENGINE": "django.db.backends.postgresql"}},
    )

    assert production_database_deploy_check(None) == []


@override_settings(DEBUG=False, SECURE_PROXY_SSL_HEADER=_PROXY_SSL_HEADER, TRUSTED_PROXY_HOPS=0)
def test_trusted_proxy_hops_check_flags_proxy_trusted_for_scheme_but_not_for_ip():
    warnings = trusted_proxy_hops_deploy_check(None)

    assert [warning.id for warning in warnings] == ["core_ui.W001"]


@override_settings(DEBUG=False, SECURE_PROXY_SSL_HEADER=_PROXY_SSL_HEADER, TRUSTED_PROXY_HOPS=1)
def test_trusted_proxy_hops_check_accepts_a_configured_hop_count():
    assert trusted_proxy_hops_deploy_check(None) == []


@override_settings(DEBUG=False, SECURE_PROXY_SSL_HEADER=None, TRUSTED_PROXY_HOPS=0)
def test_trusted_proxy_hops_check_ignores_deployments_without_a_trusted_proxy():
    assert trusted_proxy_hops_deploy_check(None) == []
