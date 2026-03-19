import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Code2,
  Copy,
  FileCode2,
  FileText,
  FolderOpen,
  HardDrive,
  Minus,
  Monitor,
  Network,
  Package,
  Play,
  RefreshCw,
  RotateCcw,
  Server,
  Settings,
  Settings2,
  Square,
  Terminal,
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
  if (status === "live") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (status === "ready") return "border-primary/30 bg-primary/10 text-primary";
  if (status === "next") return "border-amber-500/30 bg-amber-500/10 text-amber-400";
  return "border-border bg-muted text-muted-foreground";
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
}: {
  title: string;
  icon: ReactNode;
  onOpen: () => void;
  status: WorkspaceAppStatus;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group flex w-20 flex-col items-center gap-1.5 rounded-lg p-2 text-center transition-colors hover:bg-primary/10",
        status === "unavailable" && "opacity-40 pointer-events-none",
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-card/80 text-foreground shadow-sm border border-border/60 group-hover:bg-primary/15 group-hover:text-primary group-hover:border-primary/30 transition-colors">
        {icon}
      </div>
      <span className="text-[11px] leading-tight text-foreground/80 group-hover:text-foreground line-clamp-2">{title}</span>
    </button>
  );
}

function TaskbarButton({
  title,
  icon,
  active,
  minimized,
  onClick,
}: {
  title: string;
  icon: ReactNode;
  active: boolean;
  minimized?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs transition-colors",
        active
          ? "bg-primary/20 text-foreground"
          : minimized
            ? "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
            : "bg-card/60 text-muted-foreground hover:bg-card hover:text-foreground",
      )}
    >
      <span className="flex h-5 w-5 items-center justify-center [&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
      <span className="max-w-24 truncate">{title}</span>
      {active && <span className="ml-auto h-1 w-1 rounded-full bg-primary" />}
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
            "relative flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card shadow-lg",
            desktopMode ? "absolute" : "relative",
            active ? "ring-1 ring-primary/25 shadow-xl" : "",
            dragging || resizing ? "shadow-2xl" : "",
            className,
          )}
          style={style}
        >
          {/* Compact KDE-like title bar */}
          <header
            onPointerDown={onHeaderPointerDown}
            onDoubleClick={desktopMode ? onHeaderDoubleClick : undefined}
            className={cn(
              "flex h-9 items-center justify-between border-b border-border/80 bg-muted/50 px-2.5 select-none",
              desktopMode && !maximized ? "cursor-grab active:cursor-grabbing" : "",
            )}
          >
            <div className="flex min-w-0 items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center text-muted-foreground [&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
              <span className="truncate text-xs font-medium text-foreground">{title}</span>
            </div>
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                data-no-window-drag="true"
                onClick={onMinimize}
                className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label={`Minimize ${title}`}
              >
                <Minus className="h-3 w-3" />
              </button>
              {desktopMode ? (
                <button
                  type="button"
                  data-no-window-drag="true"
                  onClick={onToggleMaximize}
                  className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  aria-label={maximized ? `Restore ${title}` : `Maximize ${title}`}
                >
                  {maximized ? <Copy className="h-3 w-3" /> : <Square className="h-3 w-3" />}
                </button>
              ) : null}
              <button
                type="button"
                data-no-window-drag="true"
                onClick={onClose}
                className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-destructive/15 hover:text-destructive"
                aria-label={`Close ${title}`}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          </header>
          <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
          {desktopMode && !maximized ? (
            <div
              data-no-window-drag="true"
              onPointerDown={onResizePointerDown}
              className="absolute bottom-0 right-0 h-4 w-4 cursor-se-resize"
              aria-hidden="true"
            >
              <div className="absolute bottom-1 right-1 h-2 w-2 border-b-2 border-r-2 border-border/60" />
            </div>
          ) : null}
        </section>
      </ContextMenuTrigger>
      <ContextMenuContent className="w-48 rounded-lg border-border bg-card">
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
}: {
  item: LinuxUiDiskPathStat;
  label: string;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/90 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-foreground">{item.path}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">{label}</div>
        </div>
        <span className="shrink-0 rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.size_mb != null ? `${item.size_mb} MB` : "n/a"}
        </span>
      </div>
    </div>
  );
}

function DiskWindow({
  server,
  active,
  diskEnabled,
}: {
  server: FrontendServer;
  active: boolean;
  diskEnabled: boolean;
}) {
  const [selectedMountPath, setSelectedMountPath] = useState<string | null>(null);

  const diskQuery = useQuery({
    queryKey: ["linux-ui", server.id, "disk"],
    queryFn: () => fetchLinuxUiDisk(server.id),
    enabled: active,
    staleTime: 15_000,
  });

  const diskPayload = diskQuery.data?.disk;
  const mounts = diskPayload?.mounts || [];

  useEffect(() => {
    if (!mounts.length) {
      if (selectedMountPath != null) setSelectedMountPath(null);
      return;
    }
    if (!mounts.some((item) => item.mount === selectedMountPath)) {
      setSelectedMountPath(mounts[0].mount);
    }
  }, [mounts, selectedMountPath]);

  const selectedMount = useMemo(() => {
    return mounts.find((item) => item.mount === selectedMountPath) || mounts[0] || null;
  }, [mounts, selectedMountPath]);

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
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Mounts</div>
              <div className="mt-1 text-xs text-muted-foreground">{mounts.length} filesystems visible</div>
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
                {!diskQuery.isLoading && mounts.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    No mount data is available for this host.
                  </div>
                ) : null}
                {mounts.map((mount) => (
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

          <section className="grid min-h-0 gap-4 lg:grid-rows-[auto_minmax(0,1fr)_13rem]">
            <div className="rounded-3xl border border-border/70 bg-background/88 p-4">
              {selectedMount ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-mono text-sm text-foreground">{selectedMount.mount}</h3>
                    <span className={cn("rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide", diskUsageClass(selectedMount.percent))}>
                      {selectedMount.percent != null ? `${selectedMount.percent.toFixed(1)}% full` : "usage unknown"}
                    </span>
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

            <div className="grid min-h-0 gap-4 lg:grid-cols-2">
              <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
                <div className="border-b border-border/60 px-4 py-3">
                  <div className="text-sm font-medium text-foreground">Largest directories</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Common writable roots only. This avoids expensive full-filesystem scans on every refresh.
                  </div>
                </div>
                <ScrollArea className="h-full max-h-full">
                  <div className="space-y-2 p-3">
                    {diskPayload?.top_directories.length ? diskPayload.top_directories.map((item) => (
                      <DiskPathRow key={item.path} item={item} label="Directory footprint" />
                    )) : (
                      <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                        No directory footprint data available.
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>

              <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
                <div className="border-b border-border/60 px-4 py-3">
                  <div className="text-sm font-medium text-foreground">Largest logs</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Heavy log files are often the fastest cleanup win during incidents.
                  </div>
                </div>
                <ScrollArea className="h-full max-h-full">
                  <div className="space-y-2 p-3">
                    {diskPayload?.large_logs.length ? diskPayload.large_logs.map((item) => (
                      <DiskPathRow key={item.path} item={item} label="Log footprint" />
                    )) : (
                      <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                        No heavy log files were detected.
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>
            </div>

            <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
              <div className="border-b border-border/60 px-4 py-3">
                <div className="text-sm font-medium text-foreground">Cleanup candidates</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Old top-level `/tmp` entries are surfaced here first. Review before deleting anything.
                </div>
              </div>
              <ScrollArea className="h-full">
                <div className="space-y-2 p-3">
                  {diskPayload?.cleanup_candidates.length ? diskPayload.cleanup_candidates.map((path) => (
                    <div key={path} className="rounded-2xl border border-border/70 bg-background/90 px-3 py-3 font-mono text-xs text-foreground">
                      {path}
                    </div>
                  )) : (
                    <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                      No stale `/tmp` entries were found in the current scan.
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

function ListeningSocketRow({ item }: { item: LinuxUiListeningSocket }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/90 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.protocol}
        </span>
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.state || "unknown"}
        </span>
      </div>
      <div className="mt-2 font-mono text-xs text-foreground">{item.local_address || "n/a"}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{item.process || item.peer_address || "Process metadata unavailable"}</div>
    </div>
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

  const networkQuery = useQuery({
    queryKey: ["linux-ui", server.id, "network"],
    queryFn: () => fetchLinuxUiNetwork(server.id),
    enabled: active,
    staleTime: 10_000,
  });

  const networkPayload = networkQuery.data?.network;
  const interfaces = networkPayload?.interfaces || [];
  const filteredInterfaces = useMemo(() => {
    if (!deferredSearch) return interfaces;
    return interfaces.filter((item) => {
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
      return haystack.includes(deferredSearch);
    });
  }, [deferredSearch, interfaces]);

  const filteredListening = useMemo(() => {
    const listening = networkPayload?.listening || [];
    if (!deferredSearch) return listening;
    return listening.filter((item) =>
      `${item.protocol} ${item.state} ${item.local_address} ${item.peer_address} ${item.process}`
        .toLowerCase()
        .includes(deferredSearch),
    );
  }, [deferredSearch, networkPayload?.listening]);

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

          <section className="grid min-h-0 gap-4 lg:grid-rows-[auto_minmax(0,1fr)_14rem]">
            <div className="rounded-3xl border border-border/70 bg-background/88 p-4">
              {selectedInterface ? (
                <>
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
              ) : (
                <div className="text-sm text-muted-foreground">Select an interface to inspect addresses and flags.</div>
              )}
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
                  {filteredListening.length > 0 ? filteredListening.map((item, index) => (
                    <ListeningSocketRow key={`${item.protocol}-${item.local_address}-${index}`} item={item} />
                  )) : (
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
                <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                  {filteredRoutes.length > 0 ? filteredRoutes.join("\n") : "No route entries match the current filter."}
                </pre>
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
    <div className="rounded-2xl border border-border/70 bg-background/90 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-foreground">{item.name}</div>
          <div className="mt-1 break-words text-[11px] text-muted-foreground">{item.version}</div>
        </div>
      </div>
    </div>
  );
}

function PackagesWindow({
  server,
  active,
  packageManager,
}: {
  server: FrontendServer;
  active: boolean;
  packageManager: string;
}) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

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

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">package inspector</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Read installed versions and update previews for the package manager available on this host.
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter packages and updates..."
              className="h-9 min-w-[16rem] bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void packagesQuery.refetch()} disabled={!packageManager}>
              <RefreshCw className={cn("h-3.5 w-3.5", packagesQuery.isFetching && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
        {!packageManager ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            No supported package manager was detected on this host.
          </div>
        ) : null}
        <div className="mt-4 grid gap-2 md:grid-cols-4">
          <SummaryCard label="Manager" value={(packagesPayload?.package_manager || packageManager || "N/A").toUpperCase()} hint="Detected package toolchain" />
          <SummaryCard label="Installed" value={packagesPayload?.summary.installed_common || 0} hint="Common packages found" />
          <SummaryCard label="Updates" value={packagesPayload?.summary.update_candidates || 0} hint="Previewed upgrade lines" alert={(packagesPayload?.summary.update_candidates || 0) > 0} />
          <SummaryCard label="Scope" value="Read only" hint="Guided actions can come later" />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-sm font-medium text-foreground">Installed packages</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Common package set for {packagesPayload?.package_manager || packageManager || "this host"}.
              </div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {packagesQuery.error instanceof Error ? (
                  <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                    {packagesQuery.error.message}
                  </div>
                ) : null}
                {packagesQuery.isLoading ? (
                  <div className="rounded-2xl border border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    Loading package data...
                  </div>
                ) : null}
                {!packagesQuery.isLoading && installedPackages.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    No installed packages match the current filter.
                  </div>
                ) : null}
                {installedPackages.map((item) => (
                  <PackageRow key={`${item.name}-${item.version}`} item={item} />
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="grid min-h-0 gap-4 lg:grid-rows-[minmax(0,1fr)_12rem]">
            <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
              <div className="border-b border-border/60 px-4 py-3">
                <div className="text-sm font-medium text-foreground">Update preview</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Short preview from the current package manager. This is informational and does not change the host.
                </div>
              </div>
              <ScrollArea className="h-full">
                <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                  {updateLines.length > 0
                    ? updateLines.join("\n")
                    : packagesQuery.isLoading
                    ? "Loading package updates..."
                    : "No update preview lines are available."}
                </pre>
              </ScrollArea>
            </div>

            <div className="rounded-3xl border border-border/70 bg-card/88 p-4 text-xs leading-5 text-muted-foreground">
              <div className="text-sm font-medium text-foreground">Operational notes</div>
              <div className="mt-2">This window is intentionally read-only for now. It gives you version visibility before guided package actions are introduced.</div>
              <div className="mt-2">Different distros expose updates differently, so the preview is best-effort and capability-aware.</div>
            </div>
          </section>
        </div>
      </div>
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
  const [openApps, setOpenApps] = useState<WorkspaceAppId[]>(["files", "overview"]);
  const [activeApp, setActiveApp] = useState<WorkspaceAppId>("files");
  const [windowStates, setWindowStates] = useState<Record<WorkspaceAppId, WorkspaceWindowState>>(() => buildInitialWindowStates());
  const [dragState, setDragState] = useState<WorkspaceDragState | null>(null);
  const [resizeState, setResizeState] = useState<WorkspaceResizeState | null>(null);

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
    windowStatesRef.current = initialStates;
    setOpenApps(["files", "overview"]);
    setActiveApp("files");
    setWindowStates(initialStates);
    setDragState(null);
    setResizeState(null);
  }, [server.id]);

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
    },
    {
      id: "overview",
      title: "Overview",
      subtitle: "Host summary and system markers",
      status: "live",
      icon: <Monitor className="h-5 w-5" />,
    },
    {
      id: "services",
      title: "Services",
      subtitle: availableApps?.services ? "systemctl control center is live" : "Unavailable on this host",
      status: availableApps?.services ? "live" : "unavailable",
      icon: <Settings2 className="h-5 w-5" />,
    },
    {
      id: "processes",
      title: "Processes",
      subtitle: "Task manager for CPU and memory",
      status: "live",
      icon: <Activity className="h-5 w-5" />,
    },
    {
      id: "logs",
      title: "Logs",
      subtitle: availableApps?.logs ? "journalctl and file presets are live" : "File presets and service fallbacks are live",
      status: "live",
      icon: <FileText className="h-5 w-5" />,
    },
    {
      id: "disk",
      title: "Disk",
      subtitle: availableApps?.disk ? "Usage and cleanup signals are live" : "Disk inspection unavailable",
      status: availableApps?.disk ? "live" : "unavailable",
      icon: <HardDrive className="h-5 w-5" />,
    },
    {
      id: "network",
      title: "Network",
      subtitle: availableApps?.network ? "Interfaces and ports are live" : "Network tooling not detected",
      status: availableApps?.network ? "live" : "unavailable",
      icon: <Network className="h-5 w-5" />,
    },
    {
      id: "docker",
      title: "Docker",
      subtitle: availableApps?.docker ? "Containers and logs are live" : "Docker not detected",
      status: availableApps?.docker ? "live" : "unavailable",
      icon: <Server className="h-5 w-5" />,
    },
    {
      id: "packages",
      title: "Packages",
      subtitle: capabilities?.package_manager ? `${capabilities.package_manager} inspector is live` : "Package manager not detected",
      status: capabilities?.package_manager ? "live" : "unavailable",
      icon: <Package className="h-5 w-5" />,
    },
    {
      id: "text-editor",
      title: "Text Editor",
      subtitle: "Edit config files directly",
      status: "live" as WorkspaceAppStatus,
      icon: <FileCode2 className="h-5 w-5" />,
    },
    {
      id: "quick-run",
      title: "Quick Run",
      subtitle: "Execute commands with output",
      status: "live" as WorkspaceAppStatus,
      icon: <Terminal className="h-5 w-5" />,
    },
    {
      id: "settings",
      title: "Settings",
      subtitle: "System info, users, cron, security",
      status: "live" as WorkspaceAppStatus,
      icon: <Settings className="h-5 w-5" />,
    },
  ], [availableApps?.disk, availableApps?.docker, availableApps?.logs, availableApps?.network, availableApps?.services, capabilities?.package_manager]);

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
    focusApp(appId);
  }, [appMap, focusApp]);

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

  const desktopApps = apps;
  const sortedWindowApps = [...openApps].sort(
    (left, right) => (windowStates[left]?.zIndex || 0) - (windowStates[right]?.zIndex || 0),
  );
  const visibleWindowApps = sortedWindowApps.filter((appId) => !windowStates[appId]?.minimized);
  const taskbarApps = openApps
    .map((appId) => ({ app: appMap[appId], minimized: Boolean(windowStates[appId]?.minimized) }))
    .filter((entry) => Boolean(entry.app));

  const closeAllWindows = useCallback(() => {
    openAppsRef.current = [];
    setOpenApps([]);
    activeAppRef.current = "overview";
    setActiveApp("overview");
    setDragState(null);
    setResizeState(null);
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
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      {/* Desktop area — takes all space above taskbar */}
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* Subtle desktop wallpaper effect */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,hsl(var(--primary)/0.06),transparent_60%)]" />

        <ContextMenu>
          <ContextMenuTrigger asChild>
            <div ref={workspaceCanvasRef} className="relative z-10 h-full min-h-0 overflow-y-auto p-3 lg:overflow-hidden lg:p-4">
              {server.server_type !== "ssh" ? (
                <div className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">
                  Linux Workspace is available only for SSH servers.
                </div>
              ) : null}

              {server.server_type === "ssh" && errorMessage ? (
                <div className="mb-3 rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                  {errorMessage}
                </div>
              ) : null}

              {server.server_type === "ssh" && (capabilitiesQuery.isLoading || overviewQuery.isLoading) ? (
                <div className="flex h-full min-h-[22rem] items-center justify-center">
                  <div className="rounded-xl border border-border bg-card px-8 py-10 text-center">
                    <RefreshCw className="mx-auto mb-3 h-5 w-5 animate-spin text-primary" />
                    <div className="text-sm font-medium text-foreground">Loading workspace...</div>
                    <div className="mt-1 text-xs text-muted-foreground">Collecting host capabilities</div>
                  </div>
                </div>
              ) : null}

              {server.server_type === "ssh" && !capabilitiesQuery.isLoading && !overviewQuery.isLoading ? (
                <div className="relative min-h-full gap-3 lg:h-full">
                  {/* Desktop icons grid — shown when no windows are open */}
                  {openApps.length === 0 ? (
                    <div className="flex h-full items-start justify-start p-4">
                      <div className="grid grid-cols-4 gap-1 sm:grid-cols-5 lg:grid-cols-6">
                        {desktopApps.map((app) => (
                          <DesktopIcon
                            key={app.id}
                            title={app.title}
                            icon={app.icon}
                            status={app.status}
                            onOpen={() => launchApp(app.id)}
                          />
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {/* Floating windows */}
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
                          <SftpPanel server={server} active={active && activeApp === "files"} />
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
                        {appId === "disk" ? <DiskWindow server={server} active={active} diskEnabled={Boolean(availableApps?.disk)} /> : null}
                        {appId === "network" ? <NetworkWindow server={server} active={active} networkEnabled={Boolean(availableApps?.network)} /> : null}
                        {appId === "docker" ? <DockerWindow server={server} active={active} dockerEnabled={Boolean(availableApps?.docker)} /> : null}
                        {appId === "packages" ? <PackagesWindow server={server} active={active} packageManager={capabilities?.package_manager || ""} /> : null}
                        {appId === "text-editor" ? <TextEditorWindow server={server} active={active && activeApp === "text-editor"} /> : null}
                        {appId === "quick-run" ? <QuickRunWindow server={server} active={active && activeApp === "quick-run"} /> : null}
                        {appId === "settings" ? <SystemSettingsWindow server={server} active={active && activeApp === "settings"} /> : null}
                      </WorkspaceWindow>
                    );
                  })}
                </div>
              ) : null}
            </div>
          </ContextMenuTrigger>
          <ContextMenuContent className="w-52 rounded-lg border-border bg-card">
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

      {/* KDE-style bottom taskbar */}
      <footer className="relative z-20 flex h-11 items-center gap-1 border-t border-border bg-card/95 px-2 backdrop-blur-sm">
        {/* App launcher button */}
        <ContextMenu>
          <ContextMenuTrigger asChild>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 w-8 shrink-0 p-0 text-primary hover:bg-primary/15"
              onClick={() => {
                if (openApps.length === 0) {
                  launchApp("overview");
                } else {
                  minimizeAllWindows();
                }
              }}
            >
              <Monitor className="h-4 w-4" />
            </Button>
          </ContextMenuTrigger>
          <ContextMenuContent className="w-48 rounded-lg border-border bg-card">
            <ContextMenuLabel className="text-[11px]">{server.name}</ContextMenuLabel>
            {desktopApps.map((app) => (
              <ContextMenuItem key={app.id} onSelect={() => launchApp(app.id)} disabled={app.status === "unavailable"}>
                <span className="mr-2 flex h-4 w-4 items-center justify-center [&>svg]:h-3 [&>svg]:w-3">{app.icon}</span>
                {app.title}
              </ContextMenuItem>
            ))}
            <ContextMenuSeparator />
            <ContextMenuItem onSelect={refresh}>Refresh</ContextMenuItem>
            {onClose ? <ContextMenuItem onSelect={onClose} className="text-destructive focus:text-destructive">Exit Workspace</ContextMenuItem> : null}
          </ContextMenuContent>
        </ContextMenu>

        <div className="mx-1 h-5 w-px bg-border/60" />

        {/* Running app buttons */}
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
                onClick={() => toggleTaskbarApp(app.id)}
              />
            );
          })}
        </div>

        {/* System tray — server info */}
        <div className="mx-1 h-5 w-px bg-border/60" />
        <div className="flex shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
          <span className="hidden sm:inline font-mono">{server.username}@{server.host}</span>
          {capabilities?.os_name ? <span className="hidden lg:inline">· {capabilities.os_name}</span> : null}
          <span className="tabular-nums">{openApps.length}w</span>
        </div>
      </footer>
    </div>
  );
}
