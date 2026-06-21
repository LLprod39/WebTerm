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
import { cn } from "@/lib/utils";

const EMPTY_DOCKER_CONTAINERS: LinuxUiDockerContainer[] = [];

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
                        <div className="text-xs uppercase tracking-wide text-muted-foreground">Last action</div>
                        <div className="mt-2 text-sm text-foreground">
                          {lastAction ? `${lastAction.action} ${lastAction.container}` : "No docker action has been executed yet."}
                        </div>
                        {lastAction ? (
                          <div className={cn("mt-2 inline-flex rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", lastAction.success ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-destructive/30 bg-destructive/10 text-destructive")}>
                            {lastAction.success ? "success" : "failed"}
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
