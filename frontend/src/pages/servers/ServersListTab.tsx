import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  ChevronRight,
  Plus,
  Server,
  Settings,
  Sparkles,
  Terminal,
  Trash2,
} from "lucide-react";
import { FleetHealthIndicator, StatusIndicator } from "@/components/StatusIndicator";
import { ServerOsBadge } from "@/components/servers/ServerOsBadge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/page-shell";
import type { FrontendServer, MonitoringStatusItem } from "@/lib/api";
import { resolveServerOs, serverOsLabelKey } from "@/lib/server-os";
import { displayServerGroupName, formatServerCount } from "./formatters";

interface ServersListTabProps {
  grouped: Record<string, FrontendServer[]>;
  filteredCount: number;
  totalServers: number;
  collapsed: Record<string, boolean>;
  fleetHealthByServerId: Map<number, MonitoringStatusItem>;
  t: (key: string) => string;
  tr: (key: string, vars?: Record<string, string | number>) => string;
  lang: string;
  onToggleGroup: (group: string) => void;
  onOpenCreate: () => void;
  onOpenAdvanced: (server: FrontendServer) => void | Promise<void>;
  onOpenEdit: (server: FrontendServer) => void | Promise<void>;
  onRequestDeleteServer: (server: FrontendServer) => void;
  onClearSearch: () => void;
}

export function ServersListTab({
  grouped,
  filteredCount,
  totalServers,
  collapsed,
  fleetHealthByServerId,
  t,
  tr,
  lang,
  onToggleGroup,
  onOpenCreate,
  onOpenAdvanced,
  onOpenEdit,
  onRequestDeleteServer,
  onClearSearch,
}: ServersListTabProps) {
  return (
    <>
      {Object.entries(grouped).map(([group, inGroup]) => {
        const isCollapsed = collapsed[group];
        const groupLabel = displayServerGroupName(group, lang);

        return (
          <div key={group} className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
            <button
              onClick={() => onToggleGroup(group)}
              className="w-full flex items-center gap-3 px-4 py-3 transition-colors text-left hover:bg-secondary/30"
              aria-label={tr(isCollapsed ? "srv.expand_group" : "srv.collapse_group", {
                name: groupLabel,
              })}
            >
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-lg transition-colors ${
                  isCollapsed ? "bg-secondary/40" : "bg-primary/10"
                }`}
              >
                {isCollapsed ? (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-primary" />
                )}
              </span>
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                <Server className="h-4 w-4 text-primary" />
              </div>
              <span className="text-sm font-semibold tracking-tight text-foreground">
                {groupLabel}
              </span>
              <span className="ml-auto rounded-md border border-border/50 bg-secondary/30 px-2 py-1 text-xs font-medium text-muted-foreground">
                {formatServerCount(inGroup.length, lang)}
              </span>
            </button>

            <AnimatePresence initial={false}>
              {!isCollapsed && (
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: "auto" }}
                  exit={{ height: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="border-t border-border">
                    {inGroup.map((server, i) => {
                      const displayStatus = server.status;
                      const fleetHealth = fleetHealthByServerId.get(server.id);
                      const osKind = resolveServerOs(server);
                      const connLabel = t("srv.conn.ssh");

                      return (
                        <div
                          key={server.id}
                          className={`group flex flex-col gap-3 px-4 py-3 transition-all duration-150 hover:bg-secondary/20 sm:flex-row sm:items-center ${
                            i < inGroup.length - 1 ? "border-b border-border/40" : ""
                          }`}
                        >
                          <div className="flex min-w-0 flex-1 items-start gap-3 sm:items-center">
                            <ServerOsBadge kind={osKind} size="md" />
                            <div className="min-w-0 flex-1 space-y-1">
                              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                <p className="truncate text-sm font-semibold tracking-tight text-foreground">
                                  {server.name}
                                </p>
                                {server.is_shared ? (
                                  <span className="rounded-full border border-border bg-secondary/30 px-2 py-0.5 text-[10px] text-muted-foreground">
                                    {t("srv.shared_badge")}
                                  </span>
                                ) : null}
                                <span className="hidden rounded-md border border-border/60 bg-background/80 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline">
                                  {connLabel}
                                </span>
                              </div>
                              <p className="font-mono text-[11px] text-muted-foreground">
                                {server.host}:{server.port}
                              </p>
                              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px]">
                                <span className="font-medium text-muted-foreground">
                                  {t(serverOsLabelKey(osKind))}
                                </span>
                                <span className="text-border" aria-hidden>
                                  &middot;
                                </span>
                                <span className="text-muted-foreground sm:hidden">
                                  {connLabel}
                                </span>
                                <span className="hidden text-border sm:inline" aria-hidden>
                                  &middot;
                                </span>
                                <span className="hidden sm:inline">
                                  {fleetHealth ? (
                                    <FleetHealthIndicator
                                      status={fleetHealth.status}
                                      stale={fleetHealth.is_stale}
                                      showLabel
                                    />
                                  ) : (
                                    <StatusIndicator status={displayStatus} showLabel />
                                  )}
                                </span>
                              </div>
                            </div>
                          </div>
                          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
                            <span className="sm:hidden">
                              {fleetHealth ? (
                                <FleetHealthIndicator
                                  status={fleetHealth.status}
                                  stale={fleetHealth.is_stale}
                                />
                              ) : (
                                <StatusIndicator status={displayStatus} />
                              )}
                            </span>
                            <Button
                              asChild
                              size="xs"
                              variant="outline"
                              className="h-9 gap-1.5 border-border hover:border-primary hover:text-primary"
                            >
                              <Link to={`/servers/${server.id}/terminal`}>
                                <Terminal className="h-3 w-3" /> SSH
                              </Link>
                            </Button>
                            <Button
                              size="icon"
                              variant="outline"
                              className="h-9 w-9"
                              onClick={() => void onOpenAdvanced(server)}
                              aria-label={tr("srv.open_advanced_for", { name: server.name })}
                              title={t("srv.advanced")}
                            >
                              <Sparkles className="h-3.5 w-3.5" />
                            </Button>
                            {server.can_edit && (
                              <>
                                <Button
                                  size="icon"
                                  variant="outline"
                                  className="h-9 w-9"
                                  onClick={() => void onOpenEdit(server)}
                                  aria-label={tr("srv.edit_server_for", { name: server.name })}
                                  title={t("srv.edit_server")}
                                >
                                  <Settings className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  size="icon"
                                  variant="destructive"
                                  className="h-9 w-9"
                                  onClick={() => onRequestDeleteServer(server)}
                                  aria-label={tr("srv.delete_server_for", { name: server.name })}
                                  title={t("srv.delete")}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}

      {!filteredCount ? (
        <EmptyState
          icon={<Server className="h-5 w-5" />}
          title={totalServers ? t("srv.empty_filtered_title") : t("srv.empty_title")}
          description={totalServers ? t("srv.empty_filtered_text") : t("srv.empty_text")}
          actions={
            <>
              {totalServers ? (
                <Button size="sm" variant="outline" className="h-9" onClick={onClearSearch}>
                  {t("srv.clear_search")}
                </Button>
              ) : null}
              <Button size="sm" className="h-9 gap-1.5" onClick={onOpenCreate}>
                <Plus className="h-3.5 w-3.5" /> {t("srv.add")}
              </Button>
            </>
          }
        />
      ) : null}
    </>
  );
}
