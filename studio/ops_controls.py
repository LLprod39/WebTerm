"""Backward-compat shim: ops kill-switch moved to app.core.ops_controls.

The kill switch is platform-level infrastructure (env flag + JSON file), so it
lives in app/core where both servers and studio may import it without breaking
the servers <-> studio isolation contracts.
"""

from app.core.ops_controls import (  # noqa: F401
    assert_agents_not_paused,
    assert_schedulers_not_paused,
    get_ops_control_status,
    is_ops_paused,
    kill_switch_path,
    ops_pause_reason,
    set_ops_paused,
)
