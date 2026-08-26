import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BrainCircuit,
  CheckCircle2,
  Copy,
  Download,
  FileCode2,
  Loader2,
  Search,
  Square,
  Terminal,
  XCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHero, PageShell, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getMarsRunWsUrl, marsApi, type MarsRunEvent } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { statusLabel } from "./mars/MarsPageUtils";

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
    .map((line) => line.replace(/^[A-Z?]{1,2}\s+/, "").trim())
    .filter(Boolean);
}

function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function MarsRunPage() {
  const { runId } = useParams();
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const numericRunId = Number(runId);
  const [liveEvents, setLiveEvents] = useState<MarsRunEvent[]>([]);
  const [logSearch, setLogSearch] = useState("");

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
  const filteredCliLines = useMemo(() => {
    const query = logSearch.trim().toLowerCase();
    if (!query) return cliLines;
    return cliLines.filter((line) => line.toLowerCase().includes(query));
  }, [cliLines, logSearch]);
  const logText = filteredCliLines.length
    ? filteredCliLines.join("\n")
    : localize(lang, "Вывод команд появится здесь.", "Command output will appear here.");
  const checklist = [
    { label: localize(lang, "Подготовка", "Setup"), done: events.some((event) => event.event_type === "mars_run_started") },
    { label: localize(lang, "Создание", "Build"), done: events.some((event) => event.event_type === "codex_finished") || Boolean(run?.codex_summary) },
    { label: localize(lang, "Проверка", "Verification"), done: events.some((event) => event.event_type.startsWith("tests_")) || Boolean(run?.test_output) },
    { label: localize(lang, "Качество", "Quality"), done: events.some((event) => event.event_type === "gemini_finished") || Boolean(run?.gemini_review) },
    { label: localize(lang, "Итоговый отчет", "Final report"), done: Boolean(run?.final_report) },
  ];
  const progress = Math.round((checklist.filter((item) => item.done).length / checklist.length) * 100);
  const canStop = run?.status === "queued" || run?.status === "running";
  const recentEvents = events.filter((event) => !isCliEvent(event)).slice(-40);

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
            <StatusBadge label={runQuery.isLoading ? localize(lang, "Загрузка", "Loading") : statusLabel(run?.status, lang)} tone={runTone(run?.status)} />
            <Button variant="outline" onClick={() => stopRun.mutate()} disabled={!canStop || stopRun.isPending}>
              {stopRun.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
              {localize(lang, "Остановить", "Stop")}
            </Button>
          </div>
        }
      />

      <QueryStateBlock loading={runQuery.isLoading} error={runQuery.error}>
        <div className="space-y-5">
          <SectionCard
            title={localize(lang, "Обзор", "Overview")}
            icon={<BrainCircuit className="h-4 w-4" />}
          >
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-border/80 bg-secondary/20 px-3 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{localize(lang, "Статус", "Status")}</div>
                  <div className="mt-2 text-sm font-semibold text-foreground">{runQuery.isLoading ? localize(lang, "Загрузка", "Loading") : statusLabel(run?.status, lang)}</div>
                </div>
                <div className="rounded-lg border border-border/80 bg-secondary/20 px-3 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{localize(lang, "Изменения", "Changes")}</div>
                  <div className="mt-2 text-sm font-semibold text-foreground">{changedFiles.length}</div>
                </div>
                <div className="rounded-lg border border-border/80 bg-secondary/20 px-3 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{localize(lang, "Проверки", "Checks")}</div>
                  <div className="mt-2 text-sm font-semibold text-foreground">{run?.test_output ? localize(lang, "Завершены", "Completed") : localize(lang, "Ожидаются", "Pending")}</div>
                </div>
              </div>

              <Progress value={progress} />
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                {checklist.map((item) => (
                  <div key={item.label} className="flex min-h-12 items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm">
                    {item.done ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-muted-foreground/50" />}
                    <span className="truncate">{item.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </SectionCard>

          <Tabs defaultValue="progress" className="space-y-3">
            <TabsList className="flex h-auto w-full justify-start overflow-x-auto">
              <TabsTrigger value="progress">{localize(lang, "Ход работы", "Progress")}</TabsTrigger>
              <TabsTrigger value="logs">{localize(lang, "Логи", "Logs")}</TabsTrigger>
              <TabsTrigger value="changes">{localize(lang, "Изменения", "Changes")}</TabsTrigger>
              <TabsTrigger value="report">{localize(lang, "Отчет", "Report")}</TabsTrigger>
            </TabsList>

            <TabsContent value="progress">
              <SectionCard
                title={localize(lang, "Ход работы", "Progress")}
                icon={<BrainCircuit className="h-4 w-4" />}
              >
                <div className="space-y-2">
                  {recentEvents.map((event) => (
                    <div key={event.id} className="rounded-lg border border-border bg-secondary/15 px-3 py-2">
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-xs font-semibold text-foreground">{publicEventLabel(event.event_type, lang)}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">{event.created_at ? new Date(event.created_at).toLocaleTimeString() : ""}</span>
                      </div>
                      {event.message ? <div className="mt-1 text-xs leading-5 text-muted-foreground">{publicEventMessage(event, lang)}</div> : null}
                    </div>
                  ))}
                  {recentEvents.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                      {localize(lang, "Событий пока нет.", "No events yet.")}
                    </div>
                  ) : null}
                </div>
              </SectionCard>
            </TabsContent>

            <TabsContent value="logs">
              <SectionCard
                title={localize(lang, "Журнал выполнения", "Execution log")}
                icon={<Terminal className="h-4 w-4" />}
                actions={
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        value={logSearch}
                        onChange={(event) => setLogSearch(event.target.value)}
                        placeholder={localize(lang, "Поиск в логах", "Search logs")}
                        className="h-8 w-44 bg-background pl-8 text-xs"
                      />
                    </div>
                    <Button variant="outline" size="sm" onClick={() => void navigator.clipboard?.writeText(logText)}>
                      <Copy className="h-3.5 w-3.5" />
                      {localize(lang, "Копировать", "Copy")}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => downloadText(`mars-run-${numericRunId}.log`, logText)}>
                      <Download className="h-3.5 w-3.5" />
                      {localize(lang, "Скачать", "Download")}
                    </Button>
                  </div>
                }
              >
                <pre className="max-h-[560px] overflow-auto rounded-lg bg-background p-4 text-xs leading-5 text-foreground">
                  {logText}
                </pre>
              </SectionCard>
            </TabsContent>

            <TabsContent value="changes">
              <div className="grid gap-5 xl:grid-cols-2">
                <SectionCard title={localize(lang, "Измененные файлы", "Changed files")} icon={<FileCode2 className="h-4 w-4" />}>
                  <div className="space-y-2">
                    {changedFiles.length ? (
                      changedFiles.map((file) => (
                        <div key={file} className="truncate rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs">
                          {file}
                        </div>
                      ))
                    ) : (
                      <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                        {localize(lang, "Нет изменённых файлов.", "No changed files.")}
                      </div>
                    )}
                  </div>
                </SectionCard>

                <SectionCard title={localize(lang, "Проверки", "Checks")} icon={<Terminal className="h-4 w-4" />}>
                  <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/20 p-4 text-xs leading-5 text-foreground">
                    {run?.test_output || localize(lang, "Команда проверки не запускалась.", "No verification command was run.")}
                  </pre>
                </SectionCard>
              </div>
            </TabsContent>

            <TabsContent value="report">
              <div className="grid gap-5 xl:grid-cols-2">
                <SectionCard title={localize(lang, "Результат выполнения", "Run result")} icon={<BrainCircuit className="h-4 w-4" />}>
                  <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/20 p-4 text-xs leading-5 text-foreground">
                    {run?.codex_summary || localize(lang, "Результат пока пуст.", "No result yet.")}
                  </pre>
                </SectionCard>
                <SectionCard title={localize(lang, "Проверка качества", "Quality check")} icon={<BrainCircuit className="h-4 w-4" />}>
                  <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/20 p-4 text-xs leading-5 text-foreground">
                    {run?.gemini_review || localize(lang, "Проверка качества еще не готова.", "Quality review is not ready yet.")}
                  </pre>
                </SectionCard>
                <SectionCard title={localize(lang, "Итоговый отчет", "Final report")} icon={<CheckCircle2 className="h-4 w-4" />} className="xl:col-span-2">
                  <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/20 p-4 text-xs leading-5 text-foreground">
                    {run?.final_report || localize(lang, "Итоговый отчет появится после завершения.", "Final report appears after completion.")}
                  </pre>
                </SectionCard>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </QueryStateBlock>
    </PageShell>
  );
}
