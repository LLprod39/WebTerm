import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ElementType } from "react";
import {
  fetchAdminDashboard,
  fetchAdminUsersSessions,
  resolveAlert,
  aiAnalyzeServer,
  type AdminDashboardData,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  Users,
  Server,
  AlertTriangle,
  Bot,
  Terminal,
  DollarSign,
  Shield,
  RefreshCw,
  TrendingUp,
  X,
  Cpu,
  MemoryStick,
  HardDrive,
  Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useState } from "react";
import ReactMarkdown from "react-markdown";

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function GaugeCompact({ label, value, icon: Icon }: { label: string; value: number; icon: React.ElementType }) {
  const color = value >= 90 ? "text-red-400" : value >= 75 ? "text-yellow-400" : "text-green-400";
  const bar = value >= 90 ? "bg-red-500" : value >= 75 ? "bg-yellow-500" : "bg-green-500";
  return (
    <div className="flex items-center gap-2">
      <Icon className="h-3 w-3 text-muted-foreground shrink-0" />
      <span className="text-[10px] text-muted-foreground w-8">{label}</span>
      <div className="flex-1 h-1 bg-secondary rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${bar}`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
      <span className={`text-xs font-mono w-8 text-right ${color}`}>{Math.round(value)}%</span>
    </div>
  );
}

export default function AdminDashboard() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"activity" | "users" | "alerts" | "api">("activity");
  const [analysisResult, setAnalysisResult] = useState<{ name: string; text: string } | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);

  const { data: dashData, isLoading } = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: fetchAdminDashboard,
    refetchInterval: 15_000,
  });

  const { data: sessionsData } = useQuery({
    queryKey: ["admin", "sessions"],
    queryFn: fetchAdminUsersSessions,
    refetchInterval: 30_000,
  });

  if (isLoading || !dashData?.data) {
    return <div className="p-6 text-sm text-muted-foreground">{t("dash.loading")}</div>;
  }

  const d: AdminDashboardData = dashData.data;
  const sessions = sessionsData?.sessions || [];
  const totalCost = Object.values(d.api_usage).reduce((s, u) => s + (u.cost_usd || 0), 0);
  const fh = d.fleet_health;

  const hourlyData = (d.hourly_activity || []).map((h) => ({
    hour: new Date(h.hour).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    count: h.count,
  }));

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin"] });

  const onAnalyze = async (serverId: number) => {
    setAnalyzingId(serverId);
    try {
      const res = await aiAnalyzeServer(serverId);
      setAnalysisResult({ name: res.server_name, text: res.analysis });
    } catch {
      setAnalysisResult({ name: "Error", text: "AI analysis failed." });
    } finally {
      setAnalyzingId(null);
    }
  };

  return (
    <div className="p-5 max-w-7xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t("adash.title")}</h1>
          <p className="text-[11px] text-muted-foreground">v{d.app_version}</p>
        </div>
        <Button size="sm" variant="ghost" className="gap-1.5 text-xs h-7" onClick={refresh}>
          <RefreshCw className="h-3 w-3" /> {t("udash.refresh")}
        </Button>
      </div>

      {/* Top metrics - single row */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
        <Metric label={t("adash.users_online")} value={d.online_users.count} sub={`/ ${d.online_users.total_registered}`} color="text-green-400" />
        <Metric label={t("adash.servers")} value={d.servers.active} sub={`/ ${d.servers.total}`} color="text-blue-400" />
        <Metric label={t("adash.alerts")} value={d.active_alerts_count} color={d.active_alerts_count > 0 ? "text-red-400" : "text-green-400"} />
        <Metric label={t("adash.ai_requests")} value={d.ai.requests_today} color="text-purple-400" />
        <Metric label={t("adash.terminals")} value={d.terminals.active} color="text-cyan-400" />
        <Metric label={t("adash.api_cost")} value={`$${totalCost.toFixed(2)}`} sub={`${d.api_calls_today} calls`} color="text-yellow-400" />
      </div>

      {/* Two columns: Fleet health + Online users */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Fleet health */}
        <div className="bg-card border border-border rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Server className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-medium">{t("adash.fleet_health")}</span>
          </div>
          <div className="flex gap-2 text-center">
            {(["healthy", "warning", "critical", "unreachable"] as const).map((s) => (
              <div key={s} className="flex-1 bg-secondary/30 rounded px-1 py-1.5">
                <p className={`text-sm font-semibold ${s === "healthy" ? "text-green-400" : s === "warning" ? "text-yellow-400" : "text-red-400"}`}>
                  {fh[s] || 0}
                </p>
                <p className="text-[9px] text-muted-foreground">{s}</p>
              </div>
            ))}
          </div>
          <div className="space-y-2">
            <GaugeCompact label="CPU" value={fh.avg_cpu} icon={Cpu} />
            <GaugeCompact label="RAM" value={fh.avg_memory} icon={MemoryStick} />
            <GaugeCompact label="Disk" value={fh.avg_disk} icon={HardDrive} />
          </div>
        </div>

        {/* Online users */}
        <div className="bg-card border border-border rounded-lg p-4 space-y-3 lg:col-span-2">
          <div className="flex items-center gap-2">
            <Users className="h-3.5 w-3.5 text-green-400" />
            <span className="text-xs font-medium">{t("adash.online_users")}</span>
            <span className="text-[10px] text-muted-foreground ml-1">
              {sessions.length} online · {sessionsData?.active_today || 0} {t("adash.today")}
            </span>
          </div>
          {sessions.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">{t("adash.no_users_online")}</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 max-h-36 overflow-y-auto">
              {sessions.map((s) => (
                <div key={s.user_id} className="flex items-center gap-2 bg-secondary/20 rounded px-2.5 py-1.5">
                  <div className="h-5 w-5 rounded-full bg-primary/15 flex items-center justify-center text-[9px] font-bold text-primary shrink-0">
                    {s.username.slice(0, 1).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-medium text-foreground">{s.username}</span>
                    {s.is_staff && <span className="text-[8px] ml-1 text-primary font-bold">ADM</span>}
                  </div>
                  <span className="text-[10px] text-muted-foreground">{s.last_action}</span>
                  {s.active_terminals > 0 && (
                    <span className="text-[9px] text-cyan-400"><Terminal className="h-2.5 w-2.5 inline" /> {s.active_terminals}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Activity chart */}
      {hourlyData.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-medium">{t("adash.hourly_activity")}</span>
          </div>
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hourlyData}>
                <XAxis dataKey="hour" tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} width={25} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "6px",
                    fontSize: "11px",
                    padding: "4px 8px",
                  }}
                />
                <Bar dataKey="count" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* AI Analysis result */}
      {analysisResult && (
        <div className="bg-card border border-primary/20 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 bg-primary/5 border-b border-primary/10">
            <div className="flex items-center gap-2">
              <Bot className="h-3.5 w-3.5 text-primary" />
              <span className="text-xs font-medium">AI: {analysisResult.name}</span>
            </div>
            <Button size="sm" variant="ghost" className="h-5 px-1" onClick={() => setAnalysisResult(null)}>
              <X className="h-3 w-3" />
            </Button>
          </div>
          <div className="p-4 prose prose-sm prose-invert max-w-none text-sm [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_p]:text-xs [&_li]:text-xs [&_code]:text-[11px] [&_pre]:text-[11px] [&_strong]:text-foreground [&_h1]:text-foreground [&_h2]:text-foreground [&_h3]:text-foreground">
            <ReactMarkdown>{analysisResult.text}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Tabs: activity / top users / alerts / api */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <div className="flex items-center gap-0.5 px-3 py-1.5 border-b border-border bg-secondary/20">
          {(["activity", "users", "alerts", "api"] as const).map((t2) => (
            <button
              key={t2}
              onClick={() => setTab(t2)}
              className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${tab === t2 ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
            >
              {t2 === "activity" ? t("adash.activity_feed") : t2 === "users" ? t("adash.top_users") : t2 === "alerts" ? `${t("adash.alert_center")}${d.active_alerts_count > 0 ? ` (${d.active_alerts_count})` : ""}` : t("adash.api_usage")}
            </button>
          ))}
        </div>

        <div className="max-h-72 overflow-y-auto">
          {tab === "activity" && (
            <table className="w-full text-xs">
              <tbody className="divide-y divide-border/50">
                {d.recent_activity.map((item, i) => (
                  <tr key={i} className="hover:bg-secondary/20">
                    <td className="px-3 py-1.5 w-20">
                      <span className="text-foreground font-medium">{item.user}</span>
                    </td>
                    <td className="px-2 py-1.5">
                      <span className="text-muted-foreground">{item.action}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right text-muted-foreground w-16">{relativeTime(item.time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === "users" && (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] text-muted-foreground uppercase border-b border-border">
                  <th className="px-3 py-2 text-left font-medium">{t("adash.user")}</th>
                  <th className="px-2 py-2 text-right font-medium">{t("adash.actions")}</th>
                  <th className="px-2 py-2 text-right font-medium">AI</th>
                  <th className="px-2 py-2 text-right font-medium">Term</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {d.top_users.map((u, i) => (
                  <tr key={i} className="hover:bg-secondary/20">
                    <td className="px-3 py-1.5 font-medium text-foreground">{u.username}</td>
                    <td className="px-2 py-1.5 text-right text-muted-foreground">{u.total}</td>
                    <td className="px-2 py-1.5 text-right text-muted-foreground">{u.ai_requests}</td>
                    <td className="px-2 py-1.5 text-right text-muted-foreground">{u.terminal_sessions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === "alerts" && (
            <>
              {(d.alerts || []).length === 0 ? (
                <p className="text-xs text-muted-foreground p-6 text-center">{t("adash.no_alerts")}</p>
              ) : (
                <table className="w-full text-xs">
                  <tbody className="divide-y divide-border/50">
                    {(d.alerts || []).map((a, i) => (
                      <tr key={i} className="hover:bg-secondary/20">
                        <td className="px-3 py-1.5 w-12">
                          <span className={`text-[9px] px-1 py-0.5 rounded font-bold ${a.severity === "critical" ? "bg-red-500/20 text-red-400" : "bg-yellow-500/20 text-yellow-400"}`}>
                            {a.severity === "critical" ? "CRIT" : "WARN"}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-foreground">{a.title}</td>
                        <td className="px-2 py-1.5 text-muted-foreground">{a.server}</td>
                        <td className="px-2 py-1.5 text-right text-muted-foreground w-12">{relativeTime(a.time)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}

          {tab === "api" && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-3">
              {Object.entries(d.api_usage).map(([provider, usage]) => (
                <div key={provider} className="bg-secondary/20 rounded-lg p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-foreground uppercase">{provider}</span>
                    <span className={`text-[8px] px-1 rounded ${d.providers[provider]?.enabled ? "bg-green-500/20 text-green-400" : "bg-secondary text-muted-foreground"}`}>
                      {d.providers[provider]?.enabled ? "ON" : "OFF"}
                    </span>
                  </div>
                  <p className="text-base font-semibold text-foreground">{usage.calls} <span className="text-[10px] font-normal text-muted-foreground">calls</span></p>
                  <div className="text-[10px] text-muted-foreground">
                    <p>{(usage.input_tokens || 0).toLocaleString()} in / {(usage.output_tokens || 0).toLocaleString()} out</p>
                    <p className="text-yellow-400 font-medium">${(usage.cost_usd || 0).toFixed(4)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Active terminals */}
      {d.terminals.connections.length > 0 && (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2 border-b border-border">
            <Eye className="h-3.5 w-3.5 text-cyan-400" />
            <span className="text-xs font-medium">{t("adash.active_terminals")} ({d.terminals.active})</span>
          </div>
          <div className="flex flex-wrap gap-2 p-3">
            {d.terminals.connections.map((c, i) => (
              <div key={i} className="flex items-center gap-1.5 bg-secondary/20 rounded px-2 py-1 text-[10px]">
                <Terminal className="h-3 w-3 text-cyan-400" />
                <span className="text-foreground font-medium">{c.user}</span>
                <span className="text-muted-foreground">→ {c.server}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color: string }) {
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-2.5">
      <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-lg font-semibold ${color}`}>
        {value}
        {sub && <span className="text-[10px] font-normal text-muted-foreground ml-0.5">{sub}</span>}
      </p>
    </div>
  );
}
