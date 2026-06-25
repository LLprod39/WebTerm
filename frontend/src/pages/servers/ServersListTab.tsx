import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  ChevronRight,
  Plus,
  Server,
  Settings,
  SlidersHorizontal,
  Terminal,
  Trash2,
} from "lucide-react";
import { FleetHealthIndicator, StatusIndicator } from "@/components/StatusIndicator";
import { ServerOsBadge } from "@/components/servers/ServerOsBadge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/page-shell";
import type { FrontendServer, MonitoringStatusItem } from "@/lib/api";
import { cn } from "@/lib/utils";
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
          <section key={group} className="overflow-hidden rounded-lg border border-border/80 bg-card/75">
            <button
              onClick={() => onToggleGroup(group)}
              className={cn(
                "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[color:var(--wt-hover)] sm:px-5",
                !isCollapsed && "border-b border-border/70",
              )}
              aria-label={tr(isCollapsed ? "srv.expand_group" : "srv.collapse_group", {
                name: groupLabel,
              })}
            >
              <span
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-colors",
                  isCollapsed
                    ? "border-border/70 bg-secondary/50 text-muted-foreground"
                    : "border-primary/25 bg-primary/10 text-primary",
                )}
              >
                {isCollapsed ? (
                  <ChevronRight className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </span>
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
                <Server className="h-4 w-4 text-primary" />
              </div>
              <span className="min-w-0 truncate text-sm font-semibold tracking-normal text-foreground">
                {groupLabel}
              </span>
              <span className="ml-auto rounded-md border border-border/60 bg-secondary/50 px-2.5 py-1 text-xs font-medium text-muted-foreground">
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
                  <div className="overflow-x-auto p-3 sm:p-4">
                    <table className="w-full min-w-[980px] table-fixed overflow-hidden rounded-lg border border-border/70 bg-background/25">
                      <colgroup>
                        <col className="w-[28%]" />
                        <col className="w-[22%]" />
                        <col className="w-[14%]" />
                        <col className="w-[16%]" />
                        <col className="w-[20%]" />
                      </colgroup>
                      <thead>
                        <tr className="bg-secondary/25 text-left text-xs font-medium text-muted-foreground">
                          <th scope="col" className="border-b border-border/70 px-4 py-3">
                            {t("srv.table.server")}
                          </th>
                          <th scope="col" className="border-b border-border/70 px-4 py-3">
                            {t("srv.table.ip_address")}
                          </th>
                          <th scope="col" className="border-b border-border/70 px-4 py-3">
                            {t("srv.table.os")}
                          </th>
                          <th scope="col" className="border-b border-border/70 px-4 py-3">
                            {t("srv.table.status")}
                          </th>
                          <th scope="col" className="border-b border-border/70 px-4 py-3 text-right">
                            {t("srv.table.actions")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {inGroup.map((server, i) => {
                          const displayStatus = server.status;
                          const fleetHealth = fleetHealthByServerId.get(server.id);
                          const osKind = resolveServerOs(server);
                          const connLabel = t("srv.conn.ssh");
                          const divider = i < inGroup.length - 1 && "border-b border-border/40";

                          return (
                            <tr
                              key={server.id}
                              className="group transition-colors duration-150 hover:bg-secondary/25"
                            >
                              <td className={cn("px-4 py-3 align-middle", divider)}>
                                <div className="flex min-w-0 items-center gap-3">
                                  <ServerOsBadge kind={osKind} size="md" />
                                  <div className="min-w-0">
                                    <div className="flex min-w-0 items-center gap-2">
                                      <span className="truncate text-sm font-semibold tracking-tight text-foreground">
                                        {server.name}
                                      </span>
                                      {server.is_shared ? (
                                        <span className="shrink-0 rounded-md border border-border/70 bg-secondary/50 px-2 py-0.5 text-xs text-muted-foreground">
                                          {t("srv.shared_badge")}
                                        </span>
                                      ) : null}
                                      <span className="shrink-0 rounded-md border border-border/60 bg-background/80 px-2 py-0.5 text-xs font-medium text-muted-foreground">
                                        {connLabel}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              </td>
                              <td className={cn("px-4 py-3 align-middle", divider)}>
                                <span className="block truncate font-mono text-xs text-muted-foreground">
                                  {server.host}:{server.port}
                                </span>
                              </td>
                              <td className={cn("px-4 py-3 align-middle", divider)}>
                                <span className="block truncate text-sm text-muted-foreground">
                                  {t(serverOsLabelKey(osKind))}
                                </span>
                              </td>
                              <td className={cn("px-4 py-3 align-middle", divider)}>
                                {fleetHealth ? (
                                  <FleetHealthIndicator
                                    status={fleetHealth.status}
                                    stale={fleetHealth.is_stale}
                                    showLabel
                                  />
                                ) : (
                                  <StatusIndicator status={displayStatus} showLabel />
                                )}
                              </td>
                              <td className={cn("px-4 py-2.5 align-middle", divider)}>
                                <div className="flex items-center justify-end gap-2">
                                  <Button
                                    asChild
                                    size="sm"
                                    variant="outline"
                                    className="h-9 gap-2 rounded-md border-border bg-card/70 px-3 hover:border-primary hover:text-primary"
                                  >
                                    <Link to={`/servers/${server.id}/terminal`}>
                                      <Terminal className="h-4 w-4" /> SSH
                                    </Link>
                                  </Button>
                                  <Button
                                    size="icon"
                                    variant="outline"
                                    className="h-9 w-9 rounded-md border-border bg-card/70"
                                    onClick={() => void onOpenAdvanced(server)}
                                    aria-label={tr("srv.open_advanced_for", { name: server.name })}
                                    title={t("srv.advanced")}
                                  >
                                    <SlidersHorizontal className="h-4 w-4" />
                                  </Button>
                                  {server.can_edit && (
                                    <>
                                      <Button
                                        size="icon"
                                        variant="outline"
                                        className="h-9 w-9 rounded-md border-border bg-card/70"
                                        onClick={() => void onOpenEdit(server)}
                                        aria-label={tr("srv.edit_server_for", { name: server.name })}
                                        title={t("srv.edit_server")}
                                      >
                                        <Settings className="h-4 w-4" />
                                      </Button>
                                      <Button
                                        size="icon"
                                        variant="outline"
                                        className="h-9 w-9 rounded-md border-border bg-card/70 text-destructive hover:border-destructive/50 hover:bg-destructive/10 hover:text-destructive"
                                        onClick={() => onRequestDeleteServer(server)}
                                        aria-label={tr("srv.delete_server_for", { name: server.name })}
                                        title={t("srv.delete")}
                                      >
                                        <Trash2 className="h-4 w-4" />
                                      </Button>
                                    </>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </section>
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
                <Button size="sm" variant="outline" className="h-10" onClick={onClearSearch}>
                  {t("srv.clear_search")}
                </Button>
              ) : null}
              <Button size="sm" className="h-10 gap-2" onClick={onOpenCreate}>
                <Plus className="h-4 w-4" /> {t("srv.add")}
              </Button>
            </>
          }
        />
      ) : null}
    </>
  );
}
