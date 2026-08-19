from __future__ import annotations

import sys
from types import SimpleNamespace

from django.test import override_settings

from core_ui.ldap_login import _ldap_connect


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
