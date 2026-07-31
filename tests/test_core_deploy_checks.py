from django.test import override_settings

from core_ui.checks import production_database_deploy_check


@override_settings(DEBUG=False, DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}})
def test_production_database_deploy_check_rejects_sqlite():
    errors = production_database_deploy_check(None)

    assert [error.id for error in errors] == ["core_ui.E006"]


@override_settings(DEBUG=False, DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}})
def test_production_database_deploy_check_accepts_postgres():
    assert production_database_deploy_check(None) == []
