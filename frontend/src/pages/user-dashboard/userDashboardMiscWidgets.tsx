import {
  Activity,
  Bot,
  Clock,
  Server,
  Settings,
  Workflow,
} from "lucide-react";
import { Link } from "react-router-dom";
import { SectionCard } from "@/components/ui/page-shell";
import { getWidgetNumberProp, getWidgetStringProp } from "@/components/dashboard/widgetProps";
import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { relativeTime } from "@/lib/utils";
import { localize } from "@/lib/i18n";
import type { UserDashboardData } from "./useUserDashboardData";
import { sectionToneStyles } from "./userDashboardShared";

type MiscWidgetCtx = Pick<UserDashboardData, "boot" | "lang">;

/** Activity history and quick-action tools. */
export function buildUserMiscWidgets(ctx: MiscWidgetCtx): WidgetDefinition[] {
  const { boot, lang } = ctx;

  return [
    {
      id: "recent_activity",
      title: localize(lang, "Моя активность", "My activity"),
      icon: <Activity className="h-4 w-4" />,
      defaultSize: { w: 6, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", localize(lang, "История действий", "Action history"));
        const displayActivity = boot?.recent_activity?.slice(0, limit) ?? [];

        return (
          <SectionCard title={title} icon={<Clock className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="space-y-4">
              {displayActivity.map((a, idx) => (
                <div key={idx} className="flex items-start gap-3 text-xs group">
                  <div className="mt-1.5 h-2 w-2 rounded-full bg-primary/45 shrink-0 transition-transform group-hover:scale-125" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold truncate text-foreground/90">{a.action}</span>
                      <span className="text-xs text-muted-foreground/40 font-mono shrink-0">{relativeTime(a.created_at)}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground/70 leading-relaxed truncate">{a.description}</p>
                  </div>
                </div>
              ))}
              {displayActivity.length === 0 && (
                <div className="py-6 text-center text-xs text-muted-foreground">{localize(lang, "Нет недавних действий", "No recent actions")}</div>
              )}
            </div>
          </SectionCard>
        );
      },
    },
    {
      id: "quick_tools",
      title: localize(lang, "Быстрые действия", "Quick actions"),
      icon: <Settings className="h-4 w-4" />,
      defaultSize: { w: 4, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", localize(lang, "Быстрые действия", "Quick actions"));

        const tools = [
          { to: "/servers/hub", icon: Server, title: localize(lang, "Хаб серверов", "Server hub"), sub: localize(lang, "Все узлы", "All nodes") },
          { to: "/studio", icon: Workflow, title: localize(lang, "Студия", "Studio"), sub: localize(lang, "Пайплайны", "Pipelines") },
          { to: "/agents", icon: Bot, title: localize(lang, "Агенты", "Agents"), sub: localize(lang, "Создать и запустить", "Create & run") },
          { to: "/settings", icon: Settings, title: localize(lang, "Настройки", "Settings"), sub: localize(lang, "Параметры", "Preferences") },
        ];

        return (
          <SectionCard title={title} icon={<Settings className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {tools.map((tool) => (
                <Link
                  key={tool.to}
                  to={tool.to}
                  className="flex flex-col items-center justify-center p-3 rounded-xl border border-border/60 bg-surface-2/40 hover:border-primary/50 hover:bg-surface-2 transition-all text-center group"
                >
                  <tool.icon className="h-5 w-5 text-primary/80 mb-2 transition-transform group-hover:scale-110" />
                  <span className="font-semibold text-foreground/90">{tool.title}</span>
                  <span className="text-xs text-muted-foreground/60 mt-0.5">{tool.sub}</span>
                </Link>
              ))}
            </div>
          </SectionCard>
        );
      },
    },
  ];
}
