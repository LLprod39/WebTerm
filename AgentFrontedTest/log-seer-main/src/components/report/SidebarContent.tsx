import { useState } from "react";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Server,
  Bot,
  FlaskConical,
  Boxes,
  Orbit,
  Globe,
  Palette,
  Terminal,
  type LucideIcon,
} from "lucide-react";

interface NavItem {
  label: string;
  icon: LucideIcon;
  active?: boolean;
}

const navItems: NavItem[] = [
  { label: "Панель", icon: LayoutDashboard },
  { label: "Серверы", icon: Server },
  { label: "Агенты", icon: Bot, active: true },
  { label: "Студия", icon: FlaskConical },
  { label: "Kubernetes", icon: Boxes },
  { label: "MARS", icon: Orbit },
];

interface SidebarContentProps {
  /** when true, render compact icon-only rail (tablet) */
  collapsed?: boolean;
}

export function SidebarContent({ collapsed = false }: SidebarContentProps) {
  const [lang, setLang] = useState<"RU" | "EN">("RU");
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  return (
    <div className="flex h-full flex-col bg-sidebar">
      {/* Logo */}
      <div
        className={cn(
          "flex h-16 items-center gap-2.5 border-b border-sidebar-border px-4",
          collapsed && "justify-center px-0",
        )}
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Terminal className="h-5 w-5" />
        </div>
        {!collapsed && (
          <span className="text-base font-semibold tracking-tight text-sidebar-accent-foreground">
            WebTerm<span className="text-primary">AI</span>
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <a
              key={item.label}
              href="#"
              onClick={(e) => e.preventDefault()}
              title={item.label}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                collapsed && "justify-center px-0",
                item.active
                  ? "bg-sidebar-accent text-sidebar-primary"
                  : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <Icon
                className={cn(
                  "h-[18px] w-[18px] shrink-0",
                  item.active ? "text-sidebar-primary" : "text-sidebar-foreground",
                )}
              />
              {!collapsed && <span>{item.label}</span>}
              {item.active && !collapsed && (
                <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
              )}
            </a>
          );
        })}
      </nav>

      {/* Footer / profile */}
      <div className="border-t border-sidebar-border p-3">
        <div
          className={cn(
            "flex items-center gap-3 rounded-lg px-2 py-2",
            collapsed && "justify-center px-0",
          )}
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sidebar-accent text-sm font-semibold text-sidebar-primary">
            li
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-sidebar-accent-foreground">linux</p>
              <p className="truncate text-xs text-sidebar-foreground">Администратор</p>
            </div>
          )}
        </div>

        {!collapsed && (
          <div className="mt-3 flex gap-2">
            <ToggleGroup
              options={["RU", "EN"]}
              value={lang}
              onChange={(v) => setLang(v as "RU" | "EN")}
            />
            <ToggleGroup
              options={["dark", "light"]}
              labels={["Тёмная", "Светлая"]}
              value={theme}
              onChange={(v) => setTheme(v as "dark" | "light")}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function ToggleGroup({
  options,
  labels,
  value,
  onChange,
}: {
  options: string[];
  labels?: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-1 rounded-md border border-sidebar-border p-0.5">
      {options.map((opt, i) => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={cn(
            "flex-1 rounded-[5px] px-2 py-1 text-xs font-medium transition-colors",
            value === opt
              ? "bg-sidebar-accent text-sidebar-primary"
              : "text-sidebar-foreground hover:text-sidebar-accent-foreground",
          )}
        >
          {labels ? labels[i] : opt}
        </button>
      ))}
    </div>
  );
}
