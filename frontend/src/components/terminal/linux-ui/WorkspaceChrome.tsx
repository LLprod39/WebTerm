import type { ReactNode } from "react";

import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { FrontendServer } from "@/lib/api";
import { cn } from "@/lib/utils";
import { workspaceStatusClass, workspaceStatusLabel } from "./workspaceChromeUtils";

export type WorkspaceAppId = "files" | "overview" | "services" | "processes" | "logs" | "disk" | "network" | "docker" | "packages" | "text-editor" | "quick-run" | "settings";
export type WorkspaceAppStatus = "live" | "ready" | "next" | "unavailable";

export interface WorkspaceAppDefinition {
  id: WorkspaceAppId;
  title: string;
  subtitle: string;
  status: WorkspaceAppStatus;
  icon: ReactNode;
  accentClass: string;
  hidden?: boolean;
}

export function ToolMenu({
  apps,
  server,
  activeApp,
  query,
  onQueryChange,
  onSelect,
  onRefresh,
  onCloseWorkspace,
}: {
  apps: WorkspaceAppDefinition[];
  server: FrontendServer;
  activeApp: WorkspaceAppId;
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (appId: WorkspaceAppId) => void;
  onRefresh: () => void;
  onCloseWorkspace?: () => void;
}) {
  const normalizedQuery = query.trim().toLowerCase();
  const pinnedAppIds: WorkspaceAppId[] = ["overview", "files", "services", "logs", "quick-run", "settings"];
  const visibleApps = apps.filter((app) => !app.hidden);
  const pinnedApps = visibleApps.filter((app) => pinnedAppIds.includes(app.id));
  const filteredApps = visibleApps.filter((app) => {
    if (!normalizedQuery) return true;
    return `${app.title} ${app.subtitle}`.toLowerCase().includes(normalizedQuery);
  });

  return (
    <div className="absolute bottom-[4.35rem] left-0 z-30 w-[min(29rem,calc(100vw-1.5rem))] overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/95 p-4 shadow-[0_24px_80px_-56px_rgba(15,23,42,0.9)]">
      <div className="relative z-10">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-xs font-medium text-muted-foreground">Инструменты Linux UI</div>
            <div className="mt-2 truncate text-2xl font-semibold tracking-tight text-foreground">{server.name}</div>
            <div className="mt-1 truncate font-mono text-xs text-muted-foreground">{server.username}@{server.host}</div>
          </div>
          <div className="rounded-[1.15rem] border border-primary/20 bg-primary/10 px-3 py-2 text-right">
            <div className="text-xs font-medium text-muted-foreground">Активно</div>
            <div className="max-w-24 truncate text-sm font-semibold text-foreground">
              {apps.find((app) => app.id === activeApp)?.title || "Обзор"}
            </div>
          </div>
        </div>

        <div className="relative mt-4">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Поиск приложений, инструментов, настроек..."
            aria-label="Поиск инструментов Linux UI"
            className="h-11 rounded-2xl border-border bg-background pl-10 text-sm text-foreground placeholder:text-muted-foreground"
          />
        </div>

        <div className="mt-5">
          <div className="mb-2 text-xs font-medium text-muted-foreground">Закреплено</div>
          <div className="grid grid-cols-3 gap-2">
            {pinnedApps.map((app) => (
              <button
                key={app.id}
                type="button"
                onClick={() => onSelect(app.id)}
                disabled={app.status === "unavailable"}
                className={cn(
                  "rounded-[1.15rem] border border-border px-3 py-3 text-left transition-all duration-150",
                  activeApp === app.id ? "border-primary/35 bg-primary/10" : "bg-background/70 hover:border-primary/25 hover:bg-secondary/70",
                  "disabled:cursor-not-allowed disabled:opacity-45",
                )}
              >
                <div className={cn("flex h-10 w-10 items-center justify-center rounded-2xl border border-border bg-gradient-to-br text-primary", app.accentClass)}>
                  <div className="[&>svg]:h-4 [&>svg]:w-4">{app.icon}</div>
                </div>
                <div className="mt-2 truncate text-sm font-medium text-foreground">{app.title}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="text-xs font-medium text-muted-foreground">Все инструменты</div>
            <div className="text-xs text-muted-foreground">{filteredApps.length} доступно</div>
          </div>
          <div className="max-h-64 space-y-1 overflow-y-auto pr-1">
            {filteredApps.map((app) => (
              <button
                key={app.id}
                type="button"
                onClick={() => onSelect(app.id)}
                disabled={app.status === "unavailable"}
                className={cn(
                  "flex w-full items-center gap-3 rounded-[1.1rem] border border-transparent px-3 py-2.5 text-left transition-colors",
                  activeApp === app.id ? "border-primary/25 bg-primary/10" : "hover:border-border hover:bg-secondary/60",
                  "disabled:cursor-not-allowed disabled:opacity-45",
                )}
              >
                <div className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-border bg-gradient-to-br text-primary", app.accentClass)}>
                  <div className="[&>svg]:h-4 [&>svg]:w-4">{app.icon}</div>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-foreground">{app.title}</span>
                    <span className={cn("rounded-md border px-2 py-0.5 text-xs font-medium", workspaceStatusClass(app.status))}>
                      {workspaceStatusLabel(app.status)}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">{app.subtitle}</div>
                </div>
              </button>
            ))}
            {filteredApps.length === 0 ? (
              <div className="rounded-[1.1rem] border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
                Ничего не найдено.
              </div>
            ) : null}
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-2">
          <Button type="button" variant="outline" className="h-10 rounded-2xl border-border bg-background text-xs text-foreground hover:bg-secondary" onClick={onRefresh}>
            Обновить
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-2xl border-border bg-background text-xs text-foreground hover:bg-secondary"
            onClick={onCloseWorkspace}
            disabled={!onCloseWorkspace}
          >
            Закрыть UI
          </Button>
        </div>
      </div>
    </div>
  );
}

export function WorkspacePanel({
  title,
  subtitle,
  icon,
  status,
  className,
  children,
}: {
  title: string;
  subtitle: string;
  icon: ReactNode;
  status: WorkspaceAppStatus;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "flex min-h-0 flex-1 flex-col overflow-hidden rounded-[1.35rem] border border-border bg-card shadow-[0_18px_60px_-44px_rgba(15,23,42,0.9)]",
        className,
      )}
    >
      <header className="flex min-h-14 items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border bg-secondary text-primary [&>svg]:h-4 [&>svg]:w-4">
            {icon}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-medium text-foreground">{title}</span>
              <span className={cn("rounded-md border px-2 py-0.5 text-xs font-medium", workspaceStatusClass(status))}>
                {workspaceStatusLabel(status)}
              </span>
            </div>
            <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
          </div>
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </section>
  );
}
