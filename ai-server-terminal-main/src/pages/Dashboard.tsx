import { Activity, AlertTriangle, Server, Wifi, WifiOff } from "lucide-react";
import { fetchFrontendBootstrap, fetchAuthSession } from "@/lib/api";
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
  const { data: user } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const { data, isLoading, error } = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">{t("dash.loading")}</div>;
  }
  if (error || !data) {
    return <div className="p-6 text-sm text-destructive">{t("dash.error")}</div>;
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
    <div className="flex flex-col min-h-screen bg-background">
      <div className="flex-1 space-y-8 px-6 py-8 max-w-6xl mx-auto w-full">
        {/* Header */}
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Welcome back,</p>
          <h1 className="text-3xl font-semibold text-foreground">
            {user?.user?.username || "User"}
          </h1>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {stats.map((stat) => (
            <div
              key={stat.labelKey}
              className="bg-card border border-border rounded-lg p-4 hover:border-border/80 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-muted-foreground uppercase tracking-wide">{t(stat.labelKey)}</span>
                <stat.icon className={`h-4 w-4 ${stat.color}`} />
              </div>
              <p className="text-3xl font-semibold text-foreground">{stat.value}</p>
            </div>
          ))}
        </div>

        {/* Activity Section */}
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="flex items-center gap-3 px-6 py-4 border-b border-border">
            <Activity className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">{t("dash.activity")}</h2>
          </div>
          <div className="divide-y divide-border">
            {(data?.recent_activity || []).length === 0 ? (
              <div className="px-6 py-12 text-center text-sm text-muted-foreground">
                {t("dash.no_activity")}
              </div>
            ) : (
              (data?.recent_activity || []).slice(0, 10).map((item) => (
                <div key={item.id} className="flex items-start gap-4 px-6 py-4 hover:bg-secondary/40 transition-colors">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/50 bg-secondary/40">
                    <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-foreground">{item.description || item.action}</p>
                    <p className="mt-1 text-xs font-mono text-muted-foreground">{item.entity_name || "-"}</p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground whitespace-nowrap">{toRelativeTime(item.created_at)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
