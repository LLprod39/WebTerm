import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Play, RefreshCw, RotateCcw, Square } from "lucide-react";

import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SummaryCard } from "@/components/terminal/linux-ui/SummaryCard";
import {
  fetchLinuxUiServiceLogs,
  fetchLinuxUiServices,
  runLinuxUiServiceAction,
  type FrontendServer,
  type LinuxUiServiceAction,
  type LinuxUiServiceActionResult,
  type LinuxUiServiceHealth,
  type LinuxUiServiceItem,
  type LinuxUiServicesSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const EMPTY_SERVICES: LinuxUiServiceItem[] = [];

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
        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", serviceHealthClass(service.health))}>
          {service.health}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">{service.load}</span>
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">
          {service.active}/{service.sub}
        </span>
      </div>
    </button>
  );
}

export function ServicesWindow({
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

  const services = servicesQuery.data?.services ?? EMPTY_SERVICES;
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
                        <span className={cn("rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", serviceHealthClass(selectedService.health))}>
                          {selectedService.health}
                        </span>
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
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
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
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
                        <div className="text-xs uppercase tracking-wide text-muted-foreground">Last action</div>
                        <div className="mt-2 text-sm text-foreground">
                          {lastAction ? `${lastAction.action} ${lastAction.service}` : "No service action has been executed yet."}
                        </div>
                        {lastAction ? (
                          <div className={cn("mt-2 inline-flex rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", lastAction.success ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-destructive/30 bg-destructive/10 text-destructive")}>
                            {lastAction.success ? "success" : "failed"}
                          </div>
                        ) : null}
                      </div>
                      {lastAction?.output ? (
                        <ScrollArea className="mt-3 h-36 rounded-2xl border border-border/70 bg-background/94">
                          <pre className="whitespace-pre-wrap break-words px-3 py-3 font-mono text-xs leading-5 text-muted-foreground">
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
