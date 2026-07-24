import { Activity, AlertTriangle, Bot, LayoutGrid, Server, Siren, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AdminDashboardData, MonitoringDashboard } from "@/api";
import { Button } from "@/components/ui/button";
import { MetricCard, MetricGrid, SectionCard } from "@/components/ui/page-shell";
import { AttentionPanel } from "@/components/dashboard/AttentionPanel";
import { FleetHeatmap } from "@/components/dashboard/FleetHeatmap";
import { getWidgetNumberProp, getWidgetStringProp } from "@/components/dashboard/widgetProps";
import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { localize } from "@/lib/i18n";
import { buildAdminAttentionItems } from "./adminDashboardAttention";
import {
  formatChartDay,
  formatChartHour,
  pctTone,
  sectionToneStyles,
} from "./adminDashboardFormatters";

/** Attention, fleet map/metrics, agent trend, hourly activity. */
export function buildAdminCoreWidgets(
  d: AdminDashboardData,
  lang: string,
  mon?: MonitoringDashboard,
): WidgetDefinition[] {
  return [
    {
      id: "attention_panel",
      title: localize(lang, "Требует внимания", "Needs attention"),
      icon: <Siren className="h-4 w-4" />,
      defaultSize: { w: 12, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 6);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", localize(lang, "Требует внимания", "Needs attention"));
        const items = buildAdminAttentionItems(d, mon, lang);

        return (
          <SectionCard
            title={title}
            icon={<Siren className="h-4 w-4" />}
            description={localize(lang, "Сводка проблем по всей платформе с быстрыми действиями", "Platform-wide problems with one-click follow-ups")}
            className={sectionToneStyles[tone]}
          >
            <AttentionPanel items={items} lang={lang} maxItems={limit} />
          </SectionCard>
        );
      },
    },
    {
      id: "fleet_heatmap",
      title: localize(lang, "Карта флота", "Fleet map"),
      icon: <LayoutGrid className="h-4 w-4" />,
      defaultSize: { w: 12, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", localize(lang, "Карта флота", "Fleet map"));
        const summary = mon?.summary;

        return (
          <SectionCard
            title={title}
            icon={<LayoutGrid className="h-4 w-4" />}
            description={
              summary
                ? `${summary.healthy} ${localize(lang, "в норме", "healthy")} · ${summary.warning + summary.critical} ${localize(lang, "под нагрузкой", "stressed")} · ${summary.unreachable} ${localize(lang, "недоступно", "unreachable")}`
                : undefined
            }
            actions={
              <Button size="xs" variant="outline" asChild>
                <Link to="/servers">{localize(lang, "Все серверы", "All servers")}</Link>
              </Button>
            }
            className={sectionToneStyles[tone]}
          >
            <FleetHeatmap servers={mon?.servers ?? []} lang={lang} />
          </SectionCard>
        );
      },
    },
    {
      id: "agents_trend",
      title: localize(lang, "Тренд запусков агентов", "Agent runs trend"),
      icon: <TrendingUp className="h-4 w-4" />,
      defaultSize: { w: 4, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", localize(lang, "Запуски агентов, 7 дней", "Agent runs, 7 days"));
        const daily = d.agents?.daily ?? [];
        const total = daily.reduce((sum, day) => sum + day.succeeded + day.failed, 0);
        const failed = daily.reduce((sum, day) => sum + day.failed, 0);
        const successRate = total > 0 ? Math.round(((total - failed) / total) * 100) : null;

        return (
          <SectionCard
            title={title}
            icon={<TrendingUp className="h-4 w-4" />}
            description={
              total > 0
                ? `${total} ${localize(lang, "запусков", "runs")} · ${successRate}% ${localize(lang, "успех", "success")}`
                : localize(lang, "Запусков за неделю не было", "No runs this week")
            }
            className={sectionToneStyles[tone]}
          >
            <div className="h-[180px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={daily} margin={{ top: 5, right: 5, left: -25, bottom: 0 }} barCategoryGap="25%">
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border/40" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(value) => formatChartDay(lang, value)} className="text-xs font-medium fill-muted-foreground" />
                  <YAxis allowDecimals={false} className="text-xs font-medium fill-muted-foreground" />
                  <Tooltip
                    labelFormatter={(value) => formatChartDay(lang, value)}
                    cursor={{ fill: "hsl(var(--muted) / 0.25)" }}
                    contentStyle={{
                      background: "hsl(var(--background))",
                      borderColor: "hsl(var(--border))",
                      borderRadius: "4px",
                      fontSize: "11px",
                    }}
                  />
                  <Bar dataKey="succeeded" stackId="runs" name={localize(lang, "Успешно", "Succeeded")} fill="hsl(var(--success))" />
                  <Bar dataKey="failed" stackId="runs" name={localize(lang, "Сбой", "Failed")} fill="hsl(var(--destructive))" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>
        );
      },
    },
    {
      id: "fleet_metrics",
      title: "Метрики инфраструктуры",
      icon: <Server className="h-4 w-4" />,
      defaultSize: { w: 12, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Метрики инфраструктуры");

        const cpu = d.fleet_health?.avg_cpu || 0;
        const mem = d.fleet_health?.avg_memory || 0;
        const disk = d.fleet_health?.avg_disk || 0;
        const successRate = d.agents?.success_rate ?? 0;
        const failed24h = d.agents?.failed_24h ?? 0;

        return (
          <SectionCard title={title} icon={<Server className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <MetricGrid>
              <MetricCard
                label={localize(lang, "Серверы", "Servers")}
                value={d.servers?.total || 0}
                description={`${d.servers?.active || 0} ${localize(lang, "активно", "active")}`}
                icon={<Server className="h-5 w-5" />}
              />
              <MetricCard
                label={localize(lang, "CPU инфраструктуры", "Infrastructure CPU")}
                value={`${cpu}%`}
                description={localize(lang, "Средняя нагрузка", "Average load")}
                icon={<Activity className="h-5 w-5" />}
                tone={pctTone(cpu)}
              />
              <MetricCard
                label={localize(lang, "Память", "Memory")}
                value={`${mem}%`}
                description={localize(lang, "Средняя по флоту", "Fleet average")}
                icon={<Activity className="h-5 w-5" />}
                tone={pctTone(mem)}
              />
              <MetricCard
                label={localize(lang, "Диск", "Disk")}
                value={`${disk}%`}
                description={localize(lang, "Средняя по флоту", "Fleet average")}
                icon={<Activity className="h-5 w-5" />}
                tone={pctTone(disk)}
              />
              <MetricCard
                label={localize(lang, "Агенты", "Agents")}
                value={d.agents?.running || 0}
                description={`${d.agents?.today || 0} ${localize(lang, "сегодня", "today")} · ${successRate}% ${localize(lang, "успех", "success")}`}
                icon={<Bot className="h-5 w-5" />}
                tone={successRate > 0 && successRate < 60 ? "warning" : "default"}
              />
              <MetricCard
                label={localize(lang, "Алерты", "Alerts")}
                value={d.active_alerts_count || 0}
                description={
                  failed24h > 0
                    ? `${failed24h} ${localize(lang, "сбоев агентов за 24ч", "agent failures 24h")}`
                    : localize(lang, "Требуют внимания", "Need attention")
                }
                icon={<AlertTriangle className="h-5 w-5" />}
                tone={(d.active_alerts_count || 0) > 0 ? "danger" : "default"}
              />
            </MetricGrid>
          </SectionCard>
        );
      },
    },
    {
      id: "hourly_activity_chart",
      title: "Часовой график активности",
      icon: <Activity className="h-4 w-4" />,
      defaultSize: { w: 8, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Активность системы (по часам)");

        return (
          <SectionCard title={title} icon={<Activity className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="h-[200px] w-full mt-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={d.hourly_activity ?? []} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border/40" />
                  <XAxis dataKey="hour" tickFormatter={formatChartHour} className="text-xs font-medium fill-muted-foreground" />
                  <YAxis className="text-xs font-medium fill-muted-foreground" />
                  <Tooltip
                    labelFormatter={formatChartHour}
                    contentStyle={{
                      background: "hsl(var(--background))",
                      borderColor: "hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "11px",
                      boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)",
                    }}
                  />
                  <Area type="monotone" dataKey="count" name="Действия" stroke="hsl(var(--primary))" strokeWidth={2} fillOpacity={1} fill="url(#colorCount)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>
        );
      },
    },
  ];
}
