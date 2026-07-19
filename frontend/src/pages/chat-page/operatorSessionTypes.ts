export type OperatorSessionLine = {
  id: string;
  at: number;
  source: "agent" | "you" | "system";
  kind: "cmd" | "out" | "err" | "note";
  text: string;
};

export type OperatorSessionState = {
  open: boolean;
  serverId: number | null;
  serverName: string;
  host: string;
  /** agent = AI activity log; live = interactive xterm */
  mode: "agent" | "live";
  lines: OperatorSessionLine[];
  /** Recent human commands for operator context */
  humanTrail: Array<{ cmd: string; at: number }>;
};

export const EMPTY_OPERATOR_SESSION: OperatorSessionState = {
  open: false,
  serverId: null,
  serverName: "",
  host: "",
  mode: "agent",
  lines: [],
  humanTrail: [],
};

export function isSshToolName(name: string): boolean {
  const n = name.toLowerCase().replace(/\./g, "_");
  // Strict: real remote shell tools only — never metrics / resolve / list_*
  if (n.includes("server_metrics") || n.includes("metric_series") || n.includes("resolve_server")) {
    return false;
  }
  return (
    n.includes("run_command") ||
    n.includes("run_fanout") ||
    n.includes("operator_run_command") ||
    n === "ssh" ||
    n.endsWith("_ssh") ||
    n.includes("ssh_exec")
  );
}
