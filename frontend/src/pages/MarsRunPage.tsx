import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BrainCircuit, CheckCircle2, FileCode2, Loader2, Square, Terminal, XCircle } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { PageGrid, PageHero, PageShell, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { getMarsRunWsUrl, marsApi, type MarsRunEvent } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";

function runTone(status?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "stopped") return "warning";
  if (status === "queued" || status === "running") return "info";
  return "neutral";
}

function eventText(event: MarsRunEvent): string {
  const payloadText = event.payload?.text;
  return typeof payloadText === "string" && payloadText ? payloadText : event.message;
}

function isCliEvent(event: MarsRunEvent): boolean {
  return event.event_type.includes("_stdout") || event.event_type.includes("_stderr");
}

function publicEventLabel(eventType: string, lang: string): string {
  if (eventType.includes("architect")) return localize(lang, "Понимание задачи", "Understanding");
  if (eventType.includes("repair")) return localize(lang, "Исправление", "Repair");
  if (eventType.includes("tests")) return localize(lang, "Проверка", "Verification");
  if (eventType.includes("gemini") || eventType.includes("review")) return localize(lang, "Проверка качества", "Quality check");
  if (eventType.includes("codex") || eventType.includes("build")) return localize(lang, "Создание", "Build");
  if (eventType.includes("orchestrator")) return localize(lang, "Подготовка процесса", "Workflow setup");
  if (eventType.includes("mars_run_completed")) return localize(lang, "Готово", "Completed");
  if (eventType.includes("mars_run_failed")) return localize(lang, "Ошибка", "Failed");
  if (eventType.includes("mars_run_started")) return localize(lang, "Запуск", "Started");
  if (eventType.includes("mars_run_queued")) return localize(lang, "В очереди", "Queued");
  return eventType.replaceAll("_", " ");
}

function publicEventMessage(event: MarsRunEvent, lang: string): string {
  if (/(codex|gemini|orchestrator)/i.test(event.event_type) || /(codex|gemini)/i.test(event.message)) {
    return publicEventLabel(event.event_type, lang);
  }
  return event.message;
}

function parseChangedFiles(statusText?: string): string[] {
  return (statusText || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.slice(2).trim())
    .filter(Boolean);
}

export default function MarsRunPage() {
  const { runId } = useParams();
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const numericRunId = Number(runId);
  const [liveEvents, setLiveEvents] = useState<MarsRunEvent[]>([]);

  const runQuery = useQuery({
    queryKey: ["mars", "run", numericRunId],
    queryFn: () => marsApi.getRun(numericRunId),
    enabled: Number.isFinite(numericRunId) && numericRunId > 0,
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
    retry: false,
  });

  const run = runQuery.data?.run;
  const eventsQuery = useQuery({
    queryKey: ["mars", "run-events", numericRunId],
    queryFn: () => marsApi.listRunEvents(numericRunId),
    enabled: Number.isFinite(numericRunId) && numericRunId > 0,
    refetchInterval: run?.status === "queued" || run?.status === "running" ? 2000 : false,
    retry: false,
  });

  useEffect(() => {
    if (!Number.isFinite(numericRunId) || numericRunId <= 0) return;
    setLiveEvents([]);
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(getMarsRunWsUrl(numericRunId));
      socket.onmessage = (message) => {
        try {
          const data = JSON.parse(message.data) as { type?: string; event?: MarsRunEvent };
          if (data.type === "mars_event" && data.event) {
            setLiveEvents((current) => {
              if (current.some((event) => event.id === data.event?.id)) return current;
              return [...current, data.event as MarsRunEvent].slice(-500);
            });
          }
        } catch {
          // ignore malformed websocket payloads
        }
      };
    } catch {
      return;
    }
    return () => socket?.close();
  }, [numericRunId]);

  const events = useMemo(() => {
    const byId = new Map<number, MarsRunEvent>();
    for (const event of eventsQuery.data?.events ?? []) byId.set(event.id, event);
    for (const event of liveEvents) byId.set(event.id, event);
    return Array.from(byId.values()).sort((a, b) => a.id - b.id);
  }, [eventsQuery.data?.events, liveEvents]);

  const stopRun = useMutation({
    mutationFn: () => marsApi.stopRun(numericRunId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["mars", "run", numericRunId] }),
  });

  const changedFiles = parseChangedFiles(run?.git_after);
  const cliLines = events.filter(isCliEvent).map((event) => {
    const stream = event.event_type.includes("_stderr") ? "stderr" : "stdout";
    return `[${stream}] ${eventText(event)}`;
  });
  const checklist = [
    { label: localize(lang, "Рабочая папка", "Workspace policy"), done: events.some((event) => event.event_type === "mars_run_started") },
    { label: localize(lang, "Создание", "Build"), done: events.some((event) => event.event_type === "codex_finished") || Boolean(run?.codex_summary) },
    { label: localize(lang, "Verification", "Verification"), done: events.some((event) => event.event_type.startsWith("tests_")) || Boolean(run?.test_output) },
    { label: localize(lang, "Качество", "Quality"), done: events.some((event) => event.event_type === "gemini_finished") || Boolean(run?.gemini_review) },
    { label: localize(lang, "Final report", "Final report"), done: Boolean(run?.final_report) },
  ];
  const progress = Math.round((checklist.filter((item) => item.done).length / checklist.length) * 100);
  const canStop = run?.status === "queued" || run?.status === "running";

  return (
    <PageShell width="full" className="space-y-5">
      <PageHero
        kicker="MARS"
        title={localize(lang, "Запуск задачи", "Task run")}
        description={
          run?.workspace.name
            ? localize(lang, `Рабочая папка: ${run.workspace.name}`, `Workspace: ${run.workspace.name}`)
            : localize(lang, "Загрузка рабочей папки...", "Loading workspace...")
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" asChild>
              <Link to="/mars">
                <ArrowLeft className="h-4 w-4" />
                {localize(lang, "Назад", "Back")}
              </Link>
            </Button>
            <StatusBadge label={run?.status || "loading"} tone={runTone(run?.status)} />
            <Button variant="outline" onClick={() => stopRun.mutate()} disabled={!canStop || stopRun.isPending}>
              {stopRun.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
              {localize(lang, "Остановить", "Stop")}
            </Button>
          </div>
        }
      />

      <QueryStateBlock loading={runQuery.isLoading} error={runQuery.error}>
        <PageGrid sidebar>
          <div className="space-y-5">
            <SectionCard
              title={localize(lang, "Ход работы", "Progress")}
              description={localize(lang, "Основные события запуска без внутренних деталей.", "Main run events without internal details.")}
              icon={<BrainCircuit className="h-4 w-4" />}
            >
              <div className="space-y-4">
                <Progress value={progress} />
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                  {checklist.map((item) => (
                    <div key={item.label} className="flex min-h-12 items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm">
                      {item.done ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <XCircle className="h-4 w-4 text-muted-foreground/50" />}
                      <span className="truncate">{item.label}</span>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  {events.filter((event) => !isCliEvent(event)).slice(-40).map((event) => (
                    <div key={event.id} className="rounded-lg border border-border bg-secondary/15 px-3 py-2">
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-xs font-semibold text-foreground">{publicEventLabel(event.event_type, lang)}</span>
                        <span className="shrink-0 text-[10px] text-muted-foreground">{event.created_at ? new Date(event.created_at).toLocaleTimeString() : ""}</span>
                      </div>
                      {event.message ? <div className="mt-1 text-xs leading-5 text-muted-foreground">{publicEventMessage(event, lang)}</div> : null}
                    </div>
                  ))}
                  {events.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                      {localize(lang, "Событий пока нет.", "No events yet.")}
                    </div>
                  ) : null}
                </div>
              </div>
            </SectionCard>

            <SectionCard title={localize(lang, "Журнал выполнения", "Execution log")} icon={<Terminal className="h-4 w-4" />}>
              <pre className="max-h-[460px] overflow-auto rounded-lg bg-black p-4 text-xs leading-5 text-zinc-100">
                {cliLines.length ? cliLines.join("\n") : localize(lang, "CLI stdout/stderr появится здесь.", "CLI stdout/stderr appears here.")}
              </pre>
            </SectionCard>

            <div className="grid gap-5 xl:grid-cols-2">
              <SectionCard title={localize(lang, "Результат выполнения", "Run result")} icon={<BrainCircuit className="h-4 w-4" />}>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/20 p-4 text-xs leading-5 text-foreground">
                  {run?.codex_summary || localize(lang, "Результат пока пуст.", "No result yet.")}
                </pre>
              </SectionCard>
              <SectionCard title={localize(lang, "Проверка качества", "Quality check")} icon={<BrainCircuit className="h-4 w-4" />}>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/20 p-4 text-xs leading-5 text-foreground">
                  {run?.gemini_review || localize(lang, "Review еще не готов.", "Review is not ready yet.")}
                </pre>
              </SectionCard>
            </div>
          </div>

          <div className="space-y-5">
            <SectionCard title={localize(lang, "Changed files", "Changed files")} icon={<FileCode2 className="h-4 w-4" />}>
              <div className="space-y-2">
                {changedFiles.length ? (
                  changedFiles.map((file) => (
                    <div key={file} className="truncate rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs">
                      {file}
                    </div>
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                    {localize(lang, "Git status чистый.", "Git status is clean.")}
                  </div>
                )}
              </div>
            </SectionCard>

            <SectionCard title={localize(lang, "Tests", "Tests")} icon={<Terminal className="h-4 w-4" />}>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/20 p-4 text-xs leading-5 text-foreground">
                {run?.test_output || localize(lang, "Verification command не запускался.", "No verification command was run.")}
              </pre>
            </SectionCard>

            <SectionCard title={localize(lang, "Final report", "Final report")} icon={<CheckCircle2 className="h-4 w-4" />}>
              <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/20 p-4 text-xs leading-5 text-foreground">
                {run?.final_report || localize(lang, "Финальный отчет появится после завершения.", "Final report appears after completion.")}
              </pre>
            </SectionCard>
          </div>
        </PageGrid>
      </QueryStateBlock>
    </PageShell>
  );
}
