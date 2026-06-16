import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SummaryCard } from "@/components/terminal/linux-ui/SummaryCard";
import { formatMetric } from "@/components/terminal/linux-ui/linuxUiFormat";
import {
  fetchLinuxUiProcesses,
  runLinuxUiProcessAction,
  type FrontendServer,
  type LinuxUiProcessAction,
  type LinuxUiProcessActionResult,
  type LinuxUiProcessItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const EMPTY_PROCESSES: LinuxUiProcessItem[] = [];

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

export function ProcessesWindow({
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
  const sourceProcesses = mode === "cpu" ? processPayload?.top_cpu ?? EMPTY_PROCESSES : processPayload?.top_memory ?? EMPTY_PROCESSES;
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
