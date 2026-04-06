import { Activity, AlertTriangle, Server, Wifi, WifiOff } from "lucide-react";
import { fetchFrontendBootstrap } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/lib/i18n";

function toRelativeTime(value: string | null): string {
  if (!value) return "just now";
  const date = new Date(value);
  const diffMs = Date.now() - date.getTime();
  const mins = Math.max(1, Math.floor(diffMs / 60_000));
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function Dashboard() {
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });

  if (isLoading) {
    return <div className="w-full px-4 py-5 text-sm text-muted-foreground md:px-6 xl:px-8">{t("dash.loading")}</div>;
  }
  if (error || !data) {
    return <div className="w-full px-4 py-5 text-sm text-destructive md:px-6 xl:px-8">{t("dash.error")}</div>;
  }

  const servers = data.servers || [];
  const online = servers.filter((server) => server.status === "online").length;
  const offline = servers.filter((server) => server.status === "offline").length;
  const unknown = servers.filter((server) => server.status === "unknown").length;

  const stats = [
    { labelKey: "dash.total", value: servers.length, icon: Server, color: "text-info" },
    { labelKey: "dash.online", value: online, icon: Wifi, color: "text-success" },
    { labelKey: "dash.offline", value: offline, icon: WifiOff, color: offline > 0 ? "text-destructive" : "text-muted-foreground" },
    { labelKey: "dash.unknown", value: unknown, icon: AlertTriangle, color: unknown > 0 ? "text-warning" : "text-muted-foreground" },
  ];

  return (
    <div className="w-full space-y-6 px-4 py-5 md:px-6 xl:px-8">
      <h1 className="text-2xl font-semibold text-foreground">{t("dash.title")}</h1>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <div
            key={stat.labelKey}
            className="bg-card border border-border rounded-lg p-4"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground">{t(stat.labelKey)}</span>
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
            </div>
            <p className="text-2xl font-semibold text-foreground">{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="bg-card border border-border rounded-lg">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <Activity className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-medium text-foreground">{t("dash.activity")}</h2>
        </div>
        <div className="divide-y divide-border">
          {(data.recent_activity || []).length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              No recent activity
            </div>
          ) : (
            (data.recent_activity || []).map((item) => (
              <div key={item.id} className="flex items-start gap-4 px-5 py-3.5">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-background/35">
                  <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{item.description || item.action}</p>
                  <p className="mt-1 text-xs font-mono text-muted-foreground">{item.entity_name || "-"}</p>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">{toRelativeTime(item.created_at)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
