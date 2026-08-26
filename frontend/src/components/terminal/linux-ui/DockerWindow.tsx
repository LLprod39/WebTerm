import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { SummaryCard } from "@/components/terminal/linux-ui/SummaryCard";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  fetchLinuxUiDocker,
  fetchLinuxUiDockerLogs,
  runLinuxUiDockerAction,
  type FrontendServer,
  type LinuxUiDockerAction,
  type LinuxUiDockerActionResult,
  type LinuxUiDockerContainer,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const EMPTY_DOCKER_CONTAINERS: LinuxUiDockerContainer[] = [];

function dockerActionMeta(action: LinuxUiDockerAction, lang: string) {
  switch (action) {
    case "start":
      return { label: localize(lang, "Запустить", "Start"), confirmLabel: localize(lang, "Запустить контейнер", "Start container"), destructive: false };
    case "stop":
      return { label: localize(lang, "Остановить", "Stop"), confirmLabel: localize(lang, "Остановить контейнер", "Stop container"), destructive: true };
    case "restart":
      return { label: localize(lang, "Перезапустить", "Restart"), confirmLabel: localize(lang, "Перезапустить контейнер", "Restart container"), destructive: false };
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
          <div className="mt-1 truncate text-xs text-muted-foreground">{item.image}</div>
        </div>
        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", item.state === "running" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : item.state === "restarting" ? "border-amber-500/20 bg-amber-500/10 text-amber-300" : "border-border/70 bg-background/94 text-muted-foreground")}>
          {item.state}
        </span>
      </div>
      <div className="mt-2 text-xs text-muted-foreground">{item.status}</div>
      {item.ports ? (
        <div className="mt-2 truncate font-mono text-xs text-muted-foreground">{item.ports}</div>
      ) : null}
    </button>
  );
}

export function DockerWindow({
  server,
  active,
  dockerEnabled,
}: {
  server: FrontendServer;
  active: boolean;
  dockerEnabled: boolean;
}) {
  const { lang } = useI18n();
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
  const containers = dockerPayload?.containers ?? EMPTY_DOCKER_CONTAINERS;
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
    const base = localize(
      lang,
      `${dockerActionMeta(confirmState.action, lang).label} контейнер ${confirmState.container.name}?`,
      `${dockerActionMeta(confirmState.action, lang).label} container ${confirmState.container.name}?`,
    );
    if (confirmState.action === "stop") {
      return localize(lang, `${base} Связанные сервисы могут стать недоступны.`, `${base} Services behind it may become unavailable.`);
    }
    return localize(lang, `${base} Состояние обновится после выполнения.`, `${base} Container state will refresh after the action.`);
  }, [confirmState, lang]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">Docker</div>
            <div className="mt-1 text-xs text-muted-foreground">{localize(lang, "Контейнеры, логи и основные действия.", "Containers, logs, and common actions.")}</div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={localize(lang, "Найти контейнер...", "Filter containers...")}
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
              {localize(lang, "Обновить", "Refresh")}
            </Button>
          </div>
        </div>
        {!dockerEnabled ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            {localize(lang, "Docker недоступен на этом хосте.", "Docker is not available on this host.")}
          </div>
        ) : null}
        {dockerPayload?.error ? (
          <div className="mt-3 rounded-2xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {dockerPayload.error}
          </div>
        ) : null}
        <div className="mt-4 grid gap-2 md:grid-cols-5">
          <SummaryCard label={localize(lang, "Всего", "Total")} value={dockerPayload?.summary.total || 0} hint={localize(lang, "Все контейнеры", "Known containers")} />
          <SummaryCard label={localize(lang, "Запущены", "Running")} value={dockerPayload?.summary.running || 0} hint={localize(lang, "Работают сейчас", "Running now")} />
          <SummaryCard label={localize(lang, "Остановлены", "Exited")} value={dockerPayload?.summary.exited || 0} hint={localize(lang, "Не запущены", "Stopped containers")} alert={(dockerPayload?.summary.exited || 0) > 0} />
          <SummaryCard label={localize(lang, "Перезапускаются", "Restarting")} value={dockerPayload?.summary.restarting || 0} hint={localize(lang, "Требуют внимания", "Needs attention")} alert={(dockerPayload?.summary.restarting || 0) > 0} />
          <SummaryCard label={localize(lang, "На паузе", "Paused")} value={dockerPayload?.summary.paused || 0} hint={localize(lang, "Приостановлены", "Paused containers")} />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-sm font-medium text-foreground">{localize(lang, "Контейнеры", "Containers")}</div>
              <div className="mt-1 text-xs text-muted-foreground">{localize(lang, `Показано: ${filteredContainers.length}`, `${filteredContainers.length} visible`)}</div>
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
                    {localize(lang, "Загружаем данные Docker...", "Loading Docker data...")}
                  </div>
                ) : null}
                {!dockerQuery.isLoading && filteredContainers.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    {localize(lang, "Ничего не найдено.", "No containers match the current filter.")}
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
                        <span className={cn("rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", selectedContainer.state === "running" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : selectedContainer.state === "restarting" ? "border-amber-500/20 bg-amber-500/10 text-amber-300" : "border-border/70 bg-background/94 text-muted-foreground")}>
                          {selectedContainer.state}
                        </span>
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                          {selectedContainer.id.slice(0, 12)}
                        </span>
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">{selectedContainer.image}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{selectedContainer.status}</div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-4">
                        <SummaryCard label="CPU" value={selectedContainer.cpu_percent || "n/a"} hint="docker stats CPU%" />
                        <SummaryCard label={localize(lang, "Память", "Memory")} value={selectedContainer.memory_percent || "n/a"} hint={selectedContainer.memory_usage || localize(lang, "Нет текущих данных", "No live stats")} />
                        <SummaryCard label={localize(lang, "Сеть", "Network")} value={selectedContainer.network_io || "n/a"} hint="Net IO" />
                        <SummaryCard label={localize(lang, "Диск", "Block")} value={selectedContainer.block_io || "n/a"} hint="Block IO" />
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
                          {dockerActionMeta(action, lang).label}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid min-h-0 gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
                  <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
                    <div className="border-b border-border/60 px-4 py-3">
                      <div className="text-sm font-medium text-foreground">{localize(lang, "Последние логи", "Recent logs")}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {localize(lang, `${lines} строк из`, `${lines} lines from`)} <span className="font-mono">{selectedContainer.name}</span>
                      </div>
                    </div>
                    <ScrollArea className="h-full">
                      <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                        {dockerLogsQuery.error instanceof Error
                          ? dockerLogsQuery.error.message
                          : dockerLogsQuery.isLoading
                          ? localize(lang, "Загружаем логи...", "Loading Docker logs...")
                          : dockerLogsQuery.data?.docker_logs.content || localize(lang, "Логов пока нет.", "No log lines available.")}
                      </pre>
                    </ScrollArea>
                  </div>

                  <div className="flex min-h-0 flex-col gap-4">
                    <div className="rounded-3xl border border-border/70 bg-card/88 p-4">
                      <div className="text-sm font-medium text-foreground">{localize(lang, "Последнее действие", "Last action")}</div>
                      <div className="mt-4 rounded-2xl border border-border/70 bg-background/94 p-3">
                        <div className="mt-2 text-sm text-foreground">
                          {lastAction ? `${lastAction.action} ${lastAction.container}` : localize(lang, "Действий ещё не было.", "No Docker action has been run yet.")}
                        </div>
                        {lastAction ? (
                          <div className={cn("mt-2 inline-flex rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", lastAction.success ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-destructive/30 bg-destructive/10 text-destructive")}>
                            {lastAction.success ? localize(lang, "успешно", "success") : localize(lang, "ошибка", "failed")}
                          </div>
                        ) : null}
                      </div>
                      {lastAction?.output ? (
                        <ScrollArea className="mt-3 h-32 rounded-2xl border border-border/70 bg-background/94">
                          <pre className="whitespace-pre-wrap break-words px-3 py-3 font-mono text-xs leading-5 text-muted-foreground">
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
                      <div className="text-sm font-medium text-foreground">{localize(lang, "Важно", "Important")}</div>
                      <div className="mt-2">{localize(lang, "Сначала попробуйте перезапуск, если образ и конфигурация доверенные.", "Try restart first when the image and configuration are trusted.")}</div>
                      <div className="mt-2">{localize(lang, "Остановка сразу прервёт работу сервисов контейнера.", "Stopping immediately interrupts services in the container.")}</div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
                {localize(lang, "Выберите контейнер.", "Select a container.")}
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
        title={confirmState ? `${dockerActionMeta(confirmState.action, lang).label} ${confirmState.container.name}` : localize(lang, "Подтвердите действие", "Confirm Docker action")}
        description={confirmDescription}
        confirmLabel={confirmState ? dockerActionMeta(confirmState.action, lang).confirmLabel : localize(lang, "Подтвердить", "Confirm")}
        destructive={Boolean(confirmState && dockerActionMeta(confirmState.action, lang).destructive)}
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
