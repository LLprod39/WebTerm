import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutGrid,
  BookOpen,
  Server,
  Bot,
  Clock,
  Bell,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchAuthSession } from "@/lib/api";
import { canAccessStudio, hasFeatureAccess } from "@/lib/featureAccess";

const NAV_ITEMS = [
  { path: "/studio", label: "Overview", icon: LayoutGrid, exact: true },
  { path: "/studio/skills", label: "Skills", icon: BookOpen, feature: "studio_skills" },
  { path: "/studio/mcp", label: "MCP", icon: Server, feature: "studio_mcp" },
  { path: "/studio/agents", label: "Agents", icon: Bot, feature: "studio_agents" },
  { path: "/studio/runs", label: "Runs", icon: Clock, feature: "studio_runs" },
  { path: "/studio/notifications", label: "Alerts", icon: Bell, feature: "studio_notifications" },
] as const;

export function StudioNav() {
  const navigate = useNavigate();
  const location = useLocation();
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
    <nav className="flex items-center gap-0 overflow-x-auto border-b border-border/60 bg-card/40 backdrop-blur-sm px-4">
      <span className="mr-5 shrink-0 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-primary/80">
        <span className="h-1 w-1 rounded-full bg-primary/60 animate-pulse" />
        Studio
      </span>
      {items.map((item) => {
        const active = isActive(item.path, "exact" in item ? item.exact : undefined);
        const Icon = item.icon;
        return (
          <button
            type="button"
            key={item.path}
            onClick={() => navigate(item.path)}
            className={cn(
              "group relative flex shrink-0 items-center gap-1.5 px-3.5 pb-3 pt-2.5 text-xs font-medium transition-all duration-150",
              active
                ? "text-foreground"
                : "text-muted-foreground/70 hover:text-foreground"
            )}
          >
            <Icon className={cn("h-3.5 w-3.5 transition-colors", active ? "text-primary" : "group-hover:text-foreground/80")} />
            {item.label}
            <span className={cn(
              "absolute bottom-0 left-0 h-0.5 w-full rounded-full transition-all duration-200",
              active ? "bg-primary scale-x-100" : "bg-transparent scale-x-0 group-hover:bg-border group-hover:scale-x-100"
            )} />
          </button>
        );
      })}
    </nav>
  );
}
