import { useLocation, useNavigate } from "react-router-dom";
import {
  Workflow,
  BookOpen,
  Server,
  Bot,
  Clock,
  Bell,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { path: "/studio", label: "Pipelines", icon: Workflow, exact: true },
  { path: "/studio/skills", label: "Skills", icon: BookOpen },
  { path: "/studio/mcp", label: "MCP", icon: Server },
  { path: "/studio/agents", label: "Agents", icon: Bot },
  { path: "/studio/runs", label: "Runs", icon: Clock },
  { path: "/studio/notifications", label: "Alerts", icon: Bell },
] as const;

export function StudioNav() {
  const navigate = useNavigate();
  const location = useLocation();

  const isActive = (item: (typeof NAV_ITEMS)[number]) => {
    if (item.exact) return location.pathname === item.path;
    return location.pathname.startsWith(item.path);
  };

  return (
    <nav className="flex items-center gap-1 border-b border-border bg-card/50 px-5 py-1.5 overflow-x-auto">
      <span className="text-xs font-semibold text-primary mr-3 shrink-0">Studio</span>
      {NAV_ITEMS.map((item) => {
        const active = isActive(item);
        const Icon = item.icon;
        return (
          <button
            key={item.path}
            onClick={() => navigate(item.path)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium transition-colors shrink-0",
              active
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
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
