from __future__ import annotations

MODE_PLAN = "PLAN"
MODE_SAFE = "SAFE"
MODE_ASSISTED = "ASSISTED"
MODE_AUTONOMOUS = "AUTONOMOUS"
MODE_AUTO_GUARDED = "AUTO_GUARDED"

MUTATION_SANDBOX = {
    MODE_PLAN: "read_only",
    MODE_SAFE: "ops_read",
    MODE_ASSISTED: "workspace_write",
    MODE_AUTONOMOUS: "ops_mutation",
    MODE_AUTO_GUARDED: "ops_mutation",
}

