"""Tests for the TLS certificate collector (script, parsing, upsert)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.contrib.auth.models import User

from servers.cert_collector import build_cert_script, parse_cert_output, upsert_certificates
from servers.models import Server, ServerCertificate

RAW_CERT_OUTPUT = """==WTCERT:443==
subject=CN = api.example.com
issuer=C = US, O = Example CA, CN = R3
serial=04A1B2C3
notBefore=May 20 00:00:00 2026 GMT
notAfter=Aug 18 23:59:59 2026 GMT
sha256 Fingerprint=AA:BB:CC:DD
X509v3 Subject Alternative Name:
    DNS:api.example.com, DNS:www.example.com, IP Address:10.0.0.5
==WTCERT:8443==
subject=CN = internal
issuer=CN = internal-ca
serial=99
notBefore=Jan  2 12:00:00 2026 GMT
notAfter=Jan  2 12:00:00 2027 GMT
SHA256 Fingerprint=EE:FF:00:11
==WTCERT:END==
"""


def test_build_cert_script_contains_sni_and_excludes_ssh_port():
    script = build_cert_script("api.example.com", 2222)
    assert "SNI=api.example.com" in script
    assert "SSHP=2222" in script
    assert "servername" in script
    assert "==WTCERT:END==" in script
    assert "\n" not in script


def test_parse_cert_output_extracts_fields():
    certs, completed = parse_cert_output(RAW_CERT_OUTPUT)
    assert completed is True
    assert len(certs) == 2

    first = certs[0]
    assert first["port"] == 443
    assert first["subject"] == "CN = api.example.com"
    assert first["issuer"] == "C = US, O = Example CA, CN = R3"
    assert first["serial"] == "04A1B2C3"
    assert first["fingerprint_sha256"] == "AA:BB:CC:DD"
    assert first["not_before"] == datetime(2026, 5, 20, 0, 0, 0, tzinfo=UTC)
    assert first["not_after"] == datetime(2026, 8, 18, 23, 59, 59, tzinfo=UTC)
    assert first["sans"] == ["api.example.com", "www.example.com", "10.0.0.5"]

    second = certs[1]
    assert second["port"] == 8443
    assert second["not_after"] == datetime(2027, 1, 2, 12, 0, 0, tzinfo=UTC)
    assert second["sans"] == []


def test_parse_cert_output_incomplete_scan():
    certs, completed = parse_cert_output("==WTCERT:443==\nsubject=CN = x\n")
    assert len(certs) == 1
    assert completed is False


def test_parse_cert_output_no_openssl():
    certs, completed = parse_cert_output("==WTCERT:NOOPENSSL==\n==WTCERT:END==\n")
    assert certs == []
    assert completed is False


@pytest.mark.django_db
def test_upsert_certificates_lifecycle():
    owner = User.objects.create_user(username="cert-owner", password="x")
    server = Server.objects.create(
        user=owner,
        name="cert-srv",
        host="api.example.com",
        username="root",
        server_type="ssh",
        is_active=True,
    )
    certs, completed = parse_cert_output(RAW_CERT_OUTPUT)

    summary = upsert_certificates(server, certs, scan_completed=completed)
    assert summary["created"] == 2
    assert summary["changed"] == 0
    row = ServerCertificate.objects.get(server=server, port=443)
    assert row.endpoint == "api.example.com:443"
    assert row.is_active is True
    assert row.fingerprint_sha256 == "AA:BB:CC:DD"

    # Same cert again: update, no change detection.
    summary = upsert_certificates(server, certs, scan_completed=True)
    assert summary["created"] == 0
    assert summary["updated"] == 2
    assert summary["changed"] == 0

    # Rotated cert on 443, port 8443 vanished -> change recorded, 8443 deactivated.
    rotated = [dict(certs[0], fingerprint_sha256="11:22:33:44")]
    summary = upsert_certificates(server, rotated, scan_completed=True)
    assert summary["changed"] == 1
    assert summary["deactivated"] == 1
    row.refresh_from_db()
    assert row.fingerprint_sha256 == "11:22:33:44"
    assert row.previous_fingerprint == "AA:BB:CC:DD"
    assert row.fingerprint_changed_at is not None
    gone = ServerCertificate.objects.get(server=server, port=8443)
    assert gone.is_active is False

    # Incomplete scan must not deactivate anything.
    summary = upsert_certificates(server, [], scan_completed=False)
    assert summary["deactivated"] == 0
    assert ServerCertificate.objects.filter(server=server, is_active=True).count() == 1
