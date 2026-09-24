import { useEffect, useRef } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, CheckCircle2, FileCheck2, FolderArchive, ListOrdered, RefreshCw, Square } from "lucide-react";

import { ConfirmDialog } from "@/components/system/ConfirmDialog";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { AgentRunExecutionV2 } from "./agent-run/AgentRunExecutionV2";
import { AgentRunMaterialsV2 } from "./agent-run/AgentRunMaterialsV2";
import { AgentRunResultV2 } from "./agent-run/AgentRunResultV2";
import { OperatorHitlReply } from "./agent-run/OperatorHitlReply";
import { formatDuration } from "./agent-run/formatters";
import { useAgentRunReportController } from "./agent-run/useAgentRunReportController";

const tabItems = [
  { value: "report" as const, label: "Отчёт", icon: FileCheck2 },
  { value: "steps" as const, label: "Шаги", icon: ListOrdered },
  { value: "materials" as const, label: "Материалы", icon: FolderArchive },
];

function PageState({ title, description, loading = false, danger = false }: { title: string; description?: string; loading?: boolean; danger?: boolean }) {
  return (
    <div className="flex h-full min-h-[20rem] items-center justify-center p-6">
      <div role={danger ? "alert" : "status"} className={`max-w-md rounded-sm border p-5 text-center ${danger ? "border-destructive/35 bg-destructive/10" : "border-border bg-card"}`}>
        {loading ? <RefreshCw className="mx-auto mb-3 h-5 w-5 animate-spin text-muted-foreground" aria-hidden /> : null}
        <h1 className="font-display text-lg font-semibold text-foreground">{title}</h1>
        {description ? <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p> : null}
      </div>
    </div>
  );
}

function useOperatorQuestionNotification(question: string, runId: number, agentName: string) {
  const seenRef = useRef("");
  useEffect(() => {
    const key = `${runId}:${question}`;
    if (!question.trim() || seenRef.current === key) return;
    seenRef.current = key;
    if (typeof window === "undefined" || !("Notification" in window)) return;
    const title = agentName || `Запуск #${runId}`;
    const body = question.slice(0, 180);
    const show = () => {
      try {
        new Notification(title, { body, tag: `agent-hitl-${runId}` });
      } catch {
        /* ignore */
      }
    };
    if (Notification.permission === "granted") show();
    else if (Notification.permission === "default") {
      void Notification.requestPermission().then((perm) => {
        if (perm === "granted") show();
      });
    }
  }, [agentName, question, runId]);
}

export default function AgentRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const [searchParams] = useSearchParams();
  const rid = Number.parseInt(runId || "0", 10);
  const controller = useAgentRunReportController(rid);
  const viewModel = controller.viewModel;
  const focusReply = searchParams.get("focus") === "reply" || searchParams.get("reply") === "1";
  const pendingQuestion = String(viewModel?.run.pendingQuestion || "").trim();

  useOperatorQuestionNotification(pendingQuestion, rid, viewModel?.run.agentName || "");

  if (rid <= 0) return <PageState title="Некорректный номер запуска" danger />;
  if (controller.reportQuery.isLoading) return <PageState title="Загружаем отчёт…" loading />;
  if (controller.reportQuery.isError || !viewModel) {
    return <PageState title="Отчёт запуска недоступен" description={controller.reportQuery.error instanceof Error ? controller.reportQuery.error.message : "Запуск не найден."} danger />;
  }

  return (
    <div data-testid="agent-report-v2" data-agent-run-scroll className="h-full min-h-0 overflow-y-auto overflow-x-hidden bg-background [scrollbar-gutter:stable]">
      <header className="sticky top-0 z-20 border-b border-border bg-background">
        <div aria-hidden className="h-0.5 w-full bg-primary/90" />
        <div className="mx-auto w-full max-w-6xl px-4 py-3.5 sm:px-6">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Button variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-muted-foreground" asChild>
                  <Link to="/agents"><ArrowLeft className="h-3.5 w-3.5" aria-hidden />Агенты</Link>
                </Button>
                <span className="type-label text-muted-foreground">Отчёт · #{viewModel.run.id}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="font-display min-w-0 truncate text-xl font-bold tracking-tight text-foreground sm:text-2xl">{viewModel.header.title}</h1>
                <StatusBadge label={viewModel.header.statusLabel} tone={viewModel.header.statusTone} pulse={viewModel.header.pulse} />
              </div>
              {(() => {
                const meta = [
                  viewModel.run.serverName,
                  viewModel.run.durationMs > 0 ? formatDuration(viewModel.run.durationMs) : null,
                  viewModel.run.agentMode ? viewModel.run.agentMode.toUpperCase() : null,
                ].filter(Boolean);
                return meta.length ? <p className="mt-2 text-xs text-muted-foreground">{meta.join(" · ")}</p> : null;
              })()}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {viewModel.run.canApprove ? <Button size="sm" className="gap-1.5" onClick={() => controller.prepare("approve")}><CheckCircle2 className="h-4 w-4" aria-hidden />Подтвердить план</Button> : null}
              {viewModel.run.isActive || viewModel.run.canApprove ? <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => controller.prepare("stop")}><Square className="h-4 w-4" aria-hidden />Остановить</Button> : null}
              {viewModel.run.canCleanup ? <Button size="sm" variant="outline" className="gap-1.5" onClick={() => controller.prepare("cleanup")}><AlertTriangle className="h-4 w-4" aria-hidden />Снять зависший</Button> : null}
              <Button type="button" size="icon" variant="outline" className="h-9 w-9" aria-label="Обновить отчёт" onClick={() => void controller.refresh()}><RefreshCw className={`h-4 w-4 ${controller.reportQuery.isFetching ? "animate-spin" : ""}`} aria-hidden /></Button>
            </div>
          </div>
          <div aria-live="polite" className="mt-2 space-y-2">
            {controller.actionError ? <p role="alert" className="rounded-sm border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm text-destructive">{controller.actionError}</p> : null}
            {controller.actionNotice ? <p className="rounded-sm border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">{controller.actionNotice}</p> : null}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6">
        {pendingQuestion ? (
          <div className="sticky top-[4.5rem] z-10 mb-4">
            <OperatorHitlReply
              question={pendingQuestion}
              value={controller.replyText}
              onChange={controller.setReplyText}
              onSubmit={(answer) => controller.submitReply(answer)}
              submitting={controller.actionPending}
              autoFocus={Boolean(focusReply) || Boolean(pendingQuestion)}
            />
          </div>
        ) : null}

        <Tabs value={controller.tab} onValueChange={(value) => controller.selectTab(value as typeof controller.tab)} className="space-y-4">
          <TabsList aria-label="Разделы отчёта" className="grid h-auto w-full grid-cols-3 gap-1 rounded-sm border border-border bg-surface-0 p-1 sm:flex sm:w-fit sm:justify-start">
            {tabItems.map((item) => {
              const Icon = item.icon;
              return (
                <TabsTrigger key={item.value} value={item.value} className="min-h-11 min-w-0 gap-1.5 px-2 sm:px-4">
                  <Icon className="hidden h-4 w-4 sm:block" aria-hidden />
                  <span className="truncate">{item.label}</span>
                </TabsTrigger>
              );
            })}
          </TabsList>
          <TabsContent value="report" className="mt-0">
            <AgentRunResultV2
              viewModel={viewModel}
              prepare={controller.prepare}
              documentText={controller.documentQuery.data}
              documentLoading={controller.documentQuery.isLoading}
              documentError={controller.documentQuery.error}
            />
          </TabsContent>
          <TabsContent value="steps" className="mt-0">
            <AgentRunExecutionV2
              viewModel={viewModel}
              response={controller.activityQuery.data}
              loading={controller.activityQuery.isLoading}
              error={controller.activityQuery.error}
              filters={controller.activityFilters}
              setFilters={controller.setActivityFilters}
            />
          </TabsContent>
          <TabsContent value="materials" className="mt-0">
            <AgentRunMaterialsV2
              viewModel={viewModel}
              view={controller.materialsView}
              onViewChange={controller.selectMaterialsView}
              selected={controller.selectedEvidence}
              onSelect={controller.selectEvidence}
              eventsResponse={controller.eventsQuery.data}
              eventsLoading={controller.eventsQuery.isLoading}
              eventsError={controller.eventsQuery.error}
              eventFilters={controller.eventFilters}
              setEventFilters={controller.setEventFilters}
              artifactsResponse={controller.artifactsQuery.data}
              artifactsLoading={controller.artifactsQuery.isLoading}
              artifactsError={controller.artifactsQuery.error}
            />
          </TabsContent>
        </Tabs>
      </main>

      <ConfirmDialog open={Boolean(controller.preparedAction)} onOpenChange={(open) => { if (!open && !controller.actionPending) controller.setPreparedAction(null); }} title={controller.preparedAction?.title || "Подтвердить действие"} description={controller.preparedAction?.description || "Проверьте действие перед выполнением."} confirmLabel={controller.actionPending ? "Выполняем…" : controller.preparedAction?.confirmLabel || "Подтвердить"} cancelLabel="Отмена" tone={controller.preparedAction?.destructive ? "destructive" : "default"} onConfirm={() => void controller.confirmPrepared()} />
    </div>
  );
}
