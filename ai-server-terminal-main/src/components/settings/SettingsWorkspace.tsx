import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { ChevronRight, FolderOpen, Settings2, Shield, Users } from "lucide-react";

import { PageShell } from "@/components/ui/page-shell";
import { cn } from "@/lib/utils";

const SETTINGS_NAV_ITEMS = [
  {
    href: "/settings",
    label: "Общие",
    description: "AI, аудит и системные параметры.",
    icon: Settings2,
  },
  {
    href: "/settings/users",
    label: "Пользователи",
    description: "Аккаунты, профили и доступ.",
    icon: Users,
  },
  {
    href: "/settings/groups",
    label: "Группы",
    description: "Команды и групповые правила.",
    icon: FolderOpen,
  },
  {
    href: "/settings/permissions",
    label: "Разрешения",
    description: "Точечные исключения и политики.",
    icon: Shield,
  },
];

export function SettingsWorkspace({
  title,
  description,
  actions,
  children,
  asideHint,
  className,
}: {
  title: ReactNode;
  description: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  asideHint?: ReactNode;
  className?: string;
}) {
  return (
    <PageShell width="full" className={cn("max-w-[1600px]", className)}>
      <div className="grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="space-y-4 self-start xl:sticky xl:top-4">
          <section className="workspace-panel overflow-hidden">
            <div className="border-b border-border bg-secondary/20 px-4 py-4">
              <div className="enterprise-kicker">Settings</div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Спокойная навигация по системным и access-настройкам без лишнего шума.
              </p>
            </div>

            <nav aria-label="Settings sections" className="space-y-1 p-2">
              {SETTINGS_NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.href}
                    to={item.href}
                    end={item.href === "/settings"}
                    className={({ isActive }) =>
                      cn(
                        "group flex items-start gap-3 rounded-xl px-3 py-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                      )
                    }
                  >
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-background/70">
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{item.label}</div>
                      <div className="mt-0.5 text-xs leading-5 text-muted-foreground">{item.description}</div>
                    </div>
                    <ChevronRight className="mt-1 h-4 w-4 shrink-0 opacity-40 transition-opacity group-hover:opacity-70" aria-hidden="true" />
                  </NavLink>
                );
              })}
            </nav>
          </section>

          {asideHint ? (
            <div className="workspace-subtle rounded-xl px-4 py-3 text-sm leading-6 text-muted-foreground">
              {asideHint}
            </div>
          ) : null}
        </aside>

        <div className="min-w-0 space-y-5">
          <section className="workspace-panel px-6 py-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <div className="enterprise-kicker">Settings</div>
                <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
                <div className="max-w-3xl text-sm leading-6 text-muted-foreground">{description}</div>
              </div>
              {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
            </div>
          </section>

          {children}
        </div>
      </div>
    </PageShell>
  );
}
