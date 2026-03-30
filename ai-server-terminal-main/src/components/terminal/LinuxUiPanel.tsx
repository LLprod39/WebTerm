import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CalendarDays,
  Clock3,
  Code2,
  ChevronRight,
  Copy,
  FileCode2,
  FileText,
  FolderOpen,
  HardDrive,
  LayoutGrid,
  Minus,
  Monitor,
  Network,
  Package,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Server,
  Settings,
  Settings2,
  Shield,
  Square,
  Terminal,
  Volume2,
  Wifi,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { SftpPanel } from "@/components/terminal/SftpPanel";
import { TextEditorWindow } from "@/components/terminal/LinuxUiTextEditor";
import { QuickRunWindow } from "@/components/terminal/LinuxUiQuickRun";
import { SystemSettingsWindow } from "@/components/terminal/LinuxUiSystemSettings";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  fetchLinuxUiCapabilities,
  fetchLinuxUiDisk,
  fetchLinuxUiDocker,
  fetchLinuxUiDockerLogs,
  fetchLinuxUiLogs,
  fetchLinuxUiNetwork,
  fetchLinuxUiOverview,
  fetchLinuxUiPackages,
  fetchLinuxUiProcesses,
  fetchLinuxUiServiceLogs,
  fetchLinuxUiServices,
  type LinuxUiDiskMount,
  type LinuxUiDiskPathStat,
  type LinuxUiDockerAction,
  type LinuxUiDockerActionResult,
  type LinuxUiDockerContainer,
  type FrontendServer,
  type LinuxUiCapabilities,
  type LinuxUiListeningSocket,
  type LinuxUiLogsPayload,
  type LinuxUiNetworkInterface,
  type LinuxUiOverview,
  type LinuxUiPackageItem,
  type LinuxUiProcessAction,
  type LinuxUiProcessActionResult,
  type LinuxUiProcessItem,
  type LinuxUiServiceAction,
  type LinuxUiServiceActionResult,
  type LinuxUiServiceHealth,
  type LinuxUiServiceItem,
  type LinuxUiServicesSummary,
  runLinuxUiDockerAction,
  runLinuxUiProcessAction,
  runLinuxUiServiceAction,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type WorkspaceAppId = "files" | "overview" | "services" | "processes" | "logs" | "disk" | "network" | "docker" | "packages" | "text-editor" | "quick-run" | "settings";
type WorkspaceAppStatus = "live" | "ready" | "next" | "unavailable";

interface LinuxUiPanelProps {
  server: FrontendServer;
  active?: boolean;
  onClose?: () => void;
  onOpenAi?: () => void;
}

interface WorkspaceAppDefinition {
  id: WorkspaceAppId;
  title: string;
  subtitle: string;
  status: WorkspaceAppStatus;
  icon: ReactNode;
  accentClass: string;
  hidden?: boolean;
}

interface WorkspaceWindowState {
  x: number;
  y: number;
  width: number;
  height: number;
  minimized: boolean;
  maximized: boolean;
  restoreX?: number;
  restoreY?: number;
  restoreWidth?: number;
  restoreHeight?: number;
  zIndex: number;
}

interface WorkspaceBounds {
  width: number;
  height: number;
}

interface WorkspaceDragState {
  appId: WorkspaceAppId;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
  bounds: WorkspaceBounds;
}

interface WorkspaceResizeState {
  appId: WorkspaceAppId;
  startX: number;
  startY: number;
  originWidth: number;
  originHeight: number;
  bounds: WorkspaceBounds;
}

const DESKTOP_BREAKPOINT = 1024;
const WINDOW_MARGIN = 16;
const MIN_WINDOW_WIDTH = 420;
const MIN_WINDOW_HEIGHT = 280;
const MAXIMIZED_WINDOW_MARGIN = 10;
const APP_IDS: WorkspaceAppId[] = ["files", "overview", "services", "processes", "logs", "disk", "network", "docker", "packages", "text-editor", "quick-run", "settings"];
const DEFAULT_OPEN_APPS: WorkspaceAppId[] = [];
const DEFAULT_ACTIVE_APP: WorkspaceAppId = "overview";
const DESKTOP_GRID_STYLE: CSSProperties = {
  backgroundImage:
    "linear-gradient(rgba(148,163,184,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.06) 1px, transparent 1px)",
  backgroundSize: "132px 132px",
};

function formatUptime(seconds: number | null) {
  if (!seconds || seconds <= 0) return "Unknown";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatMetric(value: number | null, suffix = "", digits = 0) {
  if (value == null || Number.isNaN(value)) return "N/A";
  return `${value.toFixed(digits)}${suffix}`;
}

function capabilityPills(capabilities: LinuxUiCapabilities | undefined) {
  if (!capabilities) return [];
  return [
    capabilities.commands.systemctl ? "systemctl" : null,
    capabilities.commands.journalctl ? "journalctl" : null,
    capabilities.commands.docker ? "docker" : null,
    capabilities.commands.ss ? "ss" : null,
    capabilities.commands.ip ? "ip" : null,
    capabilities.package_manager ? `pkg:${capabilities.package_manager}` : null,
    capabilities.is_systemd ? "systemd" : null,
  ].filter(Boolean) as string[];
}

function statusClass(status: WorkspaceAppStatus) {
  if (status === "live") return "border-emerald-500/20 bg-emerald-500/8 text-emerald-400";
  if (status === "ready") return "border-primary/20 bg-primary/8 text-primary";
  if (status === "next") return "border-amber-500/20 bg-amber-500/8 text-amber-400";
  return "border-border bg-secondary/70 text-muted-foreground";
}

function workspaceStatusLabel(status: WorkspaceAppStatus) {
  if (status === "live") return "Ready";
  if (status === "ready") return "Available";
  if (status === "next") return "Planned";
  return "Unavailable";
}

function mobileWindowClass(appId: WorkspaceAppId) {
  switch (appId) {
    case "files":
      return "h-[28rem] lg:h-auto";
    case "overview":
      return "h-[24rem] lg:h-auto";
    case "services":
      return "h-[28rem] lg:h-auto";
    case "processes":
      return "h-[24rem] lg:h-auto";
    case "logs":
      return "h-[24rem] lg:h-auto";
    case "disk":
      return "h-[24rem] lg:h-auto";
    case "network":
      return "h-[22rem] lg:h-auto";
    case "docker":
      return "h-[24rem] lg:h-auto";
    case "packages":
      return "h-[22rem] lg:h-auto";
    case "text-editor":
      return "h-[28rem] lg:h-auto";
    case "quick-run":
      return "h-[24rem] lg:h-auto";
    case "settings":
      return "h-[26rem] lg:h-auto";
    default:
      return "h-[22rem]";
  }
}

function getDefaultWindowGeometry(appId: WorkspaceAppId, zIndex: number): WorkspaceWindowState {
  switch (appId) {
    case "files":
      return { x: 40, y: 40, width: 1160, height: 720, minimized: false, maximized: false, zIndex };
    case "overview":
      return { x: 1190, y: 44, width: 392, height: 560, minimized: false, maximized: false, zIndex };
    case "services":
      return { x: 64, y: 48, width: 1240, height: 736, minimized: false, maximized: false, zIndex };
    case "processes":
      return { x: 96, y: 78, width: 980, height: 640, minimized: false, maximized: false, zIndex };
    case "logs":
      return { x: 84, y: 64, width: 1120, height: 680, minimized: false, maximized: false, zIndex };
    case "disk":
      return { x: 92, y: 68, width: 1080, height: 690, minimized: false, maximized: false, zIndex };
    case "network":
      return { x: 118, y: 94, width: 920, height: 620, minimized: false, maximized: false, zIndex };
    case "docker":
      return { x: 74, y: 56, width: 1180, height: 708, minimized: false, maximized: false, zIndex };
    case "packages":
      return { x: 130, y: 108, width: 900, height: 600, minimized: false, maximized: false, zIndex };
    case "text-editor":
      return { x: 60, y: 50, width: 1100, height: 700, minimized: false, maximized: false, zIndex };
    case "quick-run":
      return { x: 100, y: 80, width: 900, height: 600, minimized: false, maximized: false, zIndex };
    case "settings":
      return { x: 80, y: 60, width: 1000, height: 680, minimized: false, maximized: false, zIndex };
    default:
      return { x: 88, y: 56, width: 980, height: 640, minimized: false, maximized: false, zIndex };
  }
}

function buildInitialWindowStates() {
  return Object.fromEntries(
    APP_IDS.map((appId, index) => [appId, getDefaultWindowGeometry(appId, index + 1)]),
  ) as Record<WorkspaceAppId, WorkspaceWindowState>;
}

function getWorkspaceBounds(node: HTMLDivElement | null): WorkspaceBounds {
  return {
    width: Math.max(640, node?.clientWidth || 1280),
    height: Math.max(420, node?.clientHeight || 760),
  };
}

function clampWindowState(state: WorkspaceWindowState, bounds: WorkspaceBounds): WorkspaceWindowState {
  const width = Math.max(MIN_WINDOW_WIDTH, Math.min(state.width, Math.max(MIN_WINDOW_WIDTH, bounds.width - WINDOW_MARGIN * 2)));
  const height = Math.max(MIN_WINDOW_HEIGHT, Math.min(state.height, Math.max(MIN_WINDOW_HEIGHT, bounds.height - WINDOW_MARGIN * 2)));
  const maxX = Math.max(WINDOW_MARGIN, bounds.width - width - WINDOW_MARGIN);
  const maxY = Math.max(WINDOW_MARGIN, bounds.height - height - WINDOW_MARGIN);

  return {
    ...state,
    width,
    height,
    x: Math.min(Math.max(state.x, WINDOW_MARGIN), maxX),
    y: Math.min(Math.max(state.y, WINDOW_MARGIN), maxY),
  };
}

function maximizeWindowState(state: WorkspaceWindowState, bounds: WorkspaceBounds): WorkspaceWindowState {
  return {
    ...state,
    x: MAXIMIZED_WINDOW_MARGIN,
    y: MAXIMIZED_WINDOW_MARGIN,
    width: Math.max(MIN_WINDOW_WIDTH, bounds.width - MAXIMIZED_WINDOW_MARGIN * 2),
    height: Math.max(MIN_WINDOW_HEIGHT, bounds.height - MAXIMIZED_WINDOW_MARGIN * 2),
    minimized: false,
    maximized: true,
    restoreX: state.maximized ? state.restoreX : state.x,
    restoreY: state.maximized ? state.restoreY : state.y,
    restoreWidth: state.maximized ? state.restoreWidth : state.width,
    restoreHeight: state.maximized ? state.restoreHeight : state.height,
  };
}

function normalizeWindowState(state: WorkspaceWindowState, bounds: WorkspaceBounds): WorkspaceWindowState {
  if (state.maximized) {
    return maximizeWindowState(state, bounds);
  }
  return clampWindowState(state, bounds);
}

function pickTopVisibleApp(
  appIds: WorkspaceAppId[],
  states: Record<WorkspaceAppId, WorkspaceWindowState>,
  exclude?: WorkspaceAppId,
) {
  return appIds
    .filter((appId) => appId !== exclude && !states[appId]?.minimized)
    .sort((left, right) => (states[right]?.zIndex || 0) - (states[left]?.zIndex || 0))[0];
}

function DesktopIcon({
  title,
  icon,
  onOpen,
  status,
  accentClass,
}: {
  title: string;
  icon: ReactNode;
  onOpen: () => void;
  status: WorkspaceAppStatus;
  accentClass: string;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group relative flex w-[5.5rem] flex-col items-center gap-2 rounded-2xl p-2.5 text-center transition-colors duration-150 hover:bg-card/80",
        status === "unavailable" && "opacity-40 pointer-events-none",
      )}
    >
      <div
        className={cn(
          "relative flex h-14 w-14 items-center justify-center rounded-[1.15rem] border border-border bg-card text-primary transition-colors duration-150 group-hover:border-primary/20",
          "bg-gradient-to-br",
          accentClass,
        )}
      >
        <div className="absolute inset-[1px] rounded-[1rem] bg-background/80" />
        <div className="relative z-10 [&>svg]:h-5 [&>svg]:w-5">{icon}</div>
        <span
          className={cn(
            "absolute right-1.5 top-1.5 h-2.5 w-2.5 rounded-full border border-card",
            status === "live" ? "bg-emerald-400" : status === "ready" ? "bg-primary" : "bg-muted-foreground",
          )}
        />
      </div>
      <div className="space-y-1">
        <span className="block line-clamp-2 text-[11px] font-medium leading-tight text-foreground">
          {title}
        </span>
        <span className="block text-[11px] text-muted-foreground">
          {workspaceStatusLabel(status)}
        </span>
      </div>
    </button>
  );
}

function DesktopStatCard({
  icon,
  label,
  value,
  hint,
  progress,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint: string;
  progress?: number | null;
}) {
  const clampedProgress = progress == null || Number.isNaN(progress) ? null : Math.max(0, Math.min(progress, 100));

  return (
    <div className="rounded-[1.25rem] border border-border/80 bg-card/95 p-4 text-left">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">{label}</div>
          <div className="mt-2 text-xl font-semibold text-foreground">{value}</div>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary [&>svg]:h-4 [&>svg]:w-4">
          {icon}
        </div>
      </div>
      <div className="mt-2 text-xs leading-5 text-muted-foreground">{hint}</div>
      {clampedProgress != null ? (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full rounded-full bg-primary"
            style={{ width: `${Math.max(clampedProgress, 6)}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

function LauncherMenu({
  apps,
  server,
  query,
  onQueryChange,
  onLaunch,
  onRefresh,
  onShowDesktop,
  onCloseWorkspace,
  openApps,
}: {
  apps: WorkspaceAppDefinition[];
  server: FrontendServer;
  query: string;
  onQueryChange: (value: string) => void;
  onLaunch: (appId: WorkspaceAppId) => void;
  onRefresh: () => void;
  onShowDesktop: () => void;
  onCloseWorkspace?: () => void;
  openApps: WorkspaceAppId[];
}) {
  const normalizedQuery = query.trim().toLowerCase();
  const pinnedAppIds = ["overview", "files", "services", "logs", "quick-run", "settings"];
  const pinnedApps = apps.filter((app) => pinnedAppIds.includes(app.id));
  const filteredApps = apps.filter((app) => {
    if (!normalizedQuery) return true;
    return `${app.title} ${app.subtitle}`.toLowerCase().includes(normalizedQuery);
  });

  return (
      <div className="absolute bottom-[4.35rem] left-0 z-30 w-[min(29rem,calc(100vw-1.5rem))] overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/95 p-4 shadow-[0_24px_80px_-56px_rgba(15,23,42,0.9)]">
        <div className="relative z-10">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-[11px] font-medium text-muted-foreground">Application Launcher</div>
              <div className="mt-2 truncate text-2xl font-semibold tracking-tight text-foreground">{server.name}</div>
              <div className="mt-1 truncate font-mono text-xs text-muted-foreground">{server.username}@{server.host}</div>
            </div>
            <div className="rounded-[1.15rem] border border-primary/20 bg-primary/10 px-3 py-2 text-right">
              <div className="text-[11px] font-medium text-muted-foreground">Running</div>
              <div className="text-lg font-semibold text-foreground">{openApps.length}</div>
            </div>
          </div>

        <div className="relative mt-4">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Search applications, tools, settings..."
              aria-label="Search workspace applications"
              className="h-11 rounded-2xl border-border bg-background pl-10 text-sm text-foreground placeholder:text-muted-foreground"
            />
          </div>

          <div className="mt-5">
            <div className="mb-2 text-[11px] font-medium text-muted-foreground">Pinned</div>
            <div className="grid grid-cols-3 gap-2">
            {pinnedApps.map((app) => (
              <button
                key={app.id}
                type="button"
                onClick={() => onLaunch(app.id)}
                disabled={app.status === "unavailable"}
                className={cn(
                  "rounded-[1.15rem] border border-border px-3 py-3 text-left transition-all duration-150",
                  "bg-background/70 hover:border-primary/25 hover:bg-secondary/70 disabled:cursor-not-allowed disabled:opacity-45",
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
              <div className="text-[11px] font-medium text-muted-foreground">All Applications</div>
              <div className="text-[11px] text-muted-foreground">{filteredApps.length} visible</div>
            </div>
          <div className="max-h-64 space-y-1 overflow-y-auto pr-1">
            {filteredApps.map((app) => (
              <button
                key={app.id}
                type="button"
                onClick={() => onLaunch(app.id)}
                disabled={app.status === "unavailable"}
                className={cn(
                  "flex w-full items-center gap-3 rounded-[1.1rem] border border-transparent px-3 py-2.5 text-left transition-colors",
                  "hover:border-border hover:bg-secondary/60 disabled:cursor-not-allowed disabled:opacity-45",
                )}
              >
                <div className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-border bg-gradient-to-br text-primary", app.accentClass)}>
                  <div className="[&>svg]:h-4 [&>svg]:w-4">{app.icon}</div>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-foreground">{app.title}</span>
                    <span className={cn("rounded-md border px-2 py-0.5 text-[11px] font-medium", statusClass(app.status))}>
                      {workspaceStatusLabel(app.status)}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">{app.subtitle}</div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            ))}
            {filteredApps.length === 0 ? (
              <div className="rounded-[1.1rem] border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
                Nothing matched the current search.
              </div>
            ) : null}
          </div>
        </div>

        <div className="mt-5 grid grid-cols-3 gap-2">
          <Button type="button" variant="outline" className="h-10 rounded-2xl border-border bg-background text-xs text-foreground hover:bg-secondary" onClick={onRefresh}>
            Refresh
          </Button>
          <Button type="button" variant="outline" className="h-10 rounded-2xl border-border bg-background text-xs text-foreground hover:bg-secondary" onClick={onShowDesktop}>
            Show Desktop
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-2xl border-border bg-background text-xs text-foreground hover:bg-secondary"
            onClick={onCloseWorkspace}
            disabled={!onCloseWorkspace}
          >
            Close UI
          </Button>
        </div>
      </div>
    </div>
  );
}

function TaskbarButton({
  title,
  icon,
  active,
  minimized,
  onClick,
  accentClass,
}: {
  title: string;
  icon: ReactNode;
  active: boolean;
  minimized?: boolean;
  onClick: () => void;
  accentClass: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex h-10 min-w-[8rem] items-center gap-2 rounded-[1rem] border px-3 py-2 transition-colors duration-150",
        active
          ? "border-primary/20 bg-secondary text-foreground"
          : minimized
            ? "border-border bg-background/70 text-muted-foreground hover:border-primary/20 hover:bg-secondary/70 hover:text-foreground"
            : "border-border bg-background/80 text-muted-foreground hover:border-primary/20 hover:bg-secondary hover:text-foreground",
      )}
    >
      <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-border bg-gradient-to-br text-primary", accentClass)}>
        <div className="[&>svg]:h-4 [&>svg]:w-4">{icon}</div>
      </div>
      <span className="max-w-28 truncate text-sm">{title}</span>
      {active ? <span className="absolute inset-x-3 bottom-1 h-[3px] rounded-full bg-primary" /> : null}
    </button>
  );
}

function WorkspaceWindow({
  appId,
  title,
  subtitle,
  icon,
  status,
  active,
  minimized,
  maximized,
  desktopMode,
  dragging,
  resizing,
  className,
  style,
  onFocus,
  onMinimize,
  onToggleMaximize,
  onResetPosition,
  onClose,
  onHeaderPointerDown,
  onHeaderDoubleClick,
  onResizePointerDown,
  children,
}: {
  appId: WorkspaceAppId;
  title: string;
  subtitle: string;
  icon: ReactNode;
  status: WorkspaceAppStatus;
  active: boolean;
  minimized?: boolean;
  maximized?: boolean;
  desktopMode: boolean;
  dragging?: boolean;
  resizing?: boolean;
  className?: string;
  style?: CSSProperties;
  onFocus: () => void;
  onMinimize: () => void;
  onToggleMaximize: () => void;
  onResetPosition: () => void;
  onClose: () => void;
  onHeaderPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  onHeaderDoubleClick: () => void;
  onResizePointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  children: ReactNode;
}) {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <section
          onMouseDown={onFocus}
          className={cn(
            "relative flex min-h-0 flex-col overflow-hidden rounded-[1.35rem] border border-border bg-card shadow-[0_18px_60px_-44px_rgba(15,23,42,0.9)]",
            desktopMode ? "absolute" : "relative",
            active ? "border-primary/30" : "",
            dragging || resizing ? "shadow-[0_26px_90px_-54px_rgba(15,23,42,0.95)]" : "",
            className,
          )}
          style={style}
        >
          <header
            onPointerDown={onHeaderPointerDown}
            onDoubleClick={desktopMode ? onHeaderDoubleClick : undefined}
            className={cn(
              "relative z-10 flex h-11 items-center justify-between border-b border-border px-3.5 select-none",
              desktopMode && !maximized ? "cursor-grab active:cursor-grabbing" : "",
            )}
          >
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-border bg-secondary text-primary [&>svg]:h-4 [&>svg]:w-4">
                {icon}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-foreground">{title}</span>
                  <span className={cn("rounded-md border px-2 py-0.5 text-[11px] font-medium", statusClass(status))}>
                    {workspaceStatusLabel(status)}
                  </span>
                </div>
                <div className="truncate text-[11px] text-muted-foreground">{subtitle}</div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                data-no-window-drag="true"
                onClick={onMinimize}
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-background text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                aria-label={`Minimize ${title}`}
              >
                <Minus className="h-3 w-3" />
              </button>
              {desktopMode ? (
                <button
                  type="button"
                  data-no-window-drag="true"
                  onClick={onToggleMaximize}
                    className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-background text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                    aria-label={maximized ? `Restore ${title}` : `Maximize ${title}`}
                  >
                  {maximized ? <Copy className="h-3 w-3" /> : <Square className="h-3 w-3" />}
                </button>
              ) : null}
              <button
                type="button"
                data-no-window-drag="true"
                onClick={onClose}
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-destructive/20 bg-destructive/10 text-destructive transition-colors hover:bg-destructive/20"
                aria-label={`Close ${title}`}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          </header>
          <div className="relative z-10 min-h-0 flex-1 overflow-hidden">{children}</div>
          {desktopMode && !maximized ? (
            <div
              data-no-window-drag="true"
              onPointerDown={onResizePointerDown}
              className="absolute bottom-0 right-0 h-5 w-5 cursor-se-resize"
              aria-hidden="true"
            >
              <div className="absolute bottom-1.5 right-1.5 h-2.5 w-2.5 border-b-2 border-r-2 border-muted-foreground/50" />
            </div>
          ) : null}
        </section>
      </ContextMenuTrigger>
      <ContextMenuContent className="w-48 rounded-lg border-border bg-popover text-popover-foreground">
        <ContextMenuLabel>{title}</ContextMenuLabel>
        <ContextMenuItem onSelect={onFocus}>Focus</ContextMenuItem>
        <ContextMenuItem onSelect={onMinimize}>{minimized ? "Restore" : "Minimize"}</ContextMenuItem>
        {desktopMode ? <ContextMenuItem onSelect={onToggleMaximize}>{maximized ? "Restore" : "Maximize"}</ContextMenuItem> : null}
        {desktopMode ? <ContextMenuItem onSelect={onResetPosition}>Reset Position</ContextMenuItem> : null}
        <ContextMenuSeparator />
        <ContextMenuItem className="text-destructive focus:text-destructive" onSelect={onClose}>Close</ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

function OverviewWindow({
  overview,
  capabilities,
  onOpenFiles,
  onOpenServices,
  onOpenDisk,
  onOpenLogs,
}: {
  overview: LinuxUiOverview | undefined;
  capabilities: LinuxUiCapabilities | undefined;
  onOpenFiles: () => void;
  onOpenServices: () => void;
  onOpenDisk: () => void;
  onOpenLogs: () => void;
}) {
  const pills = capabilityPills(capabilities);
  const cards = [
    { label: "Host", value: overview?.hostname || "N/A", hint: overview?.os_name || "Linux server" },
    { label: "Uptime", value: formatUptime(overview?.uptime_seconds ?? null), hint: overview?.kernel || "Kernel unknown" },
    {
      label: "Load",
      value: overview ? `${formatMetric(overview.load.one, "", 2)} / ${formatMetric(overview.load.five, "", 2)}` : "N/A",
      hint: "1m / 5m",
    },
    {
      label: "Memory",
      value: overview?.memory.percent != null ? `${overview.memory.percent.toFixed(1)}%` : "N/A",
      hint: overview?.memory.used_mb != null && overview.memory.total_mb != null ? `${overview.memory.used_mb} / ${overview.memory.total_mb} MB` : "Usage unavailable",
    },
    {
      label: "Disk",
      value: overview?.disk.percent != null ? `${overview.disk.percent.toFixed(1)}%` : "N/A",
      hint: overview?.disk.used_gb != null && overview.disk.total_gb != null ? `${overview.disk.used_gb} / ${overview.disk.total_gb} GB` : "Root filesystem",
    },
    { label: "Processes", value: overview?.process_count != null ? String(overview.process_count) : "N/A", hint: overview?.cwd || "Working directory" },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-wrap gap-1.5">
          {pills.length > 0 ? (
            pills.map((pill) => (
              <span key={pill} className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                {pill}
              </span>
            ))
          ) : (
            <span className="text-xs text-muted-foreground">Collecting environment markers...</span>
          )}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="grid gap-3">
          {cards.map((card) => (
            <div key={card.label} className="rounded-2xl border border-border/70 bg-background/90 p-3">
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{card.label}</div>
              <div className="mt-2 text-base font-semibold text-foreground">{card.value}</div>
              <div className="mt-1 text-xs text-muted-foreground">{card.hint}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="border-t border-border/60 bg-secondary/25 px-4 py-3">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={onOpenFiles}>
            Open Files
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={onOpenServices}>
            Services
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={onOpenDisk}>
            Disk
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={onOpenLogs}>
            Logs
          </Button>
        </div>
      </div>
    </div>
  );
}

function serviceHealthClass(health: LinuxUiServiceHealth) {
  switch (health) {
    case "active":
      return "border-emerald-500/20 bg-emerald-500/10 text-emerald-300";
    case "failed":
      return "border-destructive/30 bg-destructive/10 text-destructive";
    case "activating":
      return "border-sky-500/20 bg-sky-500/10 text-sky-300";
    case "inactive":
      return "border-border/80 bg-background/94 text-muted-foreground";
    case "deactivating":
      return "border-amber-500/20 bg-amber-500/10 text-amber-300";
    default:
      return "border-border/70 bg-background/92 text-muted-foreground";
  }
}

function serviceActionMeta(action: LinuxUiServiceAction) {
  switch (action) {
    case "start":
      return { label: "Start", confirmLabel: "Start Service", destructive: false, icon: <Play className="h-3.5 w-3.5" /> };
    case "stop":
      return { label: "Stop", confirmLabel: "Stop Service", destructive: true, icon: <Square className="h-3.5 w-3.5" /> };
    case "restart":
      return { label: "Restart", confirmLabel: "Restart Service", destructive: false, icon: <RefreshCw className="h-3.5 w-3.5" /> };
    case "reload":
      return { label: "Reload", confirmLabel: "Reload Service", destructive: false, icon: <RotateCcw className="h-3.5 w-3.5" /> };
    default:
      return { label: action, confirmLabel: action, destructive: false, icon: null };
  }
}

function isConnectionCriticalService(unit: string) {
  const normalized = String(unit || "").trim().toLowerCase();
  return ["ssh.service", "sshd.service", "networking.service", "networkmanager.service", "systemd-networkd.service"].includes(normalized);
}

function SummaryCard({
  label,
  value,
  hint,
  alert,
}: {
  label: string;
  value: string | number;
  hint: string;
  alert?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border px-3 py-3",
        alert ? "border-destructive/35 bg-destructive/10" : "border-border/70 bg-background/90",
      )}
    >
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("mt-2 text-lg font-semibold", alert ? "text-destructive" : "text-foreground")}>{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}

function ServiceListRow({
  service,
  selected,
  onClick,
}: {
  service: LinuxUiServiceItem;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
          : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-foreground">{service.unit}</div>
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{service.description || "No description"}</div>
        </div>
        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", serviceHealthClass(service.health))}>
          {service.health}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">{service.load}</span>
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">
          {service.active}/{service.sub}
        </span>
      </div>
    </button>
  );
}

function ServicesWindow({
  server,
  active,
  servicesEnabled,
  logsEnabled,
  onOpenLogs,
}: {
  server: FrontendServer;
  active: boolean;
  servicesEnabled: boolean;
  logsEnabled: boolean;
  onOpenLogs: () => void;
}) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const [selectedUnit, setSelectedUnit] = useState("");
  const [confirmState, setConfirmState] = useState<{
    service: LinuxUiServiceItem;
    action: LinuxUiServiceAction;
  } | null>(null);
  const [lastAction, setLastAction] = useState<LinuxUiServiceActionResult | null>(null);

  const servicesQuery = useQuery({
    queryKey: ["linux-ui", server.id, "services"],
    queryFn: () => fetchLinuxUiServices(server.id),
    enabled: active && servicesEnabled,
    staleTime: 10_000,
  });

  const services = servicesQuery.data?.services || [];
  const summary: LinuxUiServicesSummary = servicesQuery.data?.summary || {
    total: services.length,
    active: services.filter((item) => item.health === "active").length,
    failed: services.filter((item) => item.health === "failed").length,
    inactive: services.filter((item) => item.health === "inactive").length,
    other: services.filter((item) => !["active", "failed", "inactive"].includes(item.health)).length,
  };

  const filteredServices = useMemo(() => {
    if (!deferredSearch) return services;
    return services.filter((item) => {
      const haystack = `${item.unit} ${item.name} ${item.description} ${item.active} ${item.sub}`.toLowerCase();
      return haystack.includes(deferredSearch);
    });
  }, [deferredSearch, services]);

  useEffect(() => {
    if (!services.length) {
      if (selectedUnit) setSelectedUnit("");
      return;
    }
    const nextList = filteredServices.length ? filteredServices : services;
    if (!nextList.some((item) => item.unit === selectedUnit)) {
      setSelectedUnit(nextList[0].unit);
    }
  }, [filteredServices, selectedUnit, services]);

  const selectedService = useMemo(() => {
    if (!services.length) return null;
    return services.find((item) => item.unit === selectedUnit) || filteredServices[0] || services[0] || null;
  }, [filteredServices, selectedUnit, services]);

  const logsQuery = useQuery({
    queryKey: ["linux-ui", server.id, "service-logs", selectedService?.unit || ""],
    queryFn: () => fetchLinuxUiServiceLogs(server.id, selectedService?.unit || "", 80),
    enabled: active && servicesEnabled && Boolean(selectedService?.unit),
    staleTime: 5_000,
  });

  const serviceActionMutation = useMutation({
    mutationFn: ({ service, action }: { service: string; action: LinuxUiServiceAction }) =>
      runLinuxUiServiceAction(server.id, { service, action }),
    onSuccess: async (response, variables) => {
      setLastAction(response.service_action);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["linux-ui", server.id, "services"] }),
        queryClient.invalidateQueries({ queryKey: ["linux-ui", server.id, "service-logs", variables.service] }),
        queryClient.invalidateQueries({ queryKey: ["linux-ui", server.id, "overview"] }),
      ]);
    },
  });

  const refreshServices = useCallback(() => {
    void servicesQuery.refetch();
    if (selectedService?.unit) {
      void logsQuery.refetch();
    }
  }, [logsQuery, selectedService?.unit, servicesQuery]);

  const confirmDescription = useMemo(() => {
    if (!confirmState) return "";
    const unit = confirmState.service.unit;
    const base =
      confirmState.action === "stop"
        ? `Stop ${unit}? This can interrupt traffic or background workers immediately.`
        : `${serviceActionMeta(confirmState.action).label} ${unit}?`;
    if (isConnectionCriticalService(unit) && ["stop", "restart"].includes(confirmState.action)) {
      return `${base} This service looks connection-critical and may break the current SSH session.`;
    }
    return base;
  }, [confirmState]);

  if (!servicesEnabled) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center p-6">
        <div className="max-w-lg rounded-3xl border border-border/70 bg-background/92 p-6 text-center">
          <AlertTriangle className="mx-auto h-5 w-5 text-amber-300" />
          <div className="mt-3 text-sm font-medium text-foreground">systemctl is not available</div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">
            This host does not expose a systemd control surface, so the Services app cannot manage units here.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">systemd control center</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Search services, inspect their current state, and run safe actions with explicit confirmation.
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter by unit, description, state..."
              className="h-9 min-w-[16rem] bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={refreshServices}>
              <RefreshCw className={cn("h-3.5 w-3.5", (servicesQuery.isFetching || logsQuery.isFetching) && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-4">
          <SummaryCard label="Total" value={summary.total} hint="Loaded units in current slice" />
          <SummaryCard label="Active" value={summary.active} hint="Healthy active services" />
          <SummaryCard label="Failed" value={summary.failed} hint="Needs attention" alert={summary.failed > 0} />
          <SummaryCard label="Inactive" value={summary.inactive} hint="Stopped or dormant units" />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Services
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {filteredServices.length} of {services.length} visible
              </div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {servicesQuery.error instanceof Error ? (
                  <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                    {servicesQuery.error.message}
                  </div>
                ) : null}

                {servicesQuery.isLoading ? (
                  <div className="rounded-2xl border border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    Loading services...
                  </div>
                ) : null}

                {!servicesQuery.isLoading && filteredServices.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    No services match the current filter.
                  </div>
                ) : null}

                {filteredServices.map((service) => (
                  <ServiceListRow
                    key={service.unit}
                    service={service}
                    selected={selectedUnit === service.unit}
                    onClick={() => setSelectedUnit(service.unit)}
                  />
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            {selectedService ? (
              <>
                <div className="border-b border-border/60 px-4 py-4">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate font-mono text-sm text-foreground">{selectedService.unit}</h3>
                        <span className={cn("rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", serviceHealthClass(selectedService.health))}>
                          {selectedService.health}
                        </span>
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          {selectedService.active}/{selectedService.sub}
                        </span>
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">{selectedService.description || "No description available for this unit."}</div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-3">
                        <SummaryCard label="Load" value={selectedService.load} hint="Unit load state" />
                        <SummaryCard label="Active" value={selectedService.active} hint="systemctl active state" alert={selectedService.health === "failed"} />
                        <SummaryCard label="Sub" value={selectedService.sub} hint="systemctl sub-state" />
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 xl:max-w-[16rem] xl:justify-end">
                      {(["start", "restart", "reload", "stop"] as LinuxUiServiceAction[]).map((action) => {
                        const meta = serviceActionMeta(action);
                        return (
                          <Button
                            key={action}
                            type="button"
                            size="sm"
                            variant={action === "stop" ? "destructive" : "outline"}
                            className="h-9 gap-1.5 text-xs"
                            disabled={serviceActionMutation.isPending}
                            onClick={() => setConfirmState({ service: selectedService, action })}
                          >
                            {meta.icon}
                            {meta.label}
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
                  <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-card/88">
                    <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
                      <div>
                        <div className="text-sm font-medium text-foreground">Recent output</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {logsEnabled ? logsQuery.data?.service_logs.source || "journalctl" : "systemctl status fallback"}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          {logsQuery.data?.service_logs.lines || 80} lines
                        </span>
                        {logsEnabled ? (
                          <Button type="button" size="sm" variant="ghost" className="h-8 text-xs" onClick={onOpenLogs}>
                            Logs App
                          </Button>
                        ) : null}
                      </div>
                    </div>
                    <ScrollArea className="h-[18rem] lg:h-full">
                      <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                        {logsQuery.error instanceof Error
                          ? logsQuery.error.message
                          : logsQuery.isLoading
                          ? "Loading recent service output..."
                          : logsQuery.data?.service_logs.content || "No recent service output."}
                      </pre>
                    </ScrollArea>
                  </div>

                  <div className="flex min-h-0 flex-col gap-4">
                    <div className="rounded-3xl border border-border/70 bg-card/88 p-4">
                      <div className="text-sm font-medium text-foreground">Action state</div>
                      <div className="mt-2 text-xs text-muted-foreground">
                        Service actions run through typed Linux UI endpoints instead of raw shell.
                      </div>
                      <div className="mt-4 rounded-2xl border border-border/70 bg-background/94 p-3">
                        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Last action</div>
                        <div className="mt-2 text-sm text-foreground">
                          {lastAction ? `${lastAction.action} ${lastAction.service}` : "No service action has been executed yet."}
                        </div>
                        {lastAction ? (
                          <div className={cn("mt-2 inline-flex rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", lastAction.success ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-destructive/30 bg-destructive/10 text-destructive")}>
                            {lastAction.success ? "success" : "failed"}
                          </div>
                        ) : null}
                      </div>
                      {lastAction?.output ? (
                        <ScrollArea className="mt-3 h-36 rounded-2xl border border-border/70 bg-background/94">
                          <pre className="whitespace-pre-wrap break-words px-3 py-3 font-mono text-[11px] leading-5 text-muted-foreground">
                            {lastAction.output}
                          </pre>
                        </ScrollArea>
                      ) : null}
                      {serviceActionMutation.error instanceof Error ? (
                        <div className="mt-3 rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                          {serviceActionMutation.error.message}
                        </div>
                      ) : null}
                    </div>

                    <div className="rounded-3xl border border-border/70 bg-card/88 p-4 text-xs leading-5 text-muted-foreground">
                      <div className="text-sm font-medium text-foreground">Operational notes</div>
                      <div className="mt-2">Actions may fail if the current account cannot manage system services.</div>
                      <div className="mt-2">Restarting SSH or networking can break the current terminal and workspace session.</div>
                      <div className="mt-2">Use the terminal fallback when you need custom flags or sudo escalation.</div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
                Select a service from the list to inspect state and recent output.
              </div>
            )}
          </section>
        </div>
      </div>

      <ConfirmActionDialog
        open={Boolean(confirmState)}
        onOpenChange={(open) => {
          if (!open) setConfirmState(null);
        }}
        title={confirmState ? `${serviceActionMeta(confirmState.action).label} ${confirmState.service.unit}` : "Confirm service action"}
        description={confirmDescription}
        confirmLabel={confirmState ? serviceActionMeta(confirmState.action).confirmLabel : "Confirm"}
        destructive={Boolean(confirmState && (serviceActionMeta(confirmState.action).destructive || isConnectionCriticalService(confirmState.service.unit)))}
        onConfirm={async () => {
          if (!confirmState) return;
          const current = confirmState;
          setConfirmState(null);
          await serviceActionMutation.mutateAsync({ service: current.service.unit, action: current.action });
        }}
      />
    </div>
  );
}

function processActionMeta(action: LinuxUiProcessAction) {
  switch (action) {
    case "terminate":
      return { label: "Terminate", confirmLabel: "Terminate Process", destructive: false };
    case "kill_force":
      return { label: "Kill -9", confirmLabel: "Force Kill Process", destructive: true };
    default:
      return { label: action, confirmLabel: action, destructive: false };
  }
}

function ProcessListRow({
  process,
  selected,
  onClick,
}: {
  process: LinuxUiProcessItem;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
          : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-foreground">
            {process.command} <span className="text-muted-foreground">pid:{process.pid}</span>
          </div>
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{process.args}</div>
        </div>
        <div className="shrink-0 text-right text-[11px] text-muted-foreground">
          <div>CPU {formatMetric(process.cpu_percent, "%", 1)}</div>
          <div className="mt-1">MEM {formatMetric(process.memory_percent, "%", 1)}</div>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">{process.user}</span>
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">{process.elapsed}</span>
      </div>
    </button>
  );
}

function ProcessesWindow({
  server,
  active,
}: {
  server: FrontendServer;
  active: boolean;
}) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState<"cpu" | "memory">("cpu");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const [selectedPid, setSelectedPid] = useState<number | null>(null);
  const [confirmState, setConfirmState] = useState<{
    process: LinuxUiProcessItem;
    action: LinuxUiProcessAction;
  } | null>(null);
  const [lastAction, setLastAction] = useState<LinuxUiProcessActionResult | null>(null);

  const processesQuery = useQuery({
    queryKey: ["linux-ui", server.id, "processes"],
    queryFn: () => fetchLinuxUiProcesses(server.id),
    enabled: active,
    staleTime: 8_000,
  });

  const processPayload = processesQuery.data?.processes;
  const sourceProcesses = mode === "cpu" ? processPayload?.top_cpu || [] : processPayload?.top_memory || [];
  const filteredProcesses = useMemo(() => {
    if (!deferredSearch) return sourceProcesses;
    return sourceProcesses.filter((item) => {
      const haystack = `${item.pid} ${item.user} ${item.command} ${item.args}`.toLowerCase();
      return haystack.includes(deferredSearch);
    });
  }, [deferredSearch, sourceProcesses]);

  useEffect(() => {
    if (!sourceProcesses.length) {
      if (selectedPid != null) setSelectedPid(null);
      return;
    }
    if (!filteredProcesses.some((item) => item.pid === selectedPid)) {
      setSelectedPid((filteredProcesses[0] || sourceProcesses[0]).pid);
    }
  }, [filteredProcesses, selectedPid, sourceProcesses]);

  const selectedProcess = useMemo(() => {
    return sourceProcesses.find((item) => item.pid === selectedPid) || filteredProcesses[0] || sourceProcesses[0] || null;
  }, [filteredProcesses, selectedPid, sourceProcesses]);

  const processActionMutation = useMutation({
    mutationFn: ({ pid, action }: { pid: number; action: LinuxUiProcessAction }) =>
      runLinuxUiProcessAction(server.id, { pid, action }),
    onSuccess: async (response) => {
      setLastAction(response.process_action);
      await queryClient.invalidateQueries({ queryKey: ["linux-ui", server.id, "processes"] });
    },
  });

  const confirmDescription = useMemo(() => {
    if (!confirmState) return "";
    const base = `${processActionMeta(confirmState.action).label} PID ${confirmState.process.pid}?`;
    if (confirmState.action === "kill_force") {
      return `${base} This sends SIGKILL immediately and the process cannot shut down gracefully.`;
    }
    return `${base} This asks the process to stop gracefully first.`;
  }, [confirmState]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">task manager</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Inspect CPU and memory consumers, then stop bad actors with typed process actions.
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="flex rounded-xl border border-border/70 bg-background/94 p-1">
              <Button type="button" size="sm" variant={mode === "cpu" ? "default" : "ghost"} className="h-8 text-xs" onClick={() => setMode("cpu")}>
                Top CPU
              </Button>
              <Button type="button" size="sm" variant={mode === "memory" ? "default" : "ghost"} className="h-8 text-xs" onClick={() => setMode("memory")}>
                Top Memory
              </Button>
            </div>
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter by pid, command, user..."
              className="h-9 min-w-[16rem] bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void processesQuery.refetch()}>
              <RefreshCw className={cn("h-3.5 w-3.5", processesQuery.isFetching && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          <SummaryCard label="Processes" value={processPayload?.summary.total || 0} hint="Current process count" />
          <SummaryCard label="High CPU" value={processPayload?.summary.high_cpu || 0} hint=">= 20% CPU" alert={(processPayload?.summary.high_cpu || 0) > 0} />
          <SummaryCard label="High Memory" value={processPayload?.summary.high_memory || 0} hint=">= 10% memory" alert={(processPayload?.summary.high_memory || 0) > 0} />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {mode === "cpu" ? "Top CPU" : "Top Memory"}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {filteredProcesses.length} of {sourceProcesses.length} visible
              </div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {processesQuery.error instanceof Error ? (
                  <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                    {processesQuery.error.message}
                  </div>
                ) : null}
                {processesQuery.isLoading ? (
                  <div className="rounded-2xl border border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    Loading processes...
                  </div>
                ) : null}
                {!processesQuery.isLoading && filteredProcesses.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    No processes match the current filter.
                  </div>
                ) : null}
                {filteredProcesses.map((process) => (
                  <ProcessListRow
                    key={`${mode}-${process.pid}`}
                    process={process}
                    selected={selectedPid === process.pid}
                    onClick={() => setSelectedPid(process.pid)}
                  />
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            {selectedProcess ? (
              <>
                <div className="border-b border-border/60 px-4 py-4">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate font-mono text-sm text-foreground">{selectedProcess.command}</h3>
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          pid {selectedProcess.pid}
                        </span>
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          {selectedProcess.user}
                        </span>
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">{selectedProcess.args}</div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-3">
                        <SummaryCard label="CPU" value={formatMetric(selectedProcess.cpu_percent, "%", 1)} hint="Current CPU usage" alert={(selectedProcess.cpu_percent || 0) >= 20} />
                        <SummaryCard label="Memory" value={formatMetric(selectedProcess.memory_percent, "%", 1)} hint="Current memory usage" alert={(selectedProcess.memory_percent || 0) >= 10} />
                        <SummaryCard label="Elapsed" value={selectedProcess.elapsed} hint="Process uptime" />
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 xl:max-w-[16rem] xl:justify-end">
                      {(["terminate", "kill_force"] as LinuxUiProcessAction[]).map((action) => (
                        <Button
                          key={action}
                          type="button"
                          size="sm"
                          variant={action === "kill_force" ? "destructive" : "outline"}
                          className="h-9 text-xs"
                          disabled={processActionMutation.isPending}
                          onClick={() => setConfirmState({ process: selectedProcess, action })}
                        >
                          {processActionMeta(action).label}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
                  <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-card/88">
                    <div className="border-b border-border/60 px-4 py-3">
                      <div className="text-sm font-medium text-foreground">Command line</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Full argv for the selected process.
                      </div>
                    </div>
                    <ScrollArea className="h-[16rem] lg:h-full">
                      <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                        {selectedProcess.args}
                      </pre>
                    </ScrollArea>
                  </div>

                  <div className="flex min-h-0 flex-col gap-4">
                    <div className="rounded-3xl border border-border/70 bg-card/88 p-4">
                      <div className="text-sm font-medium text-foreground">Action state</div>
                      <div className="mt-2 text-xs text-muted-foreground">
                        Graceful terminate first, force kill only when the process ignores SIGTERM.
                      </div>
                      <div className="mt-4 rounded-2xl border border-border/70 bg-background/94 p-3">
                        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Last action</div>
                        <div className="mt-2 text-sm text-foreground">
                          {lastAction ? `${lastAction.action} pid:${lastAction.pid}` : "No process action has been executed yet."}
                        </div>
                        {lastAction ? (
                          <div className={cn("mt-2 inline-flex rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", lastAction.success ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-destructive/30 bg-destructive/10 text-destructive")}>
                            {lastAction.success ? "success" : "failed"}
                          </div>
                        ) : null}
                      </div>
                      {lastAction?.output ? (
                        <ScrollArea className="mt-3 h-36 rounded-2xl border border-border/70 bg-background/94">
                          <pre className="whitespace-pre-wrap break-words px-3 py-3 font-mono text-[11px] leading-5 text-muted-foreground">
                            {lastAction.output}
                          </pre>
                        </ScrollArea>
                      ) : null}
                      {processActionMutation.error instanceof Error ? (
                        <div className="mt-3 rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                          {processActionMutation.error.message}
                        </div>
                      ) : null}
                    </div>

                    <div className="rounded-3xl border border-border/70 bg-card/88 p-4 text-xs leading-5 text-muted-foreground">
                      <div className="text-sm font-medium text-foreground">Operational notes</div>
                      <div className="mt-2">Terminate is safer for app processes because it lets them flush state and close sockets.</div>
                      <div className="mt-2">Force kill is a last resort for wedged workers or runaway CPU consumers.</div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
                Select a process from the list to inspect command line and action state.
              </div>
            )}
          </section>
        </div>
      </div>

      <ConfirmActionDialog
        open={Boolean(confirmState)}
        onOpenChange={(open) => {
          if (!open) setConfirmState(null);
        }}
        title={confirmState ? `${processActionMeta(confirmState.action).label} pid:${confirmState.process.pid}` : "Confirm process action"}
        description={confirmDescription}
        confirmLabel={confirmState ? processActionMeta(confirmState.action).confirmLabel : "Confirm"}
        destructive={Boolean(confirmState && processActionMeta(confirmState.action).destructive)}
        onConfirm={async () => {
          if (!confirmState) return;
          const current = confirmState;
          setConfirmState(null);
          await processActionMutation.mutateAsync({ pid: current.process.pid, action: current.action });
        }}
      />
    </div>
  );
}

const DEFAULT_LOG_PRESETS: LinuxUiLogsPayload["presets"] = [
  { key: "journal", label: "System Journal", description: "Recent lines from journalctl", available: true },
  { key: "service", label: "Service Journal", description: "Logs for a specific systemd unit", available: true },
  { key: "syslog", label: "syslog", description: "/var/log/syslog", available: true },
  { key: "messages", label: "messages", description: "/var/log/messages", available: true },
  { key: "auth", label: "auth.log", description: "/var/log/auth.log", available: true },
  { key: "nginx_error", label: "nginx error", description: "/var/log/nginx/error.log", available: true },
  { key: "nginx_access", label: "nginx access", description: "/var/log/nginx/access.log", available: true },
  { key: "apache_error", label: "apache error", description: "/var/log/apache2/error.log or /var/log/httpd/error_log", available: true },
  { key: "apache_access", label: "apache access", description: "/var/log/apache2/access.log or /var/log/httpd/access_log", available: true },
];

function LogsWindow({
  server,
  active,
  logsEnabled,
}: {
  server: FrontendServer;
  active: boolean;
  logsEnabled: boolean;
}) {
  const [source, setSource] = useState("journal");
  const [serviceName, setServiceName] = useState("");
  const [lines, setLines] = useState(120);

  const logsQuery = useQuery({
    queryKey: ["linux-ui", server.id, "logs", source, serviceName.trim(), lines],
    queryFn: () =>
      fetchLinuxUiLogs(server.id, {
        source,
        service: serviceName.trim(),
        lines,
      }),
    enabled: active && (source !== "service" || Boolean(serviceName.trim())),
    staleTime: 5_000,
  });

  const presetList = logsQuery.data?.logs.presets || DEFAULT_LOG_PRESETS;
  const selectedPreset = presetList.find((item) => item.key === source) || presetList[0];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">log viewer</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Switch between journal presets and common file logs without dropping to the terminal.
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              type="number"
              min={20}
              max={240}
              value={String(lines)}
              onChange={(event) => setLines(Math.max(20, Math.min(240, Number(event.target.value) || 120)))}
              className="h-9 w-28 bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void logsQuery.refetch()}>
              <RefreshCw className={cn("h-3.5 w-3.5", logsQuery.isFetching && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
        {!logsEnabled ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            `journalctl` is unavailable, so the app will prefer file-based sources and systemctl fallbacks.
          </div>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Presets
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                Right now this app covers system, service, and common web stack logs.
              </div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {presetList.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    onClick={() => setSource(preset.key)}
                    className={cn(
                      "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
                      source === preset.key
                        ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
                        : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-foreground">{preset.label}</div>
                        <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{preset.description}</div>
                      </div>
                      <span
                        className={cn(
                          "shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
                          preset.available
                            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                            : "border-border/70 bg-background/94 text-muted-foreground",
                        )}
                      >
                        {preset.available ? "ready" : "missing"}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-4">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-sm font-semibold text-foreground">{selectedPreset?.label || "Logs"}</h3>
                    <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                      {lines} lines
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{selectedPreset?.description}</div>
                </div>
                {source === "service" ? (
                  <Input
                    value={serviceName}
                    onChange={(event) => setServiceName(event.target.value)}
                    placeholder="nginx.service"
                    className="h-9 min-w-[16rem] bg-background/95 text-sm font-mono"
                  />
                ) : null}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-hidden">
              {source === "service" && !serviceName.trim() ? (
                <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
                  Enter a systemd unit name like <span className="mx-1 font-mono">nginx.service</span> to load service logs.
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                    {logsQuery.error instanceof Error
                      ? logsQuery.error.message
                      : logsQuery.isLoading
                      ? "Loading log output..."
                      : logsQuery.data?.logs.content || "No log lines available."}
                  </pre>
                </ScrollArea>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function diskUsageClass(percent: number | null) {
  if ((percent || 0) >= 90) return "border-destructive/30 bg-destructive/10 text-destructive";
  if ((percent || 0) >= 80) return "border-amber-500/20 bg-amber-500/10 text-amber-300";
  return "border-emerald-500/20 bg-emerald-500/10 text-emerald-300";
}

function DiskMountRow({
  mount,
  selected,
  onClick,
}: {
  mount: LinuxUiDiskMount;
  selected: boolean;
  onClick: () => void;
}) {
  const fill = Math.max(0, Math.min(100, mount.percent || 0));

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
          : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-foreground">{mount.mount}</div>
          <div className="mt-1 truncate text-[11px] text-muted-foreground">{mount.filesystem}</div>
        </div>
        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", diskUsageClass(mount.percent))}>
          {mount.percent != null ? `${mount.percent.toFixed(1)}%` : "n/a"}
        </span>
      </div>
      <div className="mt-3 h-2 rounded-full bg-background/96">
        <div
          className={cn(
            "h-2 rounded-full transition-all",
            (mount.percent || 0) >= 90 ? "bg-destructive" : (mount.percent || 0) >= 80 ? "bg-amber-400" : "bg-emerald-400",
          )}
          style={{ width: `${fill}%` }}
        />
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground">
        {mount.used_gb != null && mount.size_gb != null ? `${mount.used_gb} / ${mount.size_gb} GB` : "Usage unavailable"}
      </div>
    </button>
  );
}

function DiskPathRow({
  item,
  label,
  selected,
  onClick,
}: {
  item: LinuxUiDiskPathStat;
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10"
          : "border-border/70 bg-background/90 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-foreground">{item.path}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">{label}</div>
        </div>
        <span className="shrink-0 rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.size_mb != null ? `${item.size_mb} MB` : "n/a"}
        </span>
      </div>
    </button>
  );
}

function DiskWindow({
  server,
  active,
  diskEnabled,
  onOpenInEditor,
}: {
  server: FrontendServer;
  active: boolean;
  diskEnabled: boolean;
  onOpenInEditor?: (path: string) => void;
}) {
  const [selectedMountPath, setSelectedMountPath] = useState<string | null>(null);
  const [mountSearch, setMountSearch] = useState("");
  const [pathSearch, setPathSearch] = useState("");
  const [mountSort, setMountSort] = useState<"usage" | "name" | "size">("usage");
  const [showCriticalOnly, setShowCriticalOnly] = useState(false);
  const [detailTab, setDetailTab] = useState<"directories" | "logs" | "cleanup">("directories");
  const [selectedArtifactPath, setSelectedArtifactPath] = useState<string | null>(null);

  const diskQuery = useQuery({
    queryKey: ["linux-ui", server.id, "disk"],
    queryFn: () => fetchLinuxUiDisk(server.id),
    enabled: active,
    staleTime: 15_000,
  });

  const diskPayload = diskQuery.data?.disk;
  const mounts = diskPayload?.mounts || [];
  const normalizedMountSearch = mountSearch.trim().toLowerCase();
  const normalizedPathSearch = pathSearch.trim().toLowerCase();
  const filteredMounts = useMemo(() => {
    const next = mounts.filter((item) => {
      if (showCriticalOnly && (item.percent || 0) < 80) return false;
      if (!normalizedMountSearch) return true;
      return `${item.mount} ${item.filesystem}`.toLowerCase().includes(normalizedMountSearch);
    });

    return [...next].sort((left, right) => {
      if (mountSort === "name") return left.mount.localeCompare(right.mount);
      if (mountSort === "size") return (right.size_gb || 0) - (left.size_gb || 0);
      return (right.percent || 0) - (left.percent || 0);
    });
  }, [mountSort, mounts, normalizedMountSearch, showCriticalOnly]);

  useEffect(() => {
    if (!filteredMounts.length) {
      if (selectedMountPath != null) setSelectedMountPath(null);
      return;
    }
    if (!filteredMounts.some((item) => item.mount === selectedMountPath)) {
      setSelectedMountPath(filteredMounts[0].mount);
    }
  }, [filteredMounts, selectedMountPath]);

  const selectedMount = useMemo(() => {
    return mounts.find((item) => item.mount === selectedMountPath) || filteredMounts[0] || mounts[0] || null;
  }, [filteredMounts, mounts, selectedMountPath]);

  const isPathInSelectedMount = useCallback((path: string) => {
    if (!selectedMount) return true;
    const mount = selectedMount.mount.replace(/\/+$/, "") || "/";
    if (mount === "/") return true;
    return path === mount || path.startsWith(`${mount}/`);
  }, [selectedMount]);

  const visibleTopDirectories = useMemo(() => {
    return (diskPayload?.top_directories || []).filter((item) => {
      if (!isPathInSelectedMount(item.path)) return false;
      if (!normalizedPathSearch) return true;
      return item.path.toLowerCase().includes(normalizedPathSearch);
    });
  }, [diskPayload?.top_directories, isPathInSelectedMount, normalizedPathSearch]);

  const visibleLargeLogs = useMemo(() => {
    return (diskPayload?.large_logs || []).filter((item) => {
      if (!isPathInSelectedMount(item.path)) return false;
      if (!normalizedPathSearch) return true;
      return item.path.toLowerCase().includes(normalizedPathSearch);
    });
  }, [diskPayload?.large_logs, isPathInSelectedMount, normalizedPathSearch]);

  const visibleCleanupCandidates = useMemo(() => {
    return (diskPayload?.cleanup_candidates || []).filter((item) => {
      if (!isPathInSelectedMount(item)) return false;
      if (!normalizedPathSearch) return true;
      return item.toLowerCase().includes(normalizedPathSearch);
    });
  }, [diskPayload?.cleanup_candidates, isPathInSelectedMount, normalizedPathSearch]);

  const detailItems = useMemo(() => {
    if (detailTab === "directories") {
      return visibleTopDirectories.map((item) => ({
        path: item.path,
        sizeMb: item.size_mb,
        label: "Directory footprint",
        kind: "directory" as const,
      }));
    }
    if (detailTab === "logs") {
      return visibleLargeLogs.map((item) => ({
        path: item.path,
        sizeMb: item.size_mb,
        label: "Log footprint",
        kind: "log" as const,
      }));
    }
    return visibleCleanupCandidates.map((item) => ({
      path: item,
      sizeMb: null,
      label: "Cleanup candidate",
      kind: "cleanup" as const,
    }));
  }, [detailTab, visibleCleanupCandidates, visibleLargeLogs, visibleTopDirectories]);

  useEffect(() => {
    if (!detailItems.length) {
      if (selectedArtifactPath != null) setSelectedArtifactPath(null);
      return;
    }
    if (!detailItems.some((item) => item.path === selectedArtifactPath)) {
      setSelectedArtifactPath(detailItems[0].path);
    }
  }, [detailItems, selectedArtifactPath]);

  const selectedArtifact = useMemo(() => {
    return detailItems.find((item) => item.path === selectedArtifactPath) || detailItems[0] || null;
  }, [detailItems, selectedArtifactPath]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">disk center</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Inspect mounts, spot heavy directories, and surface cleanup candidates before the host runs out of space.
            </div>
          </div>
          <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void diskQuery.refetch()}>
            <RefreshCw className={cn("h-3.5 w-3.5", diskQuery.isFetching && "animate-spin")} />
            Refresh
          </Button>
        </div>
        {!diskEnabled ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            Disk tooling is limited on this host. The workspace will show whatever `df`, `du`, and `find` can provide.
          </div>
        ) : null}
        <div className="mt-4 grid gap-2 md:grid-cols-4">
          <SummaryCard label="Mounts" value={diskPayload?.summary.mounts || 0} hint="Visible filesystems" />
          <SummaryCard label="Critical" value={diskPayload?.summary.critical_mounts || 0} hint=">= 90% full" alert={(diskPayload?.summary.critical_mounts || 0) > 0} />
          <SummaryCard label="Top Dir" value={diskPayload?.summary.top_directory_mb != null ? `${diskPayload.summary.top_directory_mb} MB` : "N/A"} hint="Largest common root discovered" />
          <SummaryCard label="Cleanup" value={diskPayload?.summary.cleanup_candidates || 0} hint="Old /tmp candidates" alert={(diskPayload?.summary.cleanup_candidates || 0) > 0} />
        </div>
        <div className="mt-4 flex flex-col gap-2 xl:flex-row xl:items-center">
          <Input
            value={mountSearch}
            onChange={(event) => setMountSearch(event.target.value)}
            placeholder="Filter mounts..."
            className="h-9 min-w-[14rem] bg-background/95 text-sm"
          />
          <Input
            value={pathSearch}
            onChange={(event) => setPathSearch(event.target.value)}
            placeholder="Filter directories, logs, cleanup..."
            className="h-9 min-w-[18rem] bg-background/95 text-sm"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant={showCriticalOnly ? "default" : "outline"} className="h-9 text-xs" onClick={() => setShowCriticalOnly((current) => !current)}>
              Critical only
            </Button>
            {([
              { value: "usage", label: "Usage" },
              { value: "size", label: "Size" },
              { value: "name", label: "Name" },
            ] as const).map((item) => (
              <Button
                key={item.value}
                type="button"
                size="sm"
                variant={mountSort === item.value ? "default" : "outline"}
                className="h-9 text-xs"
                onClick={() => setMountSort(item.value)}
              >
                {item.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Mounts</div>
              <div className="mt-1 text-xs text-muted-foreground">{filteredMounts.length} of {mounts.length} filesystems visible</div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {diskQuery.error instanceof Error ? (
                  <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                    {diskQuery.error.message}
                  </div>
                ) : null}
                {diskQuery.isLoading ? (
                  <div className="rounded-2xl border border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    Loading disk data...
                  </div>
                ) : null}
                {!diskQuery.isLoading && filteredMounts.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    No mounts match the current filter.
                  </div>
                ) : null}
                {filteredMounts.map((mount) => (
                  <DiskMountRow
                    key={`${mount.filesystem}-${mount.mount}`}
                    mount={mount}
                    selected={selectedMount?.mount === mount.mount}
                    onClick={() => setSelectedMountPath(mount.mount)}
                  />
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="grid min-h-0 gap-4 lg:grid-rows-[auto_auto_minmax(0,1fr)]">
            <div className="rounded-3xl border border-border/70 bg-background/88 p-4">
              {selectedMount ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-mono text-sm text-foreground">{selectedMount.mount}</h3>
                    <span className={cn("rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", diskUsageClass(selectedMount.percent))}>
                      {selectedMount.percent != null ? `${selectedMount.percent.toFixed(1)}% full` : "usage unknown"}
                    </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => void navigator.clipboard.writeText(selectedMount.mount)}>
                        <Copy className="mr-1.5 h-3.5 w-3.5" />
                        Copy mount
                      </Button>
                      {onOpenInEditor && visibleLargeLogs[0] ? (
                        <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => onOpenInEditor(visibleLargeLogs[0].path)}>
                          <FileCode2 className="mr-1.5 h-3.5 w-3.5" />
                          Open top log
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{selectedMount.filesystem}</div>
                  <div className="mt-4 h-3 rounded-full bg-background/96">
                    <div
                      className={cn(
                        "h-3 rounded-full transition-all",
                        (selectedMount.percent || 0) >= 90 ? "bg-destructive" : (selectedMount.percent || 0) >= 80 ? "bg-amber-400" : "bg-emerald-400",
                      )}
                      style={{ width: `${Math.max(0, Math.min(100, selectedMount.percent || 0))}%` }}
                    />
                  </div>
                  <div className="mt-4 grid gap-2 sm:grid-cols-3">
                    <SummaryCard label="Size" value={selectedMount.size_gb != null ? `${selectedMount.size_gb} GB` : "N/A"} hint="Total filesystem size" />
                    <SummaryCard label="Used" value={selectedMount.used_gb != null ? `${selectedMount.used_gb} GB` : "N/A"} hint="Allocated space" alert={(selectedMount.percent || 0) >= 80} />
                    <SummaryCard label="Free" value={selectedMount.available_gb != null ? `${selectedMount.available_gb} GB` : "N/A"} hint="Available capacity" />
                  </div>
                </>
              ) : (
                <div className="text-sm text-muted-foreground">Select a mount to inspect filesystem pressure.</div>
              )}
            </div>

            <div className="rounded-3xl border border-border/70 bg-background/88 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                {([
                  { value: "directories", label: `Directories (${visibleTopDirectories.length})` },
                  { value: "logs", label: `Logs (${visibleLargeLogs.length})` },
                  { value: "cleanup", label: `Cleanup (${visibleCleanupCandidates.length})` },
                ] as const).map((item) => (
                  <Button
                    key={item.value}
                    type="button"
                    size="sm"
                    variant={detailTab === item.value ? "default" : "outline"}
                    className="h-8 text-xs"
                    onClick={() => setDetailTab(item.value)}
                  >
                    {item.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="grid min-h-0 gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
              <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
                <div className="border-b border-border/60 px-4 py-3">
                  <div className="text-sm font-medium text-foreground">
                    {detailTab === "directories" ? "Largest directories" : detailTab === "logs" ? "Largest logs" : "Cleanup candidates"}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {detailTab === "directories"
                      ? "Common writable roots only. This keeps the scan responsive."
                      : detailTab === "logs"
                        ? "Heavy log files are often the fastest cleanup win."
                        : "Old top-level `/tmp` entries are surfaced here first."}
                  </div>
                </div>
                <ScrollArea className="h-full">
                  <div className="space-y-2 p-3">
                    {detailItems.length > 0 ? detailItems.map((item) => (
                      item.kind === "cleanup" ? (
                        <button
                          key={item.path}
                          type="button"
                          onClick={() => setSelectedArtifactPath(item.path)}
                          className={cn(
                            "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
                            selectedArtifact?.path === item.path
                              ? "border-primary/30 bg-primary/10"
                              : "border-border/70 bg-background/90 hover:border-primary/20 hover:bg-secondary/50",
                          )}
                        >
                          <div className="font-mono text-xs text-foreground">{item.path}</div>
                          <div className="mt-1 text-[11px] text-muted-foreground">{item.label}</div>
                        </button>
                      ) : (
                        <DiskPathRow
                          key={item.path}
                          item={{ path: item.path, size_mb: item.sizeMb }}
                          label={item.label}
                          selected={selectedArtifact?.path === item.path}
                          onClick={() => setSelectedArtifactPath(item.path)}
                        />
                      )
                    )) : (
                      <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                        No items match the current storage filter.
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </section>

              <section className="min-h-0 rounded-3xl border border-border/70 bg-background/88 p-4">
                {selectedArtifact ? (
                  <div className="space-y-4">
                    <div>
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{selectedArtifact.label}</div>
                      <div className="mt-2 break-all font-mono text-xs text-foreground">{selectedArtifact.path}</div>
                    </div>
                    <div className="grid gap-2">
                      <SummaryCard
                        label="Type"
                        value={selectedArtifact.kind}
                        hint={selectedMount ? selectedMount.mount : "Selected storage object"}
                      />
                      <SummaryCard
                        label="Size"
                        value={selectedArtifact.sizeMb != null ? `${selectedArtifact.sizeMb} MB` : "N/A"}
                        hint={selectedArtifact.kind === "cleanup" ? "Temporary candidate size unavailable" : "Reported footprint"}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Button type="button" size="sm" variant="outline" className="h-9 justify-start text-xs" onClick={() => void navigator.clipboard.writeText(selectedArtifact.path)}>
                        <Copy className="mr-2 h-3.5 w-3.5" />
                        Copy path
                      </Button>
                      {selectedArtifact.kind === "log" && onOpenInEditor ? (
                        <Button type="button" size="sm" variant="outline" className="h-9 justify-start text-xs" onClick={() => onOpenInEditor(selectedArtifact.path)}>
                          <FileCode2 className="mr-2 h-3.5 w-3.5" />
                          Open in editor
                        </Button>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">Select a directory, log, or cleanup candidate to inspect it.</div>
                )}
              </section>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function NetworkInterfaceRow({
  item,
  selected,
  onClick,
}: {
  item: LinuxUiNetworkInterface;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
          : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-foreground">{item.name}</div>
          <div className="mt-1 text-xs text-muted-foreground">{item.kind} {item.mac ? `• ${item.mac}` : ""}</div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
            item.state === "UP"
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
              : "border-border/70 bg-background/94 text-muted-foreground",
          )}
        >
          {item.state}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">
          {item.addresses.length} addr
        </span>
        {item.mtu != null ? (
          <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">
            mtu {item.mtu}
          </span>
        ) : null}
      </div>
    </button>
  );
}

function extractSocketPort(localAddress: string) {
  const raw = String(localAddress || "").trim();
  if (!raw) return "";
  const bracketMatch = raw.match(/\]:(\d+)$/);
  if (bracketMatch?.[1]) return bracketMatch[1];
  const plainMatch = raw.match(/:(\d+)$/);
  return plainMatch?.[1] || "";
}

function isSocketExposed(localAddress: string) {
  const raw = String(localAddress || "").trim().toLowerCase();
  return raw.startsWith("0.0.0.0:") || raw.startsWith("[::]:") || raw.startsWith("*:") || raw.startsWith(":::") || raw === "::";
}

function ListeningSocketRow({
  item,
  selected,
  onClick,
}: {
  item: LinuxUiListeningSocket;
  selected: boolean;
  onClick: () => void;
}) {
  const exposed = isSocketExposed(item.local_address);

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10"
          : "border-border/70 bg-background/90 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.protocol}
        </span>
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.state || "unknown"}
        </span>
        {exposed ? (
          <span className="rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-destructive">
            exposed
          </span>
        ) : null}
        {extractSocketPort(item.local_address) ? (
          <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            port {extractSocketPort(item.local_address)}
          </span>
        ) : null}
      </div>
      <div className="mt-2 font-mono text-xs text-foreground">{item.local_address || "n/a"}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{item.process || item.peer_address || "Process metadata unavailable"}</div>
    </button>
  );
}

function NetworkWindow({
  server,
  active,
  networkEnabled,
}: {
  server: FrontendServer;
  active: boolean;
  networkEnabled: boolean;
}) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const [selectedInterfaceName, setSelectedInterfaceName] = useState<string | null>(null);
  const [selectedSocketKey, setSelectedSocketKey] = useState<string | null>(null);
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);
  const [protocolFilter, setProtocolFilter] = useState<"all" | "tcp" | "udp">("all");
  const [showUpOnly, setShowUpOnly] = useState(false);
  const [showExposedOnly, setShowExposedOnly] = useState(false);
  const [networkTab, setNetworkTab] = useState<"interfaces" | "sockets" | "routes">("interfaces");

  const networkQuery = useQuery({
    queryKey: ["linux-ui", server.id, "network"],
    queryFn: () => fetchLinuxUiNetwork(server.id),
    enabled: active,
    staleTime: 10_000,
  });

  const networkPayload = networkQuery.data?.network;
  const interfaces = networkPayload?.interfaces || [];
  const filteredInterfaces = useMemo(() => {
    return interfaces.filter((item) => {
      if (showUpOnly && item.state !== "UP") return false;
      const haystack = [
        item.name,
        item.state,
        item.kind,
        item.mac,
        ...item.flags,
        ...item.addresses.map((address) => `${address.family} ${address.address} ${address.scope}`),
      ]
        .join(" ")
        .toLowerCase();
      return !deferredSearch || haystack.includes(deferredSearch);
    });
  }, [deferredSearch, interfaces, showUpOnly]);

  const filteredListening = useMemo(() => {
    const listening = networkPayload?.listening || [];
    return listening.filter((item) =>
      {
        if (protocolFilter !== "all" && !item.protocol.toLowerCase().includes(protocolFilter)) return false;
        if (showExposedOnly && !isSocketExposed(item.local_address)) return false;
        const haystack = `${item.protocol} ${item.state} ${item.local_address} ${item.peer_address} ${item.process}`.toLowerCase();
        return !deferredSearch || haystack.includes(deferredSearch);
      },
    );
  }, [deferredSearch, networkPayload?.listening, protocolFilter, showExposedOnly]);

  const filteredRoutes = useMemo(() => {
    const routes = networkPayload?.routes || [];
    if (!deferredSearch) return routes;
    return routes.filter((route) => route.toLowerCase().includes(deferredSearch));
  }, [deferredSearch, networkPayload?.routes]);

  useEffect(() => {
    if (!interfaces.length) {
      if (selectedInterfaceName != null) setSelectedInterfaceName(null);
      return;
    }
    if (!filteredInterfaces.some((item) => item.name === selectedInterfaceName)) {
      setSelectedInterfaceName((filteredInterfaces[0] || interfaces[0]).name);
    }
  }, [filteredInterfaces, interfaces, selectedInterfaceName]);

  const selectedInterface = useMemo(() => {
    return interfaces.find((item) => item.name === selectedInterfaceName) || filteredInterfaces[0] || interfaces[0] || null;
  }, [filteredInterfaces, interfaces, selectedInterfaceName]);

  useEffect(() => {
    if (!filteredListening.length) {
      if (selectedSocketKey != null) setSelectedSocketKey(null);
      return;
    }
    const socketKeys = filteredListening.map((item) => `${item.protocol}:${item.local_address}:${item.process}`);
    if (!selectedSocketKey || !socketKeys.includes(selectedSocketKey)) {
      setSelectedSocketKey(socketKeys[0]);
    }
  }, [filteredListening, selectedSocketKey]);

  const selectedSocket = useMemo(() => {
    return filteredListening.find((item) => `${item.protocol}:${item.local_address}:${item.process}` === selectedSocketKey) || filteredListening[0] || null;
  }, [filteredListening, selectedSocketKey]);

  useEffect(() => {
    if (!filteredRoutes.length) {
      if (selectedRoute != null) setSelectedRoute(null);
      return;
    }
    if (!selectedRoute || !filteredRoutes.includes(selectedRoute)) {
      setSelectedRoute(filteredRoutes[0]);
    }
  }, [filteredRoutes, selectedRoute]);

  const selectedSocketPort = selectedSocket ? extractSocketPort(selectedSocket.local_address) : "";
  const exposedCount = filteredListening.filter((item) => isSocketExposed(item.local_address)).length;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">network center</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Inspect interfaces, routes, and listening sockets without leaving the workspace shell.
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter interfaces, ports, routes..."
              className="h-9 min-w-[16rem] bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void networkQuery.refetch()}>
              <RefreshCw className={cn("h-3.5 w-3.5", networkQuery.isFetching && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
        {!networkEnabled ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            Network tooling is limited on this host. The workspace will show whatever is available from `ip`, `ss`, or fallbacks.
          </div>
        ) : null}
        <div className="mt-4 grid gap-2 md:grid-cols-4">
          <SummaryCard label="Interfaces" value={networkPayload?.summary.interfaces || 0} hint="Detected links" />
          <SummaryCard label="Addresses" value={networkPayload?.summary.addresses || 0} hint="IPv4 and IPv6 addresses" />
          <SummaryCard label="Routes" value={networkPayload?.summary.routes || 0} hint="Visible route entries" />
          <SummaryCard label="Listening" value={networkPayload?.summary.listening || 0} hint="Open listening sockets" alert={(networkPayload?.summary.listening || 0) > 0} />
        </div>
        <div className="mt-4 flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant={showUpOnly ? "default" : "outline"} className="h-9 text-xs" onClick={() => setShowUpOnly((current) => !current)}>
              Up only
            </Button>
            <Button type="button" size="sm" variant={showExposedOnly ? "default" : "outline"} className="h-9 text-xs" onClick={() => setShowExposedOnly((current) => !current)}>
              Exposed only
            </Button>
            {([
              { value: "all", label: "All protocols" },
              { value: "tcp", label: "TCP" },
              { value: "udp", label: "UDP" },
            ] as const).map((item) => (
              <Button
                key={item.value}
                type="button"
                size="sm"
                variant={protocolFilter === item.value ? "default" : "outline"}
                className="h-9 text-xs"
                onClick={() => setProtocolFilter(item.value)}
              >
                {item.label}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span className="rounded-full border border-border/70 bg-background/94 px-2 py-1">
              ip {networkPayload?.tools.ip ? "ready" : "missing"}
            </span>
            <span className="rounded-full border border-border/70 bg-background/94 px-2 py-1">
              ss {networkPayload?.tools.ss ? "ready" : "missing"}
            </span>
            <span className="rounded-full border border-destructive/20 bg-destructive/10 px-2 py-1 text-destructive">
              exposed {exposedCount}
            </span>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Interfaces</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {filteredInterfaces.length} of {interfaces.length} visible
              </div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {networkQuery.error instanceof Error ? (
                  <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                    {networkQuery.error.message}
                  </div>
                ) : null}
                {networkQuery.isLoading ? (
                  <div className="rounded-2xl border border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    Loading network data...
                  </div>
                ) : null}
                {!networkQuery.isLoading && filteredInterfaces.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    No interfaces match the current filter.
                  </div>
                ) : null}
                {filteredInterfaces.map((item) => (
                  <NetworkInterfaceRow
                    key={item.name}
                    item={item}
                    selected={selectedInterfaceName === item.name}
                    onClick={() => setSelectedInterfaceName(item.name)}
                  />
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="grid min-h-0 gap-4 lg:grid-rows-[auto_auto_minmax(0,1fr)_14rem]">
            <div className="rounded-3xl border border-border/70 bg-background/88 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                {([
                  { value: "interfaces", label: `Interfaces (${filteredInterfaces.length})` },
                  { value: "sockets", label: `Sockets (${filteredListening.length})` },
                  { value: "routes", label: `Routes (${filteredRoutes.length})` },
                ] as const).map((item) => (
                  <Button
                    key={item.value}
                    type="button"
                    size="sm"
                    variant={networkTab === item.value ? "default" : "outline"}
                    className="h-8 text-xs"
                    onClick={() => setNetworkTab(item.value)}
                  >
                    {item.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="rounded-3xl border border-border/70 bg-background/88 p-4">
              {networkTab === "interfaces" && selectedInterface ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-mono text-sm text-foreground">{selectedInterface.name}</h3>
                      <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                        {selectedInterface.state}
                      </span>
                      {selectedInterface.mtu != null ? (
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          mtu {selectedInterface.mtu}
                        </span>
                      ) : null}
                    </div>
                    <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => void navigator.clipboard.writeText(selectedInterface.name)}>
                      <Copy className="mr-1.5 h-3.5 w-3.5" />
                      Copy iface
                    </Button>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    {selectedInterface.kind} {selectedInterface.mac ? `• ${selectedInterface.mac}` : ""}
                  </div>
                  <div className="mt-4 grid gap-2 lg:grid-cols-2">
                    <div className="rounded-2xl border border-border/70 bg-card/88 p-3">
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Addresses</div>
                      <div className="mt-2 space-y-2">
                        {selectedInterface.addresses.length > 0 ? selectedInterface.addresses.map((address) => (
                          <div key={`${address.family}-${address.address}`} className="rounded-xl border border-border/70 bg-background/94 px-3 py-2">
                            <div className="font-mono text-xs text-foreground">{address.address}</div>
                            <div className="mt-1 text-[11px] text-muted-foreground">
                              {address.family}{address.scope ? ` • ${address.scope}` : ""}
                            </div>
                          </div>
                        )) : (
                          <div className="text-xs text-muted-foreground">No addresses detected.</div>
                        )}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-card/88 p-3">
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Flags</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {selectedInterface.flags.length > 0 ? selectedInterface.flags.map((flag) => (
                          <span key={flag} className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                            {flag}
                          </span>
                        )) : (
                          <div className="text-xs text-muted-foreground">No flags reported.</div>
                        )}
                      </div>
                    </div>
                  </div>
                </>
              ) : null}
              {networkTab === "sockets" && selectedSocket ? (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-mono text-sm text-foreground">{selectedSocket.local_address || "n/a"}</h3>
                      <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                        {selectedSocket.protocol}
                      </span>
                      {isSocketExposed(selectedSocket.local_address) ? (
                        <span className="rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-destructive">
                          exposed
                        </span>
                      ) : null}
                    </div>
                    <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => void navigator.clipboard.writeText(selectedSocket.local_address)}>
                      <Copy className="mr-1.5 h-3.5 w-3.5" />
                      Copy socket
                    </Button>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <SummaryCard label="Port" value={selectedSocketPort || "N/A"} hint="Parsed from bind address" />
                    <SummaryCard label="State" value={selectedSocket.state || "unknown"} hint="Reported listener state" />
                    <SummaryCard label="Exposure" value={isSocketExposed(selectedSocket.local_address) ? "Public" : "Local"} hint="Bind scope" alert={isSocketExposed(selectedSocket.local_address)} />
                  </div>
                  <div className="rounded-2xl border border-border/70 bg-card/88 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Process</div>
                    <div className="mt-2 font-mono text-xs text-foreground">{selectedSocket.process || "Process metadata unavailable"}</div>
                    <div className="mt-2 text-[11px] text-muted-foreground">{selectedSocket.peer_address || "No peer metadata"}</div>
                  </div>
                </div>
              ) : null}
              {networkTab === "routes" ? (
                selectedRoute ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-medium text-foreground">Selected route</h3>
                      <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => void navigator.clipboard.writeText(selectedRoute)}>
                        <Copy className="mr-1.5 h-3.5 w-3.5" />
                        Copy route
                      </Button>
                    </div>
                    <pre className="whitespace-pre-wrap break-words rounded-2xl border border-border/70 bg-card/88 px-3 py-3 font-mono text-[11px] leading-5 text-foreground">
                      {selectedRoute}
                    </pre>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">Select a route to inspect it.</div>
                )
              ) : null}
            </div>

            <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
              <div className="border-b border-border/60 px-4 py-3">
                <div className="text-sm font-medium text-foreground">Listening sockets</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {filteredListening.length} sockets visible
                </div>
              </div>
              <ScrollArea className="h-full max-h-full">
                <div className="space-y-2 p-3">
                  {filteredListening.length > 0 ? filteredListening.map((item, index) => {
                    const socketKey = `${item.protocol}:${item.local_address}:${item.process}`;
                    return (
                      <ListeningSocketRow
                        key={`${socketKey}-${index}`}
                        item={item}
                        selected={selectedSocketKey === socketKey}
                        onClick={() => {
                          setSelectedSocketKey(socketKey);
                          setNetworkTab("sockets");
                        }}
                      />
                    );
                  }) : (
                    <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                      No listening sockets match the current filter.
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>

            <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
              <div className="border-b border-border/60 px-4 py-3">
                <div className="text-sm font-medium text-foreground">Routes</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {filteredRoutes.length} routes visible
                </div>
              </div>
              <ScrollArea className="h-full">
                <div className="space-y-2 p-3">
                  {filteredRoutes.length > 0 ? filteredRoutes.map((route) => (
                    <button
                      key={route}
                      type="button"
                      onClick={() => {
                        setSelectedRoute(route);
                        setNetworkTab("routes");
                      }}
                      className={cn(
                        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
                        selectedRoute === route
                          ? "border-primary/30 bg-primary/10"
                          : "border-border/70 bg-background/90 hover:border-primary/20 hover:bg-secondary/50",
                      )}
                    >
                      <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-foreground">{route}</pre>
                    </button>
                  )) : (
                    <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                      No route entries match the current filter.
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function PackageRow({ item }: { item: LinuxUiPackageItem }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border/70 bg-background/90 px-3 py-2">
      <span className="truncate font-mono text-xs text-foreground">{item.name}</span>
      <span className="shrink-0 ml-2 text-[10px] text-muted-foreground font-mono">{item.version}</span>
    </div>
  );
}

function PackagesWindow({ server, active, packageManager }: { server: FrontendServer; active: boolean; packageManager: string }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const [installPkg, setInstallPkg] = useState("");
  const [actionOutput, setActionOutput] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [tab, setTab] = useState<"installed" | "updates" | "actions">("installed");

  const packagesQuery = useQuery({
    queryKey: ["linux-ui", server.id, "packages"],
    queryFn: () => fetchLinuxUiPackages(server.id),
    enabled: active && Boolean(packageManager),
    staleTime: 20_000,
  });
  const packagesPayload = packagesQuery.data?.packages;
  const installedPackages = useMemo(() => {
    const items = packagesPayload?.installed || [];
    if (!deferredSearch) return items;
    return items.filter((item) => `${item.name} ${item.version}`.toLowerCase().includes(deferredSearch));
  }, [deferredSearch, packagesPayload?.installed]);
  const updateLines = useMemo(() => {
    const items = packagesPayload?.updates || [];
    if (!deferredSearch) return items;
    return items.filter((item) => item.toLowerCase().includes(deferredSearch));
  }, [deferredSearch, packagesPayload?.updates]);

  const runPkgCmd = useCallback(async (cmd: string) => {
    setIsRunning(true);
    setActionOutput(`$ ${cmd}\n`);
    try {
      const { executeServerCommand } = await import("@/lib/api");
      const res = await executeServerCommand(server.id, cmd);
      setActionOutput((p) => p + [res.output?.stdout, res.output?.stderr, res.error].filter(Boolean).join("\n") + `\nExit: ${res.output?.exit_code ?? "?"}`);
      void queryClient.invalidateQueries({ queryKey: ["linux-ui", server.id, "packages"] });
    } catch (err) {
      setActionOutput((p) => p + (err instanceof Error ? err.message : "Failed"));
    } finally { setIsRunning(false); }
  }, [server.id, queryClient]);

  const installCmd = installPkg.trim() ? (
    packageManager === "apt" ? `apt-get install -y ${installPkg.trim()}` :
    packageManager === "yum" ? `yum install -y ${installPkg.trim()}` :
    packageManager === "dnf" ? `dnf install -y ${installPkg.trim()}` :
    packageManager === "pacman" ? `pacman -S --noconfirm ${installPkg.trim()}` :
    packageManager === "apk" ? `apk add ${installPkg.trim()}` : ""
  ) : "";
  const updateCmd =
    packageManager === "apt" ? "apt-get update && apt-get upgrade -y" :
    packageManager === "yum" ? "yum update -y" :
    packageManager === "dnf" ? "dnf upgrade -y" :
    packageManager === "pacman" ? "pacman -Syu --noconfirm" :
    packageManager === "apk" ? "apk update && apk upgrade" : "";

  if (!packageManager) return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">No package manager detected.</div>;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex items-center gap-0.5 border-b border-border/60 bg-muted/30 px-2">
        {(["installed", "updates", "actions"] as const).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)} className={cn("px-3 py-2 text-xs", tab === t ? "text-foreground border-b-2 border-primary" : "text-muted-foreground hover:text-foreground")}>
            {t === "installed" ? `Packages (${installedPackages.length})` : t === "updates" ? "Updates" : "Install / Update"}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 py-1">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter..." className="h-7 w-40 text-xs" />
          <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => void packagesQuery.refetch()}>
            <RefreshCw className={cn("h-3 w-3", packagesQuery.isFetching && "animate-spin")} />
          </Button>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="p-3">
          {tab === "installed" && (
            <div className="space-y-1">
              {packagesQuery.isLoading ? <div className="py-8 text-center text-sm text-muted-foreground">Loading...</div>
                : installedPackages.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No matches.</div>
                : installedPackages.map((item) => <PackageRow key={`${item.name}-${item.version}`} item={item} />)}
            </div>
          )}
          {tab === "updates" && (
            <pre className="whitespace-pre-wrap font-mono text-[11px] leading-5 text-foreground">{updateLines.length > 0 ? updateLines.join("\n") : "No updates available."}</pre>
          )}
          {tab === "actions" && (
            <div className="space-y-3">
              <div className="rounded-xl border border-border/70 bg-background/90 p-3">
                <div className="text-xs font-medium text-foreground mb-2">Install Package</div>
                <div className="flex items-center gap-2">
                  <Input value={installPkg} onChange={(e) => setInstallPkg(e.target.value)} placeholder="e.g. nginx htop" className="h-8 flex-1 text-xs font-mono"
                    onKeyDown={(e) => { if (e.key === "Enter" && installCmd) void runPkgCmd(installCmd); }} />
                  <Button type="button" size="sm" className="h-8 text-xs" disabled={!installCmd || isRunning} onClick={() => void runPkgCmd(installCmd)}>Install</Button>
                </div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/90 p-3">
                <div className="text-xs font-medium text-foreground mb-2">System Update</div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded bg-muted px-2 py-1.5 text-[11px] text-muted-foreground font-mono">{updateCmd}</code>
                  <Button type="button" size="sm" variant="outline" className="h-8 text-xs" disabled={isRunning} onClick={() => void runPkgCmd(updateCmd)}>Update</Button>
                </div>
              </div>
              {actionOutput && (
                <div className="rounded-xl border border-border/70 bg-card p-3">
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-5 text-foreground/80">{actionOutput}</pre>
                </div>
              )}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function dockerActionMeta(action: LinuxUiDockerAction) {
  switch (action) {
    case "start":
      return { label: "Start", confirmLabel: "Start Container", destructive: false };
    case "stop":
      return { label: "Stop", confirmLabel: "Stop Container", destructive: true };
    case "restart":
      return { label: "Restart", confirmLabel: "Restart Container", destructive: false };
    default:
      return { label: action, confirmLabel: action, destructive: false };
  }
}

function DockerContainerRow({
  item,
  selected,
  onClick,
}: {
  item: LinuxUiDockerContainer;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
          : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-foreground">{item.name}</div>
          <div className="mt-1 truncate text-[11px] text-muted-foreground">{item.image}</div>
        </div>
        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", item.state === "running" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : item.state === "restarting" ? "border-amber-500/20 bg-amber-500/10 text-amber-300" : "border-border/70 bg-background/94 text-muted-foreground")}>
          {item.state}
        </span>
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground">{item.status}</div>
      {item.ports ? (
        <div className="mt-2 truncate font-mono text-[11px] text-muted-foreground">{item.ports}</div>
      ) : null}
    </button>
  );
}

function DockerWindow({
  server,
  active,
  dockerEnabled,
}: {
  server: FrontendServer;
  active: boolean;
  dockerEnabled: boolean;
}) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const [selectedContainerName, setSelectedContainerName] = useState<string | null>(null);
  const [lines, setLines] = useState(80);
  const [confirmState, setConfirmState] = useState<{
    container: LinuxUiDockerContainer;
    action: LinuxUiDockerAction;
  } | null>(null);
  const [lastAction, setLastAction] = useState<LinuxUiDockerActionResult | null>(null);

  const dockerQuery = useQuery({
    queryKey: ["linux-ui", server.id, "docker"],
    queryFn: () => fetchLinuxUiDocker(server.id),
    enabled: active && dockerEnabled,
    staleTime: 8_000,
  });

  const dockerPayload = dockerQuery.data?.docker;
  const containers = dockerPayload?.containers || [];
  const filteredContainers = useMemo(() => {
    if (!deferredSearch) return containers;
    return containers.filter((item) => `${item.name} ${item.image} ${item.state} ${item.status} ${item.ports}`.toLowerCase().includes(deferredSearch));
  }, [containers, deferredSearch]);

  useEffect(() => {
    if (!containers.length) {
      if (selectedContainerName != null) setSelectedContainerName(null);
      return;
    }
    if (!filteredContainers.some((item) => item.name === selectedContainerName)) {
      setSelectedContainerName((filteredContainers[0] || containers[0]).name);
    }
  }, [containers, filteredContainers, selectedContainerName]);

  const selectedContainer = useMemo(() => {
    return containers.find((item) => item.name === selectedContainerName) || filteredContainers[0] || containers[0] || null;
  }, [containers, filteredContainers, selectedContainerName]);

  const dockerLogsQuery = useQuery({
    queryKey: ["linux-ui", server.id, "docker-logs", selectedContainer?.name || "", lines],
    queryFn: () => fetchLinuxUiDockerLogs(server.id, selectedContainer?.name || "", lines),
    enabled: active && dockerEnabled && Boolean(selectedContainer?.name),
    staleTime: 5_000,
  });

  const dockerActionMutation = useMutation({
    mutationFn: ({ container, action }: { container: string; action: LinuxUiDockerAction }) =>
      runLinuxUiDockerAction(server.id, { container, action }),
    onSuccess: async (response) => {
      setLastAction(response.docker_action);
      await queryClient.invalidateQueries({ queryKey: ["linux-ui", server.id, "docker"] });
      if (selectedContainer?.name) {
        await queryClient.invalidateQueries({ queryKey: ["linux-ui", server.id, "docker-logs", selectedContainer.name] });
      }
    },
  });

  const confirmDescription = useMemo(() => {
    if (!confirmState) return "";
    const base = `${dockerActionMeta(confirmState.action).label} container ${confirmState.container.name}?`;
    if (confirmState.action === "stop") {
      return `${base} This will stop the selected container and any service behind it may become unavailable.`;
    }
    return `${base} The workspace will refresh container state after the action completes.`;
  }, [confirmState]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">docker center</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Inspect containers, read recent logs, and run start/stop/restart actions without leaving the workspace shell.
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter containers..."
              className="h-9 min-w-[16rem] bg-background/95 text-sm"
            />
            <Input
              type="number"
              min={20}
              max={200}
              value={String(lines)}
              onChange={(event) => setLines(Math.max(20, Math.min(200, Number(event.target.value) || 80)))}
              className="h-9 w-28 bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void dockerQuery.refetch()} disabled={!dockerEnabled}>
              <RefreshCw className={cn("h-3.5 w-3.5", dockerQuery.isFetching && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
        {!dockerEnabled ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            Docker is not available on this host.
          </div>
        ) : null}
        {dockerPayload?.error ? (
          <div className="mt-3 rounded-2xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {dockerPayload.error}
          </div>
        ) : null}
        <div className="mt-4 grid gap-2 md:grid-cols-5">
          <SummaryCard label="Total" value={dockerPayload?.summary.total || 0} hint="Known containers" />
          <SummaryCard label="Running" value={dockerPayload?.summary.running || 0} hint="Healthy runtime containers" />
          <SummaryCard label="Exited" value={dockerPayload?.summary.exited || 0} hint="Stopped containers" alert={(dockerPayload?.summary.exited || 0) > 0} />
          <SummaryCard label="Restarting" value={dockerPayload?.summary.restarting || 0} hint="Needs attention" alert={(dockerPayload?.summary.restarting || 0) > 0} />
          <SummaryCard label="Paused" value={dockerPayload?.summary.paused || 0} hint="Paused containers" />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-sm font-medium text-foreground">Containers</div>
              <div className="mt-1 text-xs text-muted-foreground">{filteredContainers.length} visible</div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {dockerQuery.error instanceof Error ? (
                  <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                    {dockerQuery.error.message}
                  </div>
                ) : null}
                {dockerQuery.isLoading ? (
                  <div className="rounded-2xl border border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    Loading docker data...
                  </div>
                ) : null}
                {!dockerQuery.isLoading && filteredContainers.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    No containers match the current filter.
                  </div>
                ) : null}
                {filteredContainers.map((item) => (
                  <DockerContainerRow
                    key={item.id}
                    item={item}
                    selected={selectedContainer?.name === item.name}
                    onClick={() => setSelectedContainerName(item.name)}
                  />
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="grid min-h-0 gap-4 lg:grid-rows-[auto_minmax(0,1fr)]">
            {selectedContainer ? (
              <>
                <div className="rounded-3xl border border-border/70 bg-background/88 p-4">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-mono text-sm text-foreground">{selectedContainer.name}</h3>
                        <span className={cn("rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", selectedContainer.state === "running" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : selectedContainer.state === "restarting" ? "border-amber-500/20 bg-amber-500/10 text-amber-300" : "border-border/70 bg-background/94 text-muted-foreground")}>
                          {selectedContainer.state}
                        </span>
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          {selectedContainer.id.slice(0, 12)}
                        </span>
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">{selectedContainer.image}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{selectedContainer.status}</div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-4">
                        <SummaryCard label="CPU" value={selectedContainer.cpu_percent || "n/a"} hint="docker stats CPU%" />
                        <SummaryCard label="Memory" value={selectedContainer.memory_percent || "n/a"} hint={selectedContainer.memory_usage || "No live stats"} />
                        <SummaryCard label="Network" value={selectedContainer.network_io || "n/a"} hint="Net IO" />
                        <SummaryCard label="Block" value={selectedContainer.block_io || "n/a"} hint="Block IO" />
                      </div>
                      {selectedContainer.ports ? (
                        <div className="mt-3 rounded-2xl border border-border/70 bg-background/92 px-3 py-2 font-mono text-xs text-muted-foreground">
                          {selectedContainer.ports}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-2 xl:max-w-[16rem] xl:justify-end">
                      {(["start", "restart", "stop"] as LinuxUiDockerAction[]).map((action) => (
                        <Button
                          key={action}
                          type="button"
                          size="sm"
                          variant={action === "stop" ? "destructive" : "outline"}
                          className="h-9 text-xs"
                          disabled={dockerActionMutation.isPending}
                          onClick={() => setConfirmState({ container: selectedContainer, action })}
                        >
                          {dockerActionMeta(action).label}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid min-h-0 gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
                  <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
                    <div className="border-b border-border/60 px-4 py-3">
                      <div className="text-sm font-medium text-foreground">Recent logs</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {lines} lines from <span className="font-mono">{selectedContainer.name}</span>
                      </div>
                    </div>
                    <ScrollArea className="h-full">
                      <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                        {dockerLogsQuery.error instanceof Error
                          ? dockerLogsQuery.error.message
                          : dockerLogsQuery.isLoading
                          ? "Loading docker logs..."
                          : dockerLogsQuery.data?.docker_logs.content || "No log lines available."}
                      </pre>
                    </ScrollArea>
                  </div>

                  <div className="flex min-h-0 flex-col gap-4">
                    <div className="rounded-3xl border border-border/70 bg-card/88 p-4">
                      <div className="text-sm font-medium text-foreground">Action state</div>
                      <div className="mt-2 text-xs text-muted-foreground">
                        Start, stop, and restart use typed Docker actions and refresh the container list afterwards.
                      </div>
                      <div className="mt-4 rounded-2xl border border-border/70 bg-background/94 p-3">
                        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Last action</div>
                        <div className="mt-2 text-sm text-foreground">
                          {lastAction ? `${lastAction.action} ${lastAction.container}` : "No docker action has been executed yet."}
                        </div>
                        {lastAction ? (
                          <div className={cn("mt-2 inline-flex rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", lastAction.success ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-destructive/30 bg-destructive/10 text-destructive")}>
                            {lastAction.success ? "success" : "failed"}
                          </div>
                        ) : null}
                      </div>
                      {lastAction?.output ? (
                        <ScrollArea className="mt-3 h-32 rounded-2xl border border-border/70 bg-background/94">
                          <pre className="whitespace-pre-wrap break-words px-3 py-3 font-mono text-[11px] leading-5 text-muted-foreground">
                            {lastAction.output}
                          </pre>
                        </ScrollArea>
                      ) : null}
                      {dockerActionMutation.error instanceof Error ? (
                        <div className="mt-3 rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                          {dockerActionMutation.error.message}
                        </div>
                      ) : null}
                    </div>

                    <div className="rounded-3xl border border-border/70 bg-card/88 p-4 text-xs leading-5 text-muted-foreground">
                      <div className="text-sm font-medium text-foreground">Operational notes</div>
                      <div className="mt-2">Restart is the safest first response when a container is unhealthy but its image and config are still trusted.</div>
                      <div className="mt-2">Stop is intentionally treated as destructive because it can take application traffic offline immediately.</div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
                Select a container from the list to inspect logs and action state.
              </div>
            )}
          </section>
        </div>
      </div>

      <ConfirmActionDialog
        open={Boolean(confirmState)}
        onOpenChange={(open) => {
          if (!open) setConfirmState(null);
        }}
        title={confirmState ? `${dockerActionMeta(confirmState.action).label} ${confirmState.container.name}` : "Confirm docker action"}
        description={confirmDescription}
        confirmLabel={confirmState ? dockerActionMeta(confirmState.action).confirmLabel : "Confirm"}
        destructive={Boolean(confirmState && dockerActionMeta(confirmState.action).destructive)}
        onConfirm={async () => {
          if (!confirmState) return;
          const current = confirmState;
          setConfirmState(null);
          await dockerActionMutation.mutateAsync({ container: current.container.name, action: current.action });
        }}
      />
    </div>
  );
}

function PlaceholderWindow({
  title,
  description,
  bullets,
  capabilityLabel,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  bullets: string[];
  capabilityLabel?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="text-sm font-medium text-foreground">{title}</div>
        <div className="mt-1 text-xs text-muted-foreground">{description}</div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {capabilityLabel ? (
          <div className="mb-4 inline-flex rounded-full border border-border/70 bg-background/93 px-2.5 py-1 text-[11px] text-muted-foreground">
            {capabilityLabel}
          </div>
        ) : null}
        <div className="space-y-2">
          {bullets.map((bullet) => (
            <div key={bullet} className="rounded-2xl border border-border/70 bg-background/90 px-3 py-2 text-sm text-muted-foreground">
              {bullet}
            </div>
          ))}
        </div>
      </div>
      {actionLabel && onAction ? (
        <div className="border-t border-border/60 px-4 py-3">
          <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function LinuxUiPanel({ server, active = true, onClose }: LinuxUiPanelProps) {
  const workspaceCanvasRef = useRef<HTMLDivElement | null>(null);
  const launcherSurfaceRef = useRef<HTMLDivElement | null>(null);
  const zCounterRef = useRef(APP_IDS.length + 6);
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

  const [isDesktopShell, setIsDesktopShell] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth >= DESKTOP_BREAKPOINT : true,
  );
  const [openApps, setOpenApps] = useState<WorkspaceAppId[]>(DEFAULT_OPEN_APPS);
  const [activeApp, setActiveApp] = useState<WorkspaceAppId>(DEFAULT_ACTIVE_APP);
  const [windowStates, setWindowStates] = useState<Record<WorkspaceAppId, WorkspaceWindowState>>(() => buildInitialWindowStates());
  const [dragState, setDragState] = useState<WorkspaceDragState | null>(null);
  const [resizeState, setResizeState] = useState<WorkspaceResizeState | null>(null);
  const [pendingEditorPath, setPendingEditorPath] = useState<string | null>(null);
  const [launcherOpen, setLauncherOpen] = useState(false);
  const [launcherQuery, setLauncherQuery] = useState("");
  const [clockNow, setClockNow] = useState(() => new Date());

  const openAppsRef = useRef(openApps);
  const activeAppRef = useRef(activeApp);
  const windowStatesRef = useRef(windowStates);

  useEffect(() => {
    openAppsRef.current = openApps;
  }, [openApps]);

  useEffect(() => {
    activeAppRef.current = activeApp;
  }, [activeApp]);

  useEffect(() => {
    windowStatesRef.current = windowStates;
  }, [windowStates]);

  const syncDesktopWindowBounds = useCallback(() => {
    if (!workspaceCanvasRef.current) return;
    const bounds = getWorkspaceBounds(workspaceCanvasRef.current);
    setWindowStates((current) => {
      const next = Object.fromEntries(
        Object.entries(current).map(([appId, state]) => [appId, normalizeWindowState(state, bounds)]),
      ) as Record<WorkspaceAppId, WorkspaceWindowState>;
      windowStatesRef.current = next;
      return next;
    });
  }, []);

  useEffect(() => {
    const handleResize = () => {
      setIsDesktopShell(window.innerWidth >= DESKTOP_BREAKPOINT);
      syncDesktopWindowBounds();
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [syncDesktopWindowBounds]);

  useEffect(() => {
    zCounterRef.current = APP_IDS.length + 6;
    const initialStates = buildInitialWindowStates();
    openAppsRef.current = DEFAULT_OPEN_APPS;
    activeAppRef.current = DEFAULT_ACTIVE_APP;
    windowStatesRef.current = initialStates;
    setOpenApps(DEFAULT_OPEN_APPS);
    setActiveApp(DEFAULT_ACTIVE_APP);
    setWindowStates(initialStates);
    setDragState(null);
    setResizeState(null);
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

  useEffect(() => {
    if (!isDesktopShell) return;
    const frameId = window.requestAnimationFrame(() => {
      syncDesktopWindowBounds();
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [isDesktopShell, server.id, syncDesktopWindowBounds]);

  useEffect(() => {
    if (!dragState) return;

    const handlePointerMove = (event: PointerEvent) => {
      const deltaX = event.clientX - dragState.startX;
      const deltaY = event.clientY - dragState.startY;
      setWindowStates((current) => {
        const currentState = current[dragState.appId] ?? getDefaultWindowGeometry(dragState.appId, zCounterRef.current);
        const next = {
          ...current,
          [dragState.appId]: clampWindowState(
            {
              ...currentState,
              x: dragState.originX + deltaX,
              y: dragState.originY + deltaY,
            },
            dragState.bounds,
          ),
        };
        windowStatesRef.current = next;
        return next;
      });
    };

    const handlePointerUp = () => {
      setDragState(null);
    };

    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    return () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [dragState]);

  useEffect(() => {
    if (!resizeState) return;

    const handlePointerMove = (event: PointerEvent) => {
      const deltaX = event.clientX - resizeState.startX;
      const deltaY = event.clientY - resizeState.startY;
      setWindowStates((current) => {
        const currentState = current[resizeState.appId] ?? getDefaultWindowGeometry(resizeState.appId, zCounterRef.current);
        const next = {
          ...current,
          [resizeState.appId]: clampWindowState(
            {
              ...currentState,
              width: resizeState.originWidth + deltaX,
              height: resizeState.originHeight + deltaY,
              maximized: false,
            },
            resizeState.bounds,
          ),
        };
        windowStatesRef.current = next;
        return next;
      });
    };

    const handlePointerUp = () => {
      setResizeState(null);
    };

    document.body.style.userSelect = "none";
    document.body.style.cursor = "se-resize";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    return () => {
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [resizeState]);

  const refresh = useCallback(() => {
    void capabilitiesQuery.refetch();
    void overviewQuery.refetch();
  }, [capabilitiesQuery, overviewQuery]);

  const capabilities = capabilitiesQuery.data?.capabilities;
  const availableApps = capabilities?.available_apps;

  const apps = useMemo<WorkspaceAppDefinition[]>(() => [
    {
      id: "files",
      title: "Files",
      subtitle: "Folders, uploads, delete, rename",
      status: "live",
      icon: <FolderOpen className="h-5 w-5" />,
      accentClass: "from-primary/20 to-secondary",
    },
    {
      id: "overview",
      title: "Overview",
      subtitle: "Host summary and system markers",
      status: "live",
      icon: <Monitor className="h-5 w-5" />,
      accentClass: "from-primary/15 to-background",
    },
    {
      id: "services",
      title: "Services",
      subtitle: availableApps?.services ? "systemctl control center is live" : "Unavailable on this host",
      status: availableApps?.services ? "live" : "unavailable",
      icon: <Settings2 className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "processes",
      title: "Processes",
      subtitle: "Task manager for CPU and memory",
      status: "live",
      icon: <Activity className="h-5 w-5" />,
      accentClass: "from-primary/12 to-secondary",
    },
    {
      id: "logs",
      title: "Logs",
      subtitle: availableApps?.logs ? "journalctl and file presets are live" : "File presets and service fallbacks are live",
      status: "live",
      icon: <FileText className="h-5 w-5" />,
      accentClass: "from-primary/18 to-secondary",
    },
    {
      id: "disk",
      title: "Disk",
      subtitle: availableApps?.disk ? "Usage and cleanup signals are live" : "Disk inspection unavailable",
      status: availableApps?.disk ? "live" : "unavailable",
      icon: <HardDrive className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "network",
      title: "Network",
      subtitle: availableApps?.network ? "Interfaces and ports are live" : "Network tooling not detected",
      status: availableApps?.network ? "live" : "unavailable",
      icon: <Network className="h-5 w-5" />,
      accentClass: "from-primary/16 to-background",
    },
    {
      id: "docker",
      title: "Docker",
      subtitle: availableApps?.docker ? "Containers and logs are live" : "Docker not detected",
      status: availableApps?.docker ? "live" : "unavailable",
      icon: <Server className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "packages",
      title: "Packages",
      subtitle: capabilities?.package_manager ? `${capabilities.package_manager} inspector is live` : "Package manager not detected",
      status: capabilities?.package_manager ? "live" : "unavailable",
      icon: <Package className="h-5 w-5" />,
      accentClass: "from-primary/15 to-secondary",
    },
    {
      id: "text-editor",
      title: "Text Editor",
      subtitle: availableApps?.text_editor ? "Edit config files directly" : "Text editing unavailable on this host",
      status: availableApps?.text_editor ? "live" : "unavailable",
      icon: <FileCode2 className="h-5 w-5" />,
      accentClass: "from-primary/18 to-background",
      hidden: true,
    },
    {
      id: "quick-run",
      title: "Quick Run",
      subtitle: availableApps?.quick_run ? "Execute commands with output" : "Shell execution unavailable",
      status: availableApps?.quick_run ? "live" : "unavailable",
      icon: <Terminal className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "settings",
      title: "Settings",
      subtitle: availableApps?.settings ? "System info, users, cron, security" : "Settings snapshot unavailable",
      status: availableApps?.settings ? "live" : "unavailable",
      icon: <Settings className="h-5 w-5" />,
      accentClass: "from-muted to-background",
    },
  ], [
    availableApps?.disk,
    availableApps?.docker,
    availableApps?.logs,
    availableApps?.network,
    availableApps?.quick_run,
    availableApps?.services,
    availableApps?.settings,
    availableApps?.text_editor,
    capabilities?.package_manager,
  ]);

  const appMap = useMemo(
    () => Object.fromEntries(apps.map((app) => [app.id, app])) as Record<WorkspaceAppId, WorkspaceAppDefinition>,
    [apps],
  );

  const focusApp = useCallback((appId: WorkspaceAppId) => {
    const nextZ = ++zCounterRef.current;
    activeAppRef.current = appId;
    setActiveApp(appId);
    setWindowStates((current) => {
      const fallbackState = current[appId] ?? getDefaultWindowGeometry(appId, nextZ);
      const baseState = isDesktopShell
        ? clampWindowState(
            {
              ...fallbackState,
              zIndex: fallbackState.zIndex || nextZ,
            },
            getWorkspaceBounds(workspaceCanvasRef.current),
          )
        : fallbackState;
      const next = {
        ...current,
        [appId]: {
          ...baseState,
          minimized: false,
          zIndex: nextZ,
        },
      };
      windowStatesRef.current = next;
      return next;
    });
    setDragState(null);
    setResizeState(null);
  }, [isDesktopShell]);

  const resetWindowPosition = useCallback((appId: WorkspaceAppId) => {
    const bounds = getWorkspaceBounds(workspaceCanvasRef.current);
    const currentState = windowStatesRef.current[appId] ?? getDefaultWindowGeometry(appId, zCounterRef.current);
    const nextState = clampWindowState(
      {
        ...getDefaultWindowGeometry(appId, currentState.zIndex),
        minimized: currentState.minimized,
        maximized: false,
        restoreX: undefined,
        restoreY: undefined,
        restoreWidth: undefined,
        restoreHeight: undefined,
        zIndex: currentState.zIndex,
      },
      bounds,
    );
    const next = {
      ...windowStatesRef.current,
      [appId]: nextState,
    };
    windowStatesRef.current = next;
    setWindowStates(next);
  }, []);

  const rearrangeOpenWindows = useCallback(() => {
    const bounds = getWorkspaceBounds(workspaceCanvasRef.current);
    const next = { ...windowStatesRef.current };
    openAppsRef.current.forEach((appId, index) => {
      const currentState = next[appId] ?? getDefaultWindowGeometry(appId, index + 1);
      next[appId] = clampWindowState(
        {
          ...getDefaultWindowGeometry(appId, currentState.zIndex || index + 1),
          minimized: false,
          maximized: false,
          restoreX: undefined,
          restoreY: undefined,
          restoreWidth: undefined,
          restoreHeight: undefined,
          zIndex: currentState.zIndex || index + 1,
        },
        bounds,
      );
    });
    windowStatesRef.current = next;
    setWindowStates(next);
  }, []);

  const minimizeApp = useCallback((appId: WorkspaceAppId) => {
    const currentState = windowStatesRef.current[appId] ?? getDefaultWindowGeometry(appId, zCounterRef.current);
    const nextWindowStates = {
      ...windowStatesRef.current,
      [appId]: {
        ...currentState,
        minimized: true,
      },
    };
    windowStatesRef.current = nextWindowStates;
    setWindowStates(nextWindowStates);
    if (activeAppRef.current === appId) {
      const nextActive = pickTopVisibleApp(openAppsRef.current, nextWindowStates, appId) ?? "overview";
      activeAppRef.current = nextActive;
      setActiveApp(nextActive);
    }
  }, []);

  const minimizeAllWindows = useCallback(() => {
    const nextWindowStates = { ...windowStatesRef.current };
    openAppsRef.current.forEach((appId) => {
      nextWindowStates[appId] = {
        ...(nextWindowStates[appId] ?? getDefaultWindowGeometry(appId, zCounterRef.current)),
        minimized: true,
      };
    });
    windowStatesRef.current = nextWindowStates;
    setWindowStates(nextWindowStates);
    activeAppRef.current = "overview";
    setActiveApp("overview");
  }, []);

  const toggleMaximizeApp = useCallback((appId: WorkspaceAppId) => {
    if (!isDesktopShell) return;
    const bounds = getWorkspaceBounds(workspaceCanvasRef.current);
    const nextZ = ++zCounterRef.current;
    const currentState = windowStatesRef.current[appId] ?? getDefaultWindowGeometry(appId, nextZ);

    const restoredState = currentState.maximized
      ? clampWindowState(
          {
            ...currentState,
            x: currentState.restoreX ?? getDefaultWindowGeometry(appId, nextZ).x,
            y: currentState.restoreY ?? getDefaultWindowGeometry(appId, nextZ).y,
            width: currentState.restoreWidth ?? getDefaultWindowGeometry(appId, nextZ).width,
            height: currentState.restoreHeight ?? getDefaultWindowGeometry(appId, nextZ).height,
            minimized: false,
            maximized: false,
            restoreX: undefined,
            restoreY: undefined,
            restoreWidth: undefined,
            restoreHeight: undefined,
            zIndex: nextZ,
          },
          bounds,
        )
      : maximizeWindowState(
          {
            ...currentState,
            minimized: false,
            zIndex: nextZ,
          },
          bounds,
        );

    const nextWindowStates = {
      ...windowStatesRef.current,
      [appId]: restoredState,
    };
    windowStatesRef.current = nextWindowStates;
    setWindowStates(nextWindowStates);
    activeAppRef.current = appId;
    setActiveApp(appId);
    setDragState(null);
    setResizeState(null);
  }, [isDesktopShell]);

  const launchApp = useCallback((appId: WorkspaceAppId) => {
    const app = appMap[appId];
    if (!app || app.status === "unavailable") return;
    if (!openAppsRef.current.includes(appId)) {
      const nextOpenApps = [...openAppsRef.current, appId];
      openAppsRef.current = nextOpenApps;
      setOpenApps(nextOpenApps);
    }
    setLauncherOpen(false);
    focusApp(appId);
  }, [appMap, focusApp]);

  const openFileInEditor = useCallback((path: string) => {
    setPendingEditorPath(path);
    launchApp("text-editor");
  }, [launchApp]);

  const closeApp = useCallback((appId: WorkspaceAppId) => {
    const nextOpenApps = openAppsRef.current.filter((item) => item !== appId);
    openAppsRef.current = nextOpenApps;
    setOpenApps(nextOpenApps);
    if (activeAppRef.current === appId) {
      const nextActive = pickTopVisibleApp(nextOpenApps, windowStatesRef.current, appId) ?? "overview";
      activeAppRef.current = nextActive;
      setActiveApp(nextActive);
    }
  }, []);

  const toggleTaskbarApp = useCallback((appId: WorkspaceAppId) => {
    const currentState = windowStatesRef.current[appId];
    if (currentState?.minimized) {
      focusApp(appId);
      return;
    }
    if (activeAppRef.current === appId) {
      minimizeApp(appId);
      return;
    }
    focusApp(appId);
  }, [focusApp, minimizeApp]);

  const handleWindowHeaderPointerDown = useCallback((appId: WorkspaceAppId, event: ReactPointerEvent<HTMLElement>) => {
    if (!isDesktopShell || event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest("[data-no-window-drag='true']")) return;

    focusApp(appId);
    const currentState = windowStatesRef.current[appId] ?? getDefaultWindowGeometry(appId, zCounterRef.current);
    if (currentState.maximized) return;
    setResizeState(null);
    setDragState({
      appId,
      startX: event.clientX,
      startY: event.clientY,
      originX: currentState.x,
      originY: currentState.y,
      bounds: getWorkspaceBounds(workspaceCanvasRef.current),
    });
    event.preventDefault();
  }, [focusApp, isDesktopShell]);

  const handleWindowResizePointerDown = useCallback((appId: WorkspaceAppId, event: ReactPointerEvent<HTMLElement>) => {
    if (!isDesktopShell || event.button !== 0) return;
    const currentState = windowStatesRef.current[appId] ?? getDefaultWindowGeometry(appId, zCounterRef.current);
    if (currentState.maximized) return;

    focusApp(appId);
    setDragState(null);
    setResizeState({
      appId,
      startX: event.clientX,
      startY: event.clientY,
      originWidth: currentState.width,
      originHeight: currentState.height,
      bounds: getWorkspaceBounds(workspaceCanvasRef.current),
    });
    event.preventDefault();
    event.stopPropagation();
  }, [focusApp, isDesktopShell]);

  const desktopApps = apps.filter((app) => !app.hidden);
  const sortedWindowApps = [...openApps].sort(
    (left, right) => (windowStates[left]?.zIndex || 0) - (windowStates[right]?.zIndex || 0),
  );
  const visibleWindowApps = sortedWindowApps.filter((appId) => !windowStates[appId]?.minimized);
  const taskbarApps = openApps
    .map((appId) => ({ app: appMap[appId], minimized: Boolean(windowStates[appId]?.minimized) }))
    .filter((entry) => Boolean(entry.app));
  const overview = overviewQuery.data?.overview;
  const timeLabel = useMemo(
    () => new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(clockNow),
    [clockNow],
  );
  const dateLabel = useMemo(
    () => new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" }).format(clockNow),
    [clockNow],
  );

  const closeAllWindows = useCallback(() => {
    openAppsRef.current = [];
    setOpenApps([]);
    activeAppRef.current = "overview";
    setActiveApp("overview");
    setDragState(null);
    setResizeState(null);
    setLauncherOpen(false);
  }, []);

  const getWindowStyle = useCallback(
    (appId: WorkspaceAppId) => {
      if (!isDesktopShell) return undefined;
      const state = windowStates[appId] ?? getDefaultWindowGeometry(appId, zCounterRef.current);
      return {
        left: state.x,
        top: state.y,
        width: state.width,
        height: state.height,
        zIndex: state.zIndex,
      };
    },
    [isDesktopShell, windowStates],
  );

  const errorMessage =
    (capabilitiesQuery.error instanceof Error && capabilitiesQuery.error.message) ||
    (overviewQuery.error instanceof Error && overviewQuery.error.message) ||
    "";

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
        <div className="pointer-events-none absolute inset-0 opacity-[0.14]" style={DESKTOP_GRID_STYLE} />

        <ContextMenu>
          <ContextMenuTrigger asChild>
            <div ref={workspaceCanvasRef} className="relative z-10 h-full min-h-0 overflow-y-auto p-3 lg:overflow-hidden lg:p-4">
              {server.server_type !== "ssh" ? (
                <div className="rounded-[1.25rem] border border-border bg-card p-6 text-sm text-muted-foreground">
                  Linux Workspace is available only for SSH servers.
                </div>
              ) : null}

              {server.server_type === "ssh" && errorMessage ? (
                <div className="mb-3 rounded-[1.25rem] border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  {errorMessage}
                </div>
              ) : null}

              {server.server_type === "ssh" && (capabilitiesQuery.isLoading || overviewQuery.isLoading) ? (
                <div className="flex h-full min-h-[22rem] items-center justify-center">
                  <div className="rounded-[1.5rem] border border-border bg-card px-8 py-10 text-center shadow-lg">
                    <RefreshCw className="mx-auto mb-3 h-5 w-5 animate-spin text-primary" />
                    <div className="text-sm font-medium text-foreground">Loading workspace...</div>
                    <div className="mt-1 text-xs text-muted-foreground">Collecting host capabilities</div>
                  </div>
                </div>
              ) : null}

              {server.server_type === "ssh" && !capabilitiesQuery.isLoading && !overviewQuery.isLoading ? (
                <div className="relative min-h-full gap-3 lg:h-full">
                  <div className="pointer-events-none absolute right-4 top-4 z-0 hidden w-[22rem] gap-3 xl:grid">
                    <div className="rounded-[1.35rem] border border-border bg-card/95 p-4 shadow-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Workspace Session</div>
                          <div className="mt-2 truncate text-lg font-semibold text-foreground">{overview?.hostname || server.name}</div>
                          <div className="mt-1 truncate font-mono text-xs text-muted-foreground">{server.username}@{server.host}</div>
                        </div>
                        <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary">
                          <Shield className="h-4 w-4" />
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2 text-[11px]">
                        <span className="rounded-full border border-border bg-background px-2.5 py-1 text-foreground">
                          {capabilities?.os_name || overview?.os_name || "Linux host"}
                        </span>
                        {capabilities?.package_manager ? (
                          <span className="rounded-full border border-border bg-background px-2.5 py-1 text-foreground">
                            {capabilities.package_manager}
                          </span>
                        ) : null}
                        <span className="rounded-full border border-border bg-background px-2.5 py-1 text-foreground">
                          {openApps.length} windows
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <DesktopStatCard
                        icon={<Activity />}
                        label="Memory"
                        value={overview?.memory.percent != null ? `${overview.memory.percent.toFixed(0)}%` : "N/A"}
                        hint={
                          overview?.memory.used_mb != null && overview.memory.total_mb != null
                            ? `${overview.memory.used_mb} / ${overview.memory.total_mb} MB`
                            : "Usage unavailable"
                        }
                        progress={overview?.memory.percent ?? null}
                      />
                      <DesktopStatCard
                        icon={<HardDrive />}
                        label="Disk"
                        value={overview?.disk.percent != null ? `${overview.disk.percent.toFixed(0)}%` : "N/A"}
                        hint={
                          overview?.disk.used_gb != null && overview.disk.total_gb != null
                            ? `${overview.disk.used_gb} / ${overview.disk.total_gb} GB`
                            : "Root filesystem"
                        }
                        progress={overview?.disk.percent ?? null}
                      />
                    </div>
                  </div>

                  <div className="absolute left-4 top-4 z-0 max-h-[calc(100%-1rem)] overflow-hidden pointer-events-none">
                    <div className="grid grid-flow-col auto-cols-[5.75rem] grid-rows-6 gap-x-4 gap-y-3 pointer-events-auto">
                      {desktopApps.map((app) => (
                        <DesktopIcon
                          key={app.id}
                          title={app.title}
                          icon={app.icon}
                          status={app.status}
                          accentClass={app.accentClass}
                          onOpen={() => launchApp(app.id)}
                        />
                      ))}
                    </div>
                  </div>

                  {visibleWindowApps.map((appId) => {
                    const app = appMap[appId];
                    if (!app) return null;

                    return (
                      <WorkspaceWindow
                        key={appId}
                        appId={appId}
                        title={app.title}
                        subtitle={app.subtitle}
                        icon={app.icon}
                        status={app.status}
                        active={activeApp === appId}
                        minimized={Boolean(windowStates[appId]?.minimized)}
                        maximized={Boolean(windowStates[appId]?.maximized)}
                        desktopMode={isDesktopShell}
                        dragging={dragState?.appId === appId}
                        resizing={resizeState?.appId === appId}
                        style={getWindowStyle(appId)}
                        className={cn(mobileWindowClass(appId), isDesktopShell && "absolute")}
                        onFocus={() => focusApp(appId)}
                        onMinimize={() => minimizeApp(appId)}
                        onToggleMaximize={() => toggleMaximizeApp(appId)}
                        onResetPosition={() => resetWindowPosition(appId)}
                        onClose={() => closeApp(appId)}
                        onHeaderPointerDown={(event) => handleWindowHeaderPointerDown(appId, event)}
                        onHeaderDoubleClick={() => toggleMaximizeApp(appId)}
                        onResizePointerDown={(event) => handleWindowResizePointerDown(appId, event)}
                      >
                        {appId === "files" ? (
                          <SftpPanel server={server} active={active && activeApp === "files"} onOpenInEditor={openFileInEditor} />
                        ) : null}
                        {appId === "overview" ? (
                          <OverviewWindow
                            overview={overviewQuery.data?.overview}
                            capabilities={capabilities}
                            onOpenFiles={() => launchApp("files")}
                            onOpenServices={() => launchApp("services")}
                            onOpenDisk={() => launchApp("disk")}
                            onOpenLogs={() => launchApp("logs")}
                          />
                        ) : null}
                        {appId === "services" ? (
                          <ServicesWindow server={server} active={active} servicesEnabled={Boolean(availableApps?.services)} logsEnabled={Boolean(availableApps?.logs)} onOpenLogs={() => launchApp("logs")} />
                        ) : null}
                        {appId === "processes" ? <ProcessesWindow server={server} active={active} /> : null}
                        {appId === "logs" ? <LogsWindow server={server} active={active} logsEnabled={Boolean(availableApps?.logs)} /> : null}
                        {appId === "disk" ? <DiskWindow server={server} active={active} diskEnabled={Boolean(availableApps?.disk)} onOpenInEditor={openFileInEditor} /> : null}
                        {appId === "network" ? <NetworkWindow server={server} active={active} networkEnabled={Boolean(availableApps?.network)} /> : null}
                        {appId === "docker" ? <DockerWindow server={server} active={active} dockerEnabled={Boolean(availableApps?.docker)} /> : null}
                        {appId === "packages" ? <PackagesWindow server={server} active={active} packageManager={capabilities?.package_manager || ""} /> : null}
                        {appId === "text-editor" ? <TextEditorWindow server={server} active={active && activeApp === "text-editor"} initialPath={pendingEditorPath || undefined} onPathConsumed={() => setPendingEditorPath(null)} /> : null}
                        {appId === "quick-run" ? <QuickRunWindow server={server} active={active && activeApp === "quick-run"} /> : null}
                        {appId === "settings" ? <SystemSettingsWindow server={server} active={active && activeApp === "settings"} /> : null}
                      </WorkspaceWindow>
                    );
                  })}
                </div>
              ) : null}
            </div>
          </ContextMenuTrigger>
          <ContextMenuContent className="w-56 rounded-xl border-border bg-popover text-popover-foreground">
            <ContextMenuLabel>Desktop</ContextMenuLabel>
            {desktopApps.map((app) => (
              <ContextMenuItem key={app.id} onSelect={() => launchApp(app.id)} disabled={app.status === "unavailable"}>
                {app.title}
              </ContextMenuItem>
            ))}
            <ContextMenuSeparator />
            <ContextMenuItem onSelect={refresh}>Refresh</ContextMenuItem>
            <ContextMenuItem onSelect={rearrangeOpenWindows} disabled={openApps.length === 0}>Rearrange Windows</ContextMenuItem>
            <ContextMenuItem onSelect={minimizeAllWindows} disabled={openApps.length === 0}>Show Desktop</ContextMenuItem>
            <ContextMenuSeparator />
            <ContextMenuItem onSelect={closeAllWindows} disabled={openApps.length === 0} className="text-destructive focus:text-destructive">
              Close All
            </ContextMenuItem>
          </ContextMenuContent>
        </ContextMenu>
      </div>

      <div ref={launcherSurfaceRef} className="relative z-20 px-3 pb-3 pt-2">
        {launcherOpen ? (
          <LauncherMenu
            apps={apps}
            server={server}
            query={launcherQuery}
            onQueryChange={setLauncherQuery}
            onLaunch={launchApp}
            onRefresh={() => {
              refresh();
              setLauncherOpen(false);
            }}
            onShowDesktop={() => {
              minimizeAllWindows();
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
            openApps={openApps}
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
            aria-label="Open application launcher"
          >
            <LayoutGrid className="h-5 w-5" />
          </button>

          <div className="h-8 w-px bg-border" />

          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
            {taskbarApps.map(({ app, minimized }) => {
              if (!app) return null;
              return (
                <TaskbarButton
                  key={app.id}
                  title={app.title}
                  icon={app.icon}
                  active={activeApp === app.id && !minimized}
                  minimized={minimized}
                  accentClass={app.accentClass}
                  onClick={() => toggleTaskbarApp(app.id)}
                />
              );
            })}
          </div>

          <div className="h-8 w-px bg-border" />

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={refresh}
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-background text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="Refresh workspace"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={minimizeAllWindows}
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-background text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="Show desktop"
            >
              <Monitor className="h-4 w-4" />
            </button>

            <div className="hidden items-center gap-1 rounded-[1rem] border border-border bg-background px-2.5 py-1.5 lg:flex">
              <Wifi className="h-3.5 w-3.5 text-muted-foreground" />
              <Volume2 className="h-3.5 w-3.5 text-muted-foreground" />
              <Shield className="h-3.5 w-3.5 text-muted-foreground" />
            </div>

            <div className="hidden rounded-[1rem] border border-border bg-background px-3 py-1.5 text-right xl:block">
              <div className="truncate font-mono text-[11px] text-muted-foreground">{server.username}@{server.host}</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">{capabilities?.os_name || "Linux workspace"}</div>
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
                aria-label="Exit workspace"
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
