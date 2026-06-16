import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  Clock3,
  Monitor,
  RefreshCw,
  Shield,
  Terminal,
  X,
} from "lucide-react";

import { SftpPanel } from "@/components/terminal/SftpPanel";
import { TextEditorWindow } from "@/components/terminal/LinuxUiTextEditor";
import { QuickRunWindow } from "@/components/terminal/LinuxUiQuickRun";
import { SystemSettingsWindow } from "@/components/terminal/LinuxUiSystemSettings";
import { DockerWindow } from "@/components/terminal/linux-ui/DockerWindow";
import { DiskWindow } from "@/components/terminal/linux-ui/DiskWindow";
import { LogsWindow } from "@/components/terminal/linux-ui/LogsWindow";
import { NetworkWindow } from "@/components/terminal/linux-ui/NetworkWindow";
import { OverviewWindow } from "@/components/terminal/linux-ui/OverviewWindow";
import { PackagesWindow } from "@/components/terminal/linux-ui/PackagesWindow";
import { ProcessesWindow } from "@/components/terminal/linux-ui/ProcessesWindow";
import { ServicesWindow } from "@/components/terminal/linux-ui/ServicesWindow";
import { SummaryCard } from "@/components/terminal/linux-ui/SummaryCard";
import { buildWorkspaceApps } from "@/components/terminal/linux-ui/WorkspaceApps";
import {
  DEFAULT_ACTIVE_APP,
  ToolMenu,
  WorkspacePanel,
  panelHeightClass,
  type WorkspaceAppDefinition,
  type WorkspaceAppId,
  workspaceStatusLabel,
} from "@/components/terminal/linux-ui/WorkspaceChrome";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  fetchLinuxUiCapabilities,
  fetchLinuxUiOverview,
  type FrontendServer,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { localize, useI18n } from "@/lib/i18n";

interface LinuxUiPanelProps {
  server: FrontendServer;
  active?: boolean;
  onClose?: () => void;
  onOpenAi?: () => void;
}

export function LinuxUiPanel({ server, active = true, onClose }: LinuxUiPanelProps) {
  const { lang } = useI18n();
  const launcherSurfaceRef = useRef<HTMLDivElement | null>(null);
  const capabilitiesQuery = useQuery({
    queryKey: ["linux-ui", server.id, "capabilities"],
    queryFn: () => fetchLinuxUiCapabilities(server.id),
    enabled: active && server.server_type === "ssh",
    staleTime: 30_000,
  });

  const overviewQuery = useQuery({
    queryKey: ["linux-ui", server.id, "overview"],
    queryFn: () => fetchLinuxUiOverview(server.id),
    enabled: active && server.server_type === "ssh",
    staleTime: 15_000,
  });

  const [activeApp, setActiveApp] = useState<WorkspaceAppId>(DEFAULT_ACTIVE_APP);
  const [pendingEditorPath, setPendingEditorPath] = useState<string | null>(null);
  const [launcherOpen, setLauncherOpen] = useState(false);
  const [launcherQuery, setLauncherQuery] = useState("");
  const [clockNow, setClockNow] = useState(() => new Date());

  useEffect(() => {
    setActiveApp(DEFAULT_ACTIVE_APP);
    setPendingEditorPath(null);
    setLauncherOpen(false);
    setLauncherQuery("");
  }, [server.id]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setClockNow(new Date());
    }, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!launcherOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && launcherSurfaceRef.current?.contains(target)) return;
      setLauncherOpen(false);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setLauncherOpen(false);
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [launcherOpen]);

  const refresh = useCallback(() => {
    void capabilitiesQuery.refetch();
    void overviewQuery.refetch();
  }, [capabilitiesQuery, overviewQuery]);

  const capabilities = capabilitiesQuery.data?.capabilities;
  const availableApps = capabilities?.available_apps;
  const packageManager = capabilities?.package_manager;

  const apps = useMemo<WorkspaceAppDefinition[]>(() => buildWorkspaceApps({ availableApps, packageManager, lang }), [
    availableApps?.disk,
    availableApps?.docker,
    availableApps?.logs,
    availableApps?.network,
    availableApps?.quick_run,
    availableApps?.services,
    availableApps?.settings,
    availableApps?.text_editor,
    packageManager,
    lang,
  ]);

  const appMap = useMemo(
    () => Object.fromEntries(apps.map((app) => [app.id, app])) as Record<WorkspaceAppId, WorkspaceAppDefinition>,
    [apps],
  );

  const selectApp = useCallback((appId: WorkspaceAppId) => {
    const app = appMap[appId];
    if (!app || app.status === "unavailable") return;
    setActiveApp(appId);
    setLauncherOpen(false);
  }, [appMap]);

  const openFileInEditor = useCallback((path: string) => {
    setPendingEditorPath(path);
    setActiveApp("text-editor");
    setLauncherOpen(false);
  }, []);

  useEffect(() => {
    const app = appMap[activeApp];
    if (app?.status === "unavailable") {
      setActiveApp(DEFAULT_ACTIVE_APP);
    }
  }, [activeApp, appMap]);

  const visibleApps = useMemo(() => apps.filter((app) => !app.hidden), [apps]);
  const activeAppDefinition = appMap[activeApp] ?? appMap[DEFAULT_ACTIVE_APP];
  const overview = overviewQuery.data?.overview;
  const timeLabel = useMemo(
    () => new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(clockNow),
    [clockNow],
  );
  const dateLabel = useMemo(
    () => new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" }).format(clockNow),
    [clockNow],
  );

  const errorMessage =
    (capabilitiesQuery.error instanceof Error && capabilitiesQuery.error.message) ||
    (overviewQuery.error instanceof Error && overviewQuery.error.message) ||
    "";

  const renderActiveContent = (appId: WorkspaceAppId) => {
    if (appId === "files") {
      return <SftpPanel server={server} active={active && activeApp === "files"} onOpenInEditor={openFileInEditor} />;
    }
    if (appId === "overview") {
      return (
        <OverviewWindow
          overview={overviewQuery.data?.overview}
          capabilities={capabilities}
          onOpenFiles={() => selectApp("files")}
          onOpenServices={() => selectApp("services")}
          onOpenDisk={() => selectApp("disk")}
          onOpenLogs={() => selectApp("logs")}
        />
      );
    }
    if (appId === "services") {
      return <ServicesWindow server={server} active={active && activeApp === "services"} servicesEnabled={Boolean(availableApps?.services)} logsEnabled={Boolean(availableApps?.logs)} onOpenLogs={() => selectApp("logs")} />;
    }
    if (appId === "processes") {
      return <ProcessesWindow server={server} active={active && activeApp === "processes"} />;
    }
    if (appId === "logs") {
      return <LogsWindow server={server} active={active && activeApp === "logs"} logsEnabled={Boolean(availableApps?.logs)} />;
    }
    if (appId === "disk") {
      return <DiskWindow server={server} active={active && activeApp === "disk"} diskEnabled={Boolean(availableApps?.disk)} onOpenInEditor={openFileInEditor} />;
    }
    if (appId === "network") {
      return <NetworkWindow server={server} active={active && activeApp === "network"} networkEnabled={Boolean(availableApps?.network)} />;
    }
    if (appId === "docker") {
      return <DockerWindow server={server} active={active && activeApp === "docker"} dockerEnabled={Boolean(availableApps?.docker)} />;
    }
    if (appId === "packages") {
      return <PackagesWindow server={server} active={active && activeApp === "packages"} packageManager={packageManager || ""} />;
    }
    if (appId === "text-editor") {
      return <TextEditorWindow server={server} active={active && activeApp === "text-editor"} initialPath={pendingEditorPath || undefined} onPathConsumed={() => setPendingEditorPath(null)} />;
    }
    if (appId === "quick-run") {
      return <QuickRunWindow server={server} active={active && activeApp === "quick-run"} />;
    }
    return <SystemSettingsWindow server={server} active={active && activeApp === "settings"} />;
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(circle at 14% 16%, rgba(45,212,191,0.08), transparent 24%), radial-gradient(circle at 82% 10%, rgba(45,212,191,0.06), transparent 20%), linear-gradient(180deg, rgba(28,31,38,1) 0%, rgba(24,26,32,1) 100%)",
          }}
        />
        <div className="relative z-10 flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-3 lg:overflow-hidden lg:p-4">
          {server.server_type !== "ssh" ? (
            <div className="rounded-[1.25rem] border border-border bg-card p-6 text-sm text-muted-foreground">
              Linux Workspace доступен только для SSH-серверов.
            </div>
          ) : null}

          {server.server_type === "ssh" && errorMessage ? (
            <div className="rounded-[1.25rem] border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMessage}
            </div>
          ) : null}

          {server.server_type === "ssh" && (capabilitiesQuery.isLoading || overviewQuery.isLoading) ? (
            <div className="flex h-full min-h-[22rem] items-center justify-center">
              <div className="rounded-[1.5rem] border border-border bg-card px-8 py-10 text-center shadow-lg">
                <RefreshCw className="mx-auto mb-3 h-5 w-5 animate-spin text-primary" />
                <div className="text-sm font-medium text-foreground">{localize(lang, "Загрузка Linux UI...", "Loading Linux UI...")}</div>
                <div className="mt-1 text-xs text-muted-foreground">Собираем возможности хоста</div>
              </div>
            </div>
          ) : null}

          {server.server_type === "ssh" && !capabilitiesQuery.isLoading && !overviewQuery.isLoading && activeAppDefinition ? (
            <>
              <div className="grid gap-3 md:grid-cols-3">
                <SummaryCard
                  label="Host"
                  value={overview?.hostname || server.name}
                  hint={`${server.username}@${server.host}`}
                />
                <SummaryCard
                  label="Memory"
                  value={overview?.memory.percent != null ? `${overview.memory.percent.toFixed(1)}%` : "Нет данных"}
                  hint={
                    overview?.memory.used_mb != null && overview.memory.total_mb != null
                      ? `${overview.memory.used_mb} / ${overview.memory.total_mb} MB`
                      : capabilities?.os_name || localize(lang, "Linux-хост", "Linux host")
                  }
                  alert={(overview?.memory.percent || 0) >= 90}
                />
                <SummaryCard
                  label="Disk"
                  value={overview?.disk.percent != null ? `${overview.disk.percent.toFixed(1)}%` : "Нет данных"}
                  hint={
                    overview?.disk.used_gb != null && overview.disk.total_gb != null
                      ? `${overview.disk.used_gb} / ${overview.disk.total_gb} GB`
                      : localize(lang, "Корневая файловая система", "Root filesystem")
                  }
                  alert={(overview?.disk.percent || 0) >= 90}
                />
              </div>

              <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[17rem_minmax(0,1fr)]">
                <aside className="min-h-0 overflow-hidden rounded-[1.35rem] border border-border bg-card/95">
                  <div className="border-b border-border px-4 py-3">
                    <div className="text-sm font-medium text-foreground">Инструменты</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {capabilities?.os_name || overview?.os_name || localize(lang, "Linux-хост", "Linux host")}
                    </div>
                  </div>
                  <ScrollArea className="h-[18rem] xl:h-full">
                    <div className="space-y-1.5 p-2">
                      {visibleApps.map((app) => (
                        <button
                          key={app.id}
                          type="button"
                          onClick={() => selectApp(app.id)}
                          disabled={app.status === "unavailable"}
                          className={cn(
                            "flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors",
                            activeApp === app.id
                              ? "border-primary/35 bg-primary/10 text-foreground"
                              : "border-transparent text-muted-foreground hover:border-border hover:bg-secondary/60 hover:text-foreground",
                            "disabled:cursor-not-allowed disabled:opacity-45",
                          )}
                        >
                          <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border bg-gradient-to-br text-primary", app.accentClass)}>
                            <span className="[&>svg]:h-4 [&>svg]:w-4">{app.icon}</span>
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium">{app.title}</span>
                            <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{workspaceStatusLabel(app.status)}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </ScrollArea>
                </aside>

                <WorkspacePanel
                  title={activeAppDefinition.title}
                  subtitle={activeAppDefinition.subtitle}
                  icon={activeAppDefinition.icon}
                  status={activeAppDefinition.status}
                  className={panelHeightClass(activeApp)}
                >
                  {renderActiveContent(activeApp)}
                </WorkspacePanel>
              </div>
            </>
          ) : null}
        </div>
      </div>

      <div ref={launcherSurfaceRef} className="relative z-20 px-3 pb-3 pt-2">
        {launcherOpen ? (
          <ToolMenu
            apps={apps}
            server={server}
            activeApp={activeApp}
            query={launcherQuery}
            onQueryChange={setLauncherQuery}
            onSelect={selectApp}
            onRefresh={() => {
              refresh();
              setLauncherOpen(false);
            }}
            onCloseWorkspace={
              onClose
                ? () => {
                    setLauncherOpen(false);
                    onClose();
                  }
                : undefined
            }
          />
        ) : null}

        <footer className="relative flex h-14 items-center gap-2 rounded-[1.4rem] border border-border bg-card/95 px-3 shadow-lg">
          <button
            type="button"
            onClick={() => setLauncherOpen((current) => !current)}
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-[1rem] border border-border bg-primary/10 text-primary transition-all duration-150 hover:bg-primary/15",
              launcherOpen && "border-primary/35 bg-primary/15",
            )}
            aria-label="Открыть панель инструментов"
          >
            <Monitor className="h-5 w-5" />
          </button>

          <div className="h-8 w-px bg-border" />

          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-foreground">{activeAppDefinition?.title || "Обзор"}</div>
            <div className="truncate text-[11px] text-muted-foreground">
              {activeAppDefinition?.subtitle || `${server.username}@${server.host}`}
            </div>
          </div>

          <div className="h-8 w-px bg-border" />

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={refresh}
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-background text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label={localize(lang, "Обновить Linux UI", "Refresh Linux UI")}
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <div className="hidden items-center gap-1 rounded-[1rem] border border-border bg-background px-2.5 py-1.5 lg:flex">
              <Shield className="h-3.5 w-3.5 text-muted-foreground" />
              <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
            </div>

            <div className="hidden rounded-[1rem] border border-border bg-background px-3 py-1.5 text-right xl:block">
              <div className="truncate font-mono text-[11px] text-muted-foreground">{server.username}@{server.host}</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">{capabilities?.os_name || localize(lang, "Рабочее пространство Linux", "Linux workspace")}</div>
            </div>

            <div className="rounded-[1rem] border border-border bg-background px-3 py-1.5 text-right">
              <div className="flex items-center justify-end gap-1 text-[11px] text-muted-foreground">
                <CalendarDays className="h-3.5 w-3.5" />
                <span>{dateLabel}</span>
              </div>
              <div className="mt-0.5 flex items-center justify-end gap-1 text-sm font-semibold text-foreground">
                <Clock3 className="h-3.5 w-3.5 text-primary" />
                <span>{timeLabel}</span>
              </div>
            </div>

            {onClose ? (
              <button
                type="button"
                onClick={onClose}
                className="flex h-9 w-9 items-center justify-center rounded-xl border border-destructive/20 bg-destructive/10 text-destructive transition-colors hover:bg-destructive/20"
                aria-label={localize(lang, "Закрыть Linux UI", "Close Linux UI")}
              >
                <X className="h-4 w-4" />
              </button>
            ) : null}
          </div>
        </footer>
      </div>
    </div>
  );
}
