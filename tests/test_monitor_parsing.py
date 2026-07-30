"""Unit tests for server monitor quick-output parsing (CPU calculation)."""

from __future__ import annotations

from servers.monitoring.monitor_parsing import (
    _cpu_percent_from_load,
    _get_cpu_estimate,
    _parse_quick_output,
    cpu_percent_from_stat_ticks,
)


def test_cpu_percent_from_stat_ticks_basic():
    # total +100, idle +80 → 20% busy
    assert cpu_percent_from_stat_ticks(0, 0, 100, 80) == 20.0
    assert cpu_percent_from_stat_ticks(100, 80, 100, 80) is None


def test_cpu_percent_from_load_normalizes_by_cores():
    # load 2.91 on 4 cores ≈ 72.8%, not 100%
    assert _cpu_percent_from_load(2.91, 4) == 72.8
    # load 2.91 with the old bug (1 core) would cap at 100
    assert _cpu_percent_from_load(2.91, 1) == 100.0
    assert _cpu_percent_from_load(0.5, 4) == 12.5


def test_parse_quick_prefers_proc_stat_over_loadavg():
    # Synthetic /proc/stat: total 100→200, idle 90→170 → delta_idle/delta_total=0.8 → 20% busy.
    # Load would wrongly imply high CPU; parser must prefer /proc/stat.
    raw = "\n".join(
        [
            "CPUSTAT1=cpu  10 0 0 90 0 0 0 0",
            "CPUSTAT2=cpu  30 0 0 170 0 0 0 0",
            "NPROC=8",
            "2.91 1.50 1.00 1/200 12345",
            "Mem:  16000 4000 200 0 0 12000",
            "/dev/sda1  100G  40G  60G  40% /",
            "123456.78 999999.99",
            "150",
            "NET_RX_BYTES=1000",
            "NET_TX_BYTES=2000",
        ]
    )
    parsed = _parse_quick_output(raw)
    assert parsed["cpu_percent"] == 20.0
    assert parsed["cpu_source"] == "proc_stat"
    assert parsed["cpu_count"] == 8
    assert parsed["load_1m"] == 2.91
    assert parsed["memory_percent"] == 25.0
    assert parsed["disk_percent"] == 40.0
    assert parsed["process_count"] == 150
    assert parsed["net_rx_bytes"] == 1000


def test_parse_quick_loadavg_fallback_uses_nproc():
    """Without CPUSTAT samples, load is normalized by NPROC (not hard-coded 1 core)."""
    raw = "\n".join(
        [
            "NPROC=4",
            "2.00 1.50 1.00 1/200 12345",
            "Mem:  8000 2000 100 0 0 5000",
            "/dev/sda1  50G  10G  40G  20% /",
            "1000.0 2000.0",
            "80",
        ]
    )
    parsed = _parse_quick_output(raw)
    assert parsed["cpu_count"] == 4
    assert parsed["cpu_percent"] == 50.0  # 2.0 / 4 * 100
    assert parsed["cpu_source"] == "loadavg"
    assert _get_cpu_estimate(parsed) == 4


def test_legacy_output_without_nproc_still_parses():
    """Old monitor output without NPROC/CPUSTAT keeps working (1-core load fallback)."""
    raw = "\n".join(
        [
            "0.25 0.20 0.15 1/100 1",
            "Mem:  4000 1000 500 0 0 2000",
            "/dev/vda1  20G  5G  15G  25% /",
            "500.0 1000.0",
            "42",
        ]
    )
    parsed = _parse_quick_output(raw)
    assert parsed["cpu_percent"] == 25.0  # 0.25 / 1 * 100
    assert parsed["cpu_source"] == "loadavg"
    assert parsed["load_1m"] == 0.25
