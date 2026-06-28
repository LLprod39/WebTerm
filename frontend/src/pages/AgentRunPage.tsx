import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, CheckCircle2, FileText, FolderArchive, List, RefreshCw, Square, Terminal, Workflow } from "lucide-react";

import {
  approvePipelinePlan,
  cleanupStaleAgentRuns,
  fetchAgentRunReport,
  replyToAgent,
  retryAgentRunReportDelivery,
  stopAgent,
} from "@/lib/api";
import { agentRunStatusPresentation } from "@/design/status";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/lib/i18n";

import { AgentStepsTab } from "./agent-run/AgentRunStepsTab";
import { ArtifactsTab, LogsTab } from "./agent-run/AgentRunLogsArtifactsTabs";
import { EventsTab } from "./agent-run/AgentRunEventsTab";
import {
  LiveRunBanner,
  PendingQuestionPanel,
  ReportMetricCards,
  StateBlock,
} from "./agent-run/AgentRunCommonPanels";
import { OverviewTab } from "./agent-run/AgentRunOverviewTab";
import { primaryOutcomeSummary, severityLabel, severityTone, type ReportTab } from "./agent-run/reportShared";


const tabItems: Array<{ value: ReportTab; label: string; icon: LucideIcon }> = [
  { value: "overview", label: "Обзор", icon: FileText },
  { value: "events", label: "События", icon: List },
  { value: "logs", label: "Логи", icon: Terminal },
  { value: "artifacts", label: "Артефакты", icon: FolderArchive },
  { value: "agent", label: "Ход агента", icon: Workflow },
];


export default function AgentRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const rid = parseInt(runId || "0", 10);
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ReportTab>("overview");
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
      return status && ["running", "pending", "paused", "waiting", "plan_review"].includes(status) ? 2500 : false;
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
      setActionNotice(`Очищено stale-запусков: ${response.cleanup.cleaned}; отменено dispatch: ${response.cleanup.canceled_dispatches}.`);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не удалось очистить stale-запуск.");
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
      setActionError(err instanceof Error ? err.message : "Не удалось повторить доставку отчёта.");
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
      setActionError(err instanceof Error ? err.message : "Не удалось отправить ответ агенту.");
    } finally {
      setReplying(false);
    }
  };

  const copyText = async (value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard?.writeText(value);
      setActionNotice("Скопировано.");
      setActionError(null);
    } catch {
      setActionNotice(null);
      setActionError(value);
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

  const status = agentRunStatusPresentation(run.status);

  return (
    <div
      data-agent-run-scroll
      className="h-full min-h-0 overflow-y-auto overflow-x-hidden bg-background [scrollbar-gutter:stable]"
    >
      <header className="sticky top-0 z-20 border-b border-border/70 bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-3 px-4 py-3 sm:px-6 2xl:px-8">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="truncate text-2xl font-semibold tracking-[-0.02em] text-foreground sm:text-3xl">
                  {data.report.title || run.agent_name}
                </h1>
                <StatusBadge label={t(status.labelKey)} tone={status.tone} pulse={status.pulse} />
                <StatusBadge
                  label={severityLabel[data.report.severity] || data.report.severity}
                  tone={severityTone[data.report.severity] || "neutral"}
                />
              </div>
              <p className="mt-1 max-w-4xl text-sm leading-6 text-muted-foreground">{primaryOutcomeSummary(data)}</p>
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
              {data.report_state?.execution_state?.can_cleanup ? (
                <Button size="sm" variant="outline" className="h-9 gap-1.5 border-amber-500/30 text-amber-200 hover:text-amber-100" onClick={onCleanupStale} disabled={cleaningStale}>
                  {cleaningStale ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                  {cleaningStale ? "Очищаем" : "Очистить stale"}
                </Button>
              ) : null}
              <Button size="icon" variant="outline" className="h-9 w-9" onClick={() => void refresh()} aria-label={t("udash.refresh")}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {actionError ? <div className="text-sm text-destructive">{actionError}</div> : null}
          {actionNotice ? <div className="text-sm text-emerald-300">{actionNotice}</div> : null}
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1680px] flex-col gap-4 px-4 py-5 sm:px-6 2xl:px-8">
        <ReportMetricCards report={data} />
        <PendingQuestionPanel
          report={data}
          answer={replyText}
          submitting={replying}
          onAnswerChange={setReplyText}
          onSubmit={onReply}
        />
        <LiveRunBanner
          report={data}
          onOpenTab={setActiveTab}
          onCleanupStale={onCleanupStale}
          cleaningStale={cleaningStale}
          onCopyText={copyText}
        />

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as ReportTab)} className="space-y-4">
          <TabsContent value="overview">
            <OverviewTab report={data} onRetryDelivery={onRetryDelivery} retryingDelivery={retryingDelivery} />
          </TabsContent>
          <TabsContent value="events">
            <EventsTab report={data} />
          </TabsContent>
          <TabsContent value="logs">
            <LogsTab report={data} logs={data.logs} />
          </TabsContent>
          <TabsContent value="artifacts">
            <ArtifactsTab report={data} />
          </TabsContent>
          <TabsContent value="agent">
            <AgentStepsTab report={data} steps={data.agent_steps} />
          </TabsContent>

          <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto p-1.5 sm:w-auto">
            {tabItems.map((item) => {
              const Icon = item.icon;
              return (
                <TabsTrigger key={item.value} value={item.value} className="h-10 gap-2 px-3 text-sm">
                  <Icon className="h-4 w-4" />
                  {item.label}
                </TabsTrigger>
              );
            })}
          </TabsList>
        </Tabs>
      </main>
    </div>
  );
}
