import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { fetchAuthSession } from "@/lib/api";
import { canAccessStudio, hasFeatureAccess } from "@/lib/featureAccess";
import { localize, useI18n } from "@/lib/i18n";
import { StudioNavIcons } from "@/lib/app-icons";

const NAV_ITEMS = [
  { path: "/studio", labelRu: "Обзор", labelEn: "Overview", icon: StudioNavIcons.overview, exact: true },
  { path: "/studio/drafts", labelRu: "Черновики", labelEn: "Drafts", icon: StudioNavIcons.drafts, feature: "studio_pipelines" },
  { path: "/studio/skills", labelRu: "Скиллы", labelEn: "OPS Skills", icon: StudioNavIcons.skills, feature: "studio_skills" },
  { path: "/studio/mcp", labelRu: "MCP", labelEn: "MCP Tools", icon: StudioNavIcons.mcp, feature: "studio_mcp" },
  { path: "/studio/agents", labelRu: "Профили", labelEn: "Profiles", icon: StudioNavIcons.agents, feature: "studio_agents" },
  { path: "/studio/runs", labelRu: "Запуски", labelEn: "Runs", icon: StudioNavIcons.runs, feature: "studio_runs" },
  { path: "/studio/notifications", labelRu: "Оповещения", labelEn: "Alerts", icon: StudioNavIcons.notifications, feature: "studio_notifications" },
] as const;

export function StudioNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const { lang } = useI18n();
  const { data } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  const isActive = (path: string, exact?: boolean) => {
    if (exact) return location.pathname === path;
    return location.pathname.startsWith(path);
  };

  const items = NAV_ITEMS.filter((item) => {
    if (!("feature" in item) || !item.feature) {
      return canAccessStudio(data?.user);
    }
    return hasFeatureAccess(data?.user, item.feature);
  });

  return (
    <nav className="flex min-h-14 items-center gap-1 overflow-x-auto border-b border-border/60 bg-card/70 py-0 pl-16 pr-4 sm:px-4">
      <span className="mr-4 flex min-h-10 shrink-0 items-center gap-1.5 rounded-lg px-1 text-xs font-bold uppercase tracking-[0.14em] text-primary/80">
        <span className="h-1.5 w-1.5 rounded-full bg-primary/70" />
        Studio
      </span>
      {items.map((item) => {
        const active = isActive(item.path, "exact" in item ? item.exact : undefined);
        const Icon = item.icon;
        const label = localize(lang, item.labelRu, item.labelEn);
        return (
          <button
            type="button"
            key={item.path}
            onClick={() => navigate(item.path)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group relative flex min-h-10 shrink-0 items-center gap-2 rounded-lg px-3.5 text-xs font-medium transition-all duration-150",
              active
                ? "bg-secondary text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
            )}
          >
            <Icon
              className={cn("h-3.5 w-3.5 transition-colors", active ? "text-primary" : "group-hover:text-foreground/80")}
              strokeWidth={1.5}
            />
            {label}
            <span className={cn(
              "absolute bottom-0 left-2 right-2 h-0.5 rounded-full transition-all duration-200",
              active ? "bg-primary scale-x-100" : "bg-transparent scale-x-0 group-hover:bg-border group-hover:scale-x-100"
            )} />
          </button>
        );
      })}
    </nav>
  );
}
