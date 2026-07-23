"""Tests for servers.os_detect parser and mapping."""

from servers.os_detect import map_to_os_kind, parse_os_release


def test_parse_os_release_basic():
    raw = """
NAME="Ubuntu"
VERSION="22.04.5 LTS (Jammy Jellyfish)"
ID=ubuntu
ID_LIKE=debian
PRETTY_NAME="Ubuntu 22.04.5 LTS"
VERSION_ID="22.04"
"""
    parsed = parse_os_release(raw)
    assert parsed["ID"] == "ubuntu"
    assert parsed["ID_LIKE"] == "debian"
    assert "22.04" in parsed["VERSION_ID"]


def test_map_ubuntu():
    parsed = parse_os_release('ID=ubuntu\nPRETTY_NAME="Ubuntu 24.04 LTS"\nVERSION_ID="24.04"')
    kind, meta = map_to_os_kind(parsed, uname="Linux host 6.8.0 x86_64 GNU/Linux")
    assert kind == "ubuntu"
    assert meta["pretty_name"] == "Ubuntu 24.04 LTS"


def test_map_debian_from_id_like():
    parsed = parse_os_release('ID=debian\nPRETTY_NAME="Debian GNU/Linux 12 (bookworm)"')
    kind, _meta = map_to_os_kind(parsed)
    assert kind == "debian"


def test_map_rocky():
    parsed = parse_os_release('ID="rocky"\nPRETTY_NAME="Rocky Linux 9.4 (Green Obsidian)"')
    kind, _meta = map_to_os_kind(parsed)
    assert kind == "rocky"


def test_map_amazon():
    parsed = parse_os_release('ID="amzn"\nPRETTY_NAME="Amazon Linux 2023"')
    kind, _meta = map_to_os_kind(parsed)
    assert kind == "amazon"


def test_map_freebsd_uname():
    kind, meta = map_to_os_kind({}, uname="FreeBSD host 14.1-RELEASE FreeBSD amd64")
    assert kind == "freebsd"
    assert meta["uname"]


def test_map_unknown_empty():
    kind, _meta = map_to_os_kind({})
    assert kind == "unknown"
