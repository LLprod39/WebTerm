from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group
from django.test import override_settings

from core_ui.ldap_login import PILOT_GROUP_FEATURES, _ldap_connect, ensure_pilot_group_permissions
from core_ui.models import GroupAppPermission


@override_settings(
    AUTH_LDAP_SERVER_URI="ldap://directory.example.test:389",
    LDAP_NETWORK_TIMEOUT_SECONDS=4,
    LDAP_CA_CERT_FILE="",
    LDAP_CA_CERT_DIR="",
    LDAP_IGNORE_CERT=False,
    LDAP_START_TLS=True,
)
def test_ldap_connect_starts_tls(monkeypatch):
    class FakeConnection:
        def __init__(self):
            self.options = []
            self.started_tls = False

        def set_option(self, option, value):
            self.options.append((option, value))

        def start_tls_s(self):
            self.started_tls = True

    connection = FakeConnection()
    fake_ldap = SimpleNamespace(
        OPT_REFERRALS=1,
        OPT_NETWORK_TIMEOUT=2,
        OPT_TIMEOUT=3,
        OPT_X_TLS_CACERTFILE=4,
        OPT_X_TLS_CACERTDIR=5,
        OPT_X_TLS_REQUIRE_CERT=6,
        OPT_X_TLS_NEVER=7,
        OPT_X_TLS_DEMAND=8,
        OPT_X_TLS_NEWCTX=9,
        initialize=lambda uri: connection,
    )
    monkeypatch.setitem(sys.modules, "ldap", fake_ldap)

    result = _ldap_connect()

    assert result is connection
    assert connection.started_tls is True
    assert (fake_ldap.OPT_X_TLS_REQUIRE_CERT, fake_ldap.OPT_X_TLS_DEMAND) in connection.options


@pytest.mark.django_db
def test_pilot_group_permissions_are_reconciled_to_the_exact_managed_policy():
    group = Group.objects.create(name="managed-pilot-test")
    GroupAppPermission.objects.create(group=group, feature="automation", allowed=False)
    GroupAppPermission.objects.create(group=group, feature="knowledge_base", allowed=True)
    GroupAppPermission.objects.create(group=group, feature="orchestrator", allowed=True)

    reconciled = ensure_pilot_group_permissions(group)

    assert reconciled == group
    assert not Group.objects.filter(name="pilot").exists()
    permissions = dict(group.app_permissions.values_list("feature", "allowed"))
    assert {feature for feature, allowed in permissions.items() if allowed} == set(PILOT_GROUP_FEATURES)
    assert permissions["automation"] is True
    assert permissions["chat"] is True
    assert permissions["knowledge_base"] is False
    assert permissions["orchestrator"] is False
