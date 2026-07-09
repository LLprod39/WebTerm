import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  FileText,
  FolderOpen,
  RefreshCw,
  Square,
  Workflow,
} from "lucide-react";

import {
  approvePipelinePlan,
  cleanupStaleAgentRuns,
  fetchAgentRunReport,
  replyToAgent,
  retryAgentRunReportDelivery,
  stopAgent,
} from "@/lib/api";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { AgentStepsTab } from "./agent-run/AgentRunStepsTab";
import {
  PendingQuestionPanel,
  StateBlock,
} from "./agent-run/AgentRunCommonPanels";
import { MaterialsTab } from "./agent-run/AgentRunMaterialsTab";
import { OverviewTab } from "./agent-run/AgentRunOverviewTab";
import {
  primaryOutcomeSummary,
  unifiedRunStatus,
  type ReportTab,
} from "./agent-run/reportShared";
import { formatDuration } from "./agent-run/formatters";

const tabItems: Array<{ value: ReportTab; label: string; hint: string; icon: LucideIcon }> = [
  { value: "summary", label: "Итог", hint: "Что случилось", icon: FileText },
  { value: "progress", label: "Ход", hint: "Шаги агента", icon: Workflow },
  { value: "materials", label: "Материалы", hint: "Логи и файлы", icon: FolderOpen },
];

/**
 * Agent run report — simplified IA:
 * 1. One status + one-liner
 * 2. HITL first if waiting
 * 3. Three zones: Итог · Ход · Материалы
 */
export default function AgentRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const rid = parseInt(runId || "0", 10);
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ReportTab>("summary");
  const [stopping, setStopping] = useState(false);
  const [approving, setApproving] = useState(false);
  const [cleaningStale, setCleaningStale] = useState(false);
  const [retryingDelivery, setRetryingDelivery] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [replying, setReplying] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["agent-run-report", rid],
    queryFn: () => fetchAgentRunReport(rid),
    enabled: rid > 0,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.run?.status;
      return status && ["running", "pending", "paused", "waiting", "plan_review"].includes(status)
        ? 2500
        : false;
    },
  });

  const run = data?.run;
  const isActive = Boolean(run && ["running", "pending", "paused", "waiting"].includes(run.status));
  const isPlanReview = run?.status === "plan_review";

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["agent-run-report", rid] });
    await queryClient.invalidateQueries({ queryKey: ["agents"] });
  };

  const onStop = async () => {
    if (!run) return;
    setStopping(true);
    setActionError(null);
    setActionNotice(null);
    try {
      await stopAgent(run.agent_id, run.id);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Stop failed");
    } finally {
      setStopping(false);
    }
  };

  const onApprove = async () => {
    if (!run) return;
    setApproving(true);
    setActionError(null);
    setActionNotice(null);
    try {
      await approvePipelinePlan(run.id);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : t("run.approve_error"));
    } finally {
      setApproving(false);
    }
  };

  const onCleanupStale = async () => {
    setCleaningStale(true);
    setActionError(null);
    setActionNotice(null);
    try {
      const response = await cleanupStaleAgentRuns({ limit: 50 });
      setActionNotice(
        `Очищено зависших запусков: ${response.cleanup.cleaned}.`,
      );
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не удалось очистить зависший запуск.");
    } finally {
      setCleaningStale(false);
    }
  };

  const onRetryDelivery = async () => {
    if (!run) return;
    setRetryingDelivery(true);
    setActionError(null);
    setActionNotice(null);
    try {
      await retryAgentRunReportDelivery(run.id);
      setActionNotice("Доставка отчёта запущена повторно.");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не удалось повторить доставку.");
    } finally {
      setRetryingDelivery(false);
    }
  };

  const onReply = async () => {
    if (!run) return;
    const answer = replyText.trim();
    if (!answer) {
      setActionNotice(null);
      setActionError("Введите ответ для агента.");
      return;
    }
    setReplying(true);
    setActionError(null);
    setActionNotice(null);
    try {
      await replyToAgent(run.id, answer);
      setReplyText("");
      setActionNotice("Ответ отправлен агенту.");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не удалось отправить ответ.");
    } finally {
      setReplying(false);
    }
  };

  if (rid <= 0) {
    return <StateBlock title={t("run.invalid_id")} />;
  }

  if (isLoading) {
    return <StateBlock title={t("loading")} icon={<RefreshCw className="h-4 w-4 animate-spin" />} />;
  }

  if (isError || !data || !run) {
    const message = error instanceof Error ? error.message : t("run.not_found");
    return <StateBlock title={t("run.not_found_title")} description={message} danger />;
  }

  const outcome = unifiedRunStatus(data);
  const oneLiner = primaryOutcomeSummary(data);
  const canCleanup = Boolean(data.report_state?.execution_state?.can_cleanup);

  return (
    <div
      data-agent-run-scroll
      className="h-full min-h-0 overflow-y-auto overflow-x-hidden bg-background [scrollbar-gutter:stable]"
    >
      <header className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 py-3 sm:px-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Button variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-muted-foreground" asChild>
                  <Link to="/agents">
                    <ArrowLeft className="h-3.5 w-3.5" />
                    Агенты
                  </Link>
                </Button>
                <span className="font-mono text-2xs text-muted-foreground">#{run.id}</span>
              </div>

              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="font-display truncate text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                  {data.report.title || run.agent_name}
                </h1>
                <StatusBadge label={outcome.label} tone={outcome.tone} pulse={outcome.pulse} />
              </div>

              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{oneLiner}</p>

              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-2xs text-muted-foreground">
                {(data.report.meta.server || run.server_name) ? (
                  <span>Сервер: <span className="text-foreground/80">{data.report.meta.server || run.server_name}</span></span>
                ) : null}
                {run.duration_ms > 0 ? (
                  <span>Время: <span className="text-foreground/80">{formatDuration(run.duration_ms)}</span></span>
                ) : null}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {isPlanReview ? (
                <Button size="sm" className="h-9 gap-1.5" onClick={onApprove} disabled={approving}>
                  {approving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                  {approving ? t("run.approving") : t("run.approve")}
                </Button>
              ) : null}
              {isActive || isPlanReview ? (
                <Button size="sm" variant="destructive" className="h-9 gap-1.5" onClick={onStop} disabled={stopping}>
                  {stopping ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
                  {t("agent.stop")}
                </Button>
              ) : null}
              {canCleanup ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-9 gap-1.5"
                  onClick={onCleanupStale}
                  disabled={cleaningStale}
                >
                  {cleaningStale ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                  {cleaningStale ? "Очищаем…" : "Снять зависший"}
                </Button>
              ) : null}
              <Button
                size="icon"
                variant="outline"
                className="h-9 w-9"
                onClick={() => void refresh()}
                aria-label={t("udash.refresh")}
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {actionError ? <div className="text-sm text-destructive">{actionError}</div> : null}
          {actionNotice ? <div className="text-sm text-success">{actionNotice}</div> : null}
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-5 sm:px-6">
        {/* HITL dominates when waiting */}
        <PendingQuestionPanel
          report={data}
          answer={replyText}
          submitting={replying}
          onAnswerChange={setReplyText}
          onSubmit={onReply}
        />

        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as ReportTab)}
          className="space-y-4"
        >
          <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-sm border border-border bg-surface-0 p-1 sm:w-auto">
            {tabItems.map((item) => {
              const Icon = item.icon;
              return (
                <TabsTrigger
                  key={item.value}
                  value={item.value}
                  className={cn(
                    "h-10 gap-2 rounded-sm px-3.5 text-sm data-[state=active]:shadow-none",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="flex flex-col items-start leading-none">
                    <span>{item.label}</span>
                    <span className="mt-0.5 hidden text-2xs font-normal opacity-70 sm:block">
                      {item.hint}
                    </span>
                  </span>
                </TabsTrigger>
              );
            })}
          </TabsList>

          <TabsContent value="summary" className="mt-0 outline-none">
            <OverviewTab
              report={data}
              onRetryDelivery={onRetryDelivery}
              retryingDelivery={retryingDelivery}
              onOpenProgress={() => setActiveTab("progress")}
              onOpenMaterials={() => setActiveTab("materials")}
            />
          </TabsContent>

          <TabsContent value="progress" className="mt-0 outline-none">
            <AgentStepsTab report={data} steps={data.agent_steps} />
          </TabsContent>

          <TabsContent value="materials" className="mt-0 outline-none">
            <MaterialsTab report={data} />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
