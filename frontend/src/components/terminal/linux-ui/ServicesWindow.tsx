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
import { localize, useI18n } from "@/lib/i18n";
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

function serviceActionMeta(action: LinuxUiServiceAction, lang: string) {
  switch (action) {
    case "start":
      return { label: localize(lang, "Запустить", "Start"), confirmLabel: localize(lang, "Запустить сервис", "Start service"), destructive: false, icon: <Play className="h-3.5 w-3.5" /> };
    case "stop":
      return { label: localize(lang, "Остановить", "Stop"), confirmLabel: localize(lang, "Остановить сервис", "Stop service"), destructive: true, icon: <Square className="h-3.5 w-3.5" /> };
    case "restart":
      return { label: localize(lang, "Перезапустить", "Restart"), confirmLabel: localize(lang, "Перезапустить сервис", "Restart service"), destructive: false, icon: <RefreshCw className="h-3.5 w-3.5" /> };
    case "reload":
      return { label: localize(lang, "Перечитать", "Reload"), confirmLabel: localize(lang, "Перечитать конфигурацию", "Reload service"), destructive: false, icon: <RotateCcw className="h-3.5 w-3.5" /> };
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
  const { lang } = useI18n();
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
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{service.description || localize(lang, "Нет описания", "No description")}</div>
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
  const { lang } = useI18n();
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
        ? localize(lang, `Остановить ${unit}? Это может сразу прервать трафик или фоновые задачи.`, `Stop ${unit}? This may immediately interrupt traffic or background workers.`)
        : `${serviceActionMeta(confirmState.action, lang).label} ${unit}?`;
    if (isConnectionCriticalService(unit) && ["stop", "restart"].includes(confirmState.action)) {
      return localize(lang, `${base} Текущая SSH-сессия может оборваться.`, `${base} The current SSH session may disconnect.`);
    }
    return base;
  }, [confirmState, lang]);

  if (!servicesEnabled) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center p-6">
        <div className="max-w-lg rounded-3xl border border-border/70 bg-background/92 p-6 text-center">
          <AlertTriangle className="mx-auto h-5 w-5 text-amber-300" />
          <div className="mt-3 text-sm font-medium text-foreground">{localize(lang, "systemctl недоступен", "systemctl is unavailable")}</div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">
            {localize(lang, "На этом хосте нельзя управлять unit systemd.", "Systemd units cannot be managed on this host.")}
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
            <div className="text-sm font-medium text-foreground">{localize(lang, "Сервисы systemd", "Systemd services")}</div>
            <div className="mt-1 text-xs text-muted-foreground">{localize(lang, "Состояние и управление сервисами.", "Service state and actions.")}</div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={localize(lang, "Найти сервис...", "Filter services...")}
              className="h-9 min-w-[16rem] bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={refreshServices}>
              <RefreshCw className={cn("h-3.5 w-3.5", (servicesQuery.isFetching || logsQuery.isFetching) && "animate-spin")} />
              {localize(lang, "Обновить", "Refresh")}
            </Button>
          </div>
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-4">
          <SummaryCard label={localize(lang, "Всего", "Total")} value={summary.total} hint={localize(lang, "Загруженные unit", "Loaded units")} />
          <SummaryCard label={localize(lang, "Активны", "Active")} value={summary.active} hint={localize(lang, "Работают сейчас", "Running now")} />
          <SummaryCard label={localize(lang, "С ошибкой", "Failed")} value={summary.failed} hint={localize(lang, "Требуют внимания", "Needs attention")} alert={summary.failed > 0} />
          <SummaryCard label={localize(lang, "Неактивны", "Inactive")} value={summary.inactive} hint={localize(lang, "Остановлены", "Stopped units")} />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {localize(lang, "Сервисы", "Services")}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {localize(lang, `Показано ${filteredServices.length} из ${services.length}`, `${filteredServices.length} of ${services.length} visible`)}
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
                    {localize(lang, "Загружаем сервисы...", "Loading services...")}
                  </div>
                ) : null}

                {!servicesQuery.isLoading && filteredServices.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    {localize(lang, "Ничего не найдено.", "No services match the current filter.")}
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
                      <div className="mt-2 text-sm text-muted-foreground">{selectedService.description || localize(lang, "Нет описания.", "No description available.")}</div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-3">
                        <SummaryCard label={localize(lang, "Загрузка", "Load")} value={selectedService.load} hint={localize(lang, "Состояние загрузки unit", "Unit load state")} />
                        <SummaryCard label={localize(lang, "Активность", "Active")} value={selectedService.active} hint={localize(lang, "Состояние systemctl", "systemctl active state")} alert={selectedService.health === "failed"} />
                        <SummaryCard label={localize(lang, "Подсостояние", "Sub-state")} value={selectedService.sub} hint={localize(lang, "Детальное состояние", "systemctl sub-state")} />
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 xl:max-w-[16rem] xl:justify-end">
                      {(["start", "restart", "reload", "stop"] as LinuxUiServiceAction[]).map((action) => {
                        const meta = serviceActionMeta(action, lang);
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
                        <div className="text-sm font-medium text-foreground">{localize(lang, "Последний вывод", "Recent output")}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {logsEnabled ? logsQuery.data?.service_logs.source || "journalctl" : "systemctl status fallback"}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                          {localize(lang, `${logsQuery.data?.service_logs.lines || 80} строк`, `${logsQuery.data?.service_logs.lines || 80} lines`)}
                        </span>
                        {logsEnabled ? (
                          <Button type="button" size="sm" variant="ghost" className="h-8 text-xs" onClick={onOpenLogs}>
                            {localize(lang, "Все логи", "All logs")}
                          </Button>
                        ) : null}
                      </div>
                    </div>
                    <ScrollArea className="h-[18rem] lg:h-full">
                      <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                        {logsQuery.error instanceof Error
                          ? logsQuery.error.message
                          : logsQuery.isLoading
                            ? localize(lang, "Загружаем вывод сервиса...", "Loading service output...")
                            : logsQuery.data?.service_logs.content || localize(lang, "Вывода пока нет.", "No recent service output.")}
                      </pre>
                    </ScrollArea>
                  </div>

                  <div className="flex min-h-0 flex-col gap-4">
                    <div className="rounded-3xl border border-border/70 bg-card/88 p-4">
                      <div className="text-sm font-medium text-foreground">{localize(lang, "Последнее действие", "Last action")}</div>
                      <div className="mt-4 rounded-2xl border border-border/70 bg-background/94 p-3">
                        <div className="mt-2 text-sm text-foreground">
                          {lastAction ? `${lastAction.action} ${lastAction.service}` : localize(lang, "Действий ещё не было.", "No service action has been run yet.")}
                        </div>
                        {lastAction ? (
                          <div className={cn("mt-2 inline-flex rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", lastAction.success ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-destructive/30 bg-destructive/10 text-destructive")}>
                            {lastAction.success ? localize(lang, "успешно", "success") : localize(lang, "ошибка", "failed")}
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
                      <div className="text-sm font-medium text-foreground">{localize(lang, "Важно", "Important")}</div>
                      <div className="mt-2">{localize(lang, "Нужны права на управление системными сервисами.", "The account needs permission to manage system services.")}</div>
                      <div className="mt-2">{localize(lang, "Перезапуск SSH или сети может оборвать текущую сессию.", "Restarting SSH or networking may disconnect this session.")}</div>
                      <div className="mt-2">{localize(lang, "Для дополнительных флагов и sudo используйте терминал.", "Use the terminal for custom flags or sudo.")}</div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
                {localize(lang, "Выберите сервис.", "Select a service.")}
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
        title={confirmState ? `${serviceActionMeta(confirmState.action, lang).label} ${confirmState.service.unit}` : localize(lang, "Подтвердите действие", "Confirm service action")}
        description={confirmDescription}
        confirmLabel={confirmState ? serviceActionMeta(confirmState.action, lang).confirmLabel : localize(lang, "Подтвердить", "Confirm")}
        destructive={Boolean(confirmState && (serviceActionMeta(confirmState.action, lang).destructive || isConnectionCriticalService(confirmState.service.unit)))}
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
