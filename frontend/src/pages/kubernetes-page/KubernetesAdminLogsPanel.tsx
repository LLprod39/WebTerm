import type { KubernetesAdminPodLogsResponse } from "@/api";
import { StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";

export function AdminLogsSnapshotPanel({ lang, logs }: { lang: string; logs: KubernetesAdminPodLogsResponse }) {
  return (
    <div className="mb-4 rounded-lg border border-border/70 bg-background/45 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={localize(lang, "Logs snapshot", "Logs snapshot")} tone={logs.available ? "success" : logs.source === "provider_error" ? "danger" : "neutral"} />
        <StatusBadge label={logs.target.namespace || "namespace"} tone="neutral" />
        <StatusBadge label={`${logs.policy.requested_tail_lines} lines`} tone="info" />
        <StatusBadge label={logs.policy.streaming ? "streaming" : "snapshot"} tone={logs.policy.streaming ? "warning" : "success"} />
        {logs.truncated ? <StatusBadge label="truncated" tone="warning" /> : null}
      </div>
      <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        <div>
          {localize(lang, "Pod:", "Pod:")} <span className="font-medium text-foreground">{logs.target.name}</span>
        </div>
        <div>
          {localize(lang, "Source:", "Source:")} {logs.source}
        </div>
        <div>
          {localize(lang, "Provider:", "Provider:")} {logs.provider.name}
        </div>
        <div>
          {localize(lang, "Stored lines in audit:", "Stored lines in audit:")} 0
        </div>
      </div>
      {logs.message ? <div className="mt-3 text-xs text-muted-foreground">{logs.message}</div> : null}
      <pre className="mt-3 max-h-80 overflow-auto rounded-lg border border-border/70 bg-secondary/25 p-4 text-xs leading-5 text-foreground">
        {logs.lines.length ? logs.lines.join("\n") : localize(lang, "Лог-строки недоступны.", "Log lines are not available.")}
      </pre>
    </div>
  );
}
