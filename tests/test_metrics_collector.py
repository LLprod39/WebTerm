"""Tests for collector v2 script building and output parsing."""

from __future__ import annotations

from servers.monitoring.metrics_parsing import build_metrics_v2, split_sections
from servers.monitoring.metrics_script import build_metrics_script, section_marker

RAW_V2_OUTPUT = """==WT2:BEGIN==
==WT2:NPROC==
4
==WT2:UPTIME==
123456.78 400000.00
==WT2:CPU0==
cpu  100000 500 30000 800000 7000 0 2000 1000 0 0
==WT2:NET0==
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000 10 0 0 0 0 0 0 1000 10 0 0 0 0 0 0
  eth0: 5000000 4000 1 2 0 0 0 0 3000000 3500 0 1 0 0 0 0
==WT2:TCP0==
Tcp: RtoAlgorithm RtoMin RtoMax MaxConn ActiveOpens PassiveOpens AttemptFails EstabResets CurrEstab InSegs OutSegs RetransSegs InErrs OutRsts InCsumErrors
Tcp: 1 200 120000 -1 1000 2000 10 5 42 100000 90000 150 0 20 0
==WT2:CPU1==
cpu  100400 500 30100 801200 7050 0 2010 1010 0 0
==WT2:NET1==
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000 10 0 0 0 0 0 0 1000 10 0 0 0 0 0 0
  eth0: 5125000 4100 1 2 0 0 0 0 3062500 3600 0 1 0 0 0 0
==WT2:TCP1==
Tcp: RtoAlgorithm RtoMin RtoMax MaxConn ActiveOpens PassiveOpens AttemptFails EstabResets CurrEstab InSegs OutSegs RetransSegs InErrs OutRsts InCsumErrors
Tcp: 1 200 120000 -1 1001 2002 10 5 45 100500 90400 153 0 20 0
==WT2:LOAD==
1.20 0.80 0.60 2/345 12345
==WT2:MEM==
MemTotal:        8000000 kB
MemFree:         2000000 kB
MemAvailable:    4000000 kB
Buffers:          300000 kB
Cached:          1500000 kB
SwapTotal:       2000000 kB
SwapFree:        1500000 kB
Dirty:              1000 kB
Slab:             200000 kB
==WT2:DISK==
Filesystem     1024-blocks      Used Available Capacity Mounted on
/dev/sda1        102400000  51200000  46080000      53% /
/dev/sdb1        512000000 460800000  25600000      95% /var/lib/data
tmpfs              4000000         0   4000000       0% /dev/shm
==WT2:INODES==
Filesystem       Inodes    IUsed   IFree IUse% Mounted on
/dev/sda1       6553600   655360 5898240    10% /
/dev/sdb1      32768000 31457280 1310720    96% /var/lib/data
==WT2:FDS==
5344\t0\t9223372036854775807
==WT2:PROCS==
234
==WT2:ZOMBIES==
2
==WT2:TOPCPU==
 1234 45.5  2.1 postgres
 2345 12.0  1.0 nginx
==WT2:TOPMEM==
 1234 45.5 25.5 postgres
 3456  1.0 10.2 redis-server
==WT2:JERR==
7
==WT2:JWARN==
23
==WT2:REBOOT==
1
==WT2:NTP==
yes
==WT2:END==
"""


def test_build_metrics_script_is_single_line_with_markers():
    script = build_metrics_script()
    assert "\n" not in script
    assert section_marker("BEGIN") in script
    assert section_marker("END") in script
    for name in ("CPU0", "CPU1", "MEM", "DISK", "INODES", "JERR", "NTP"):
        assert section_marker(name) in script
    assert "sleep 1" in script


def test_split_sections_requires_markers():
    assert split_sections("") is None
    assert split_sections("Mem: 100 50") is None
    sections = split_sections(RAW_V2_OUTPUT)
    assert sections is not None
    assert sections["NPROC"] == ["4"]


def test_build_metrics_v2_full_parse():
    metrics = build_metrics_v2(RAW_V2_OUTPUT)
    assert metrics is not None
    assert metrics["collector_version"] == 2

    # CPU from dual /proc/stat deltas: busy 520/1770, iowait 50/1770, steal 10/1770.
    assert metrics["cpu_percent"] == 29.4
    assert metrics["cpu_iowait_percent"] == 2.8
    assert metrics["cpu_steal_percent"] == 0.6
    assert metrics["cpu_count"] == 4

    assert metrics["load_1m"] == 1.2
    assert metrics["load_5m"] == 0.8
    assert metrics["load_15m"] == 0.6
    assert metrics["uptime_seconds"] == 123456

    assert metrics["memory_total_mb"] == 7812
    assert metrics["memory_available_mb"] == 3906
    assert metrics["memory_used_mb"] == 3906
    assert metrics["memory_percent"] == 50.0
    assert metrics["swap_total_mb"] == 1953
    assert metrics["swap_used_mb"] == 488
    assert metrics["swap_percent"] == 25.0

    mounts = metrics["disk_mounts"]
    assert [item["mount"] for item in mounts] == ["/var/lib/data", "/"]
    assert mounts[0]["percent"] == 95.0
    assert mounts[0]["inode_percent"] == 96.0
    assert mounts[1]["inode_percent"] == 10.0
    # Legacy root-mount fields still present for ServerHealthCheck.
    assert metrics["disk_percent"] == 53.0
    assert metrics["disk_total_gb"] == 97.66
    assert metrics["disk_used_gb"] == 48.83

    assert metrics["net_rx_bytes"] == 5125000
    assert metrics["net_tx_bytes"] == 3062500
    assert metrics["net_rx_bps"] == 125000.0
    assert metrics["net_tx_bps"] == 62500.0
    assert metrics["net_errors_per_sec"] == 0.0
    assert metrics["tcp_established"] == 45
    assert metrics["tcp_retrans_per_sec"] == 3.0

    assert metrics["fd_used"] == 5344
    assert metrics["fd_max"] == 9223372036854775807
    assert metrics["process_count"] == 234
    assert metrics["zombie_count"] == 2

    top = metrics["top_processes"]
    assert top["by_cpu"][0] == {"pid": 1234, "cpu_percent": 45.5, "memory_percent": 2.1, "command": "postgres"}
    assert top["by_memory"][1]["command"] == "redis-server"

    assert metrics["journal_err_10m"] == 7
    assert metrics["journal_warn_10m"] == 23
    assert metrics["reboot_required"] is True
    assert metrics["ntp_synchronized"] is True


def test_build_metrics_v2_returns_none_without_markers():
    legacy_output = "0.5 0.4 0.3 1/100 200\nMem: 8000 4000 1000\n/dev/sda1 100G 50G 45G 53% /\n"
    assert build_metrics_v2(legacy_output) is None


def test_build_metrics_v2_cpu_fallback_from_load_and_nproc():
    raw = (
        "==WT2:BEGIN==\n"
        "==WT2:NPROC==\n4\n"
        "==WT2:LOAD==\n2.00 1.00 0.50 1/100 200\n"
        "==WT2:MEM==\nMemTotal: 1000000 kB\nMemAvailable: 500000 kB\n"
        "==WT2:END==\n"
    )
    metrics = build_metrics_v2(raw)
    assert metrics is not None
    assert metrics["cpu_percent"] == 50.0
    assert metrics["memory_percent"] == 50.0


def test_build_metrics_v2_requires_core_sections():
    raw = "==WT2:BEGIN==\n==WT2:NPROC==\n4\n==WT2:END==\n"
    assert build_metrics_v2(raw) is None


def test_build_metrics_v2_ntp_key_value_form():
    raw = "==WT2:BEGIN==\n==WT2:LOAD==\n0.10 0.10 0.10 1/50 100\n==WT2:NTP==\nNTPSynchronized=yes\n==WT2:END==\n"
    metrics = build_metrics_v2(raw)
    assert metrics is not None
    assert metrics["ntp_synchronized"] is True
