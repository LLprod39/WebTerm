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
    <nav className="flex items-center gap-1 overflow-x-auto border-b border-border bg-card/40 px-4 py-2">
      <span className="mr-3 shrink-0 text-sm font-semibold text-foreground">Studio</span>
      {items.map((item) => {
        const active = isActive(item.path, "exact" in item ? item.exact : undefined);
        const Icon = item.icon;
        return (
          <button
            type="button"
            key={item.path}
            onClick={() => navigate(item.path)}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
