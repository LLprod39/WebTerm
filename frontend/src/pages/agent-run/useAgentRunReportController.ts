import { useCallback, useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import {
  approvePipelinePlan,
  backendPath,
  cleanupStaleAgentRun,
  fetchAgentRunActivityV2,
  fetchAgentRunArtifactsV2,
  fetchAgentRunReport,
  fetchAgentRunReportEventsV2,
  fetchAgentRunReportV2,
  replyToAgent,
  retryAgentRunReportDelivery,
  stopAgent,
  type AgentRunActivityFilters,
  type AgentRunReportEventFilters,
  type AgentRunReportV2Response,
} from "@/lib/api";
import { pushRecentRun } from "@/lib/recent-entities";

import {
  createReportViewModel,
  isReportV2,
  type EvidenceView,
  type ReportSource,
  type ReportTabV2,
} from "./reportViewModel";

const validTabs = new Set<ReportTabV2>(["result", "execution", "evidence"]);
const validEvidenceViews = new Set<EvidenceView>(["activity", "events", "outputs", "artifacts", "document"]);

export type PreparedReportMutation = "stop" | "approve" | "cleanup" | "retry-delivery" | "reply";

export interface PreparedReportAction {
  kind: PreparedReportMutation;
  title: string;
  description: string;
  confirmLabel: string;
  destructive: boolean;
}

function isV2Unavailable(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || "");
  return /HTTP\s+(404|405)|not\s+found|не найден/i.test(message);
}

async function fetchReportWithLegacyFallback(runId: number): Promise<ReportSource> {
  try {
    const response = await fetchAgentRunReportV2(runId);
    if (isReportV2(response)) return response;
    return fetchAgentRunReport(runId);
  } catch (error) {
    if (isV2Unavailable(error)) return fetchAgentRunReport(runId);
    throw error;
  }
}

async function fetchDocumentText(path: string) {
  const response = await fetch(backendPath(path), { credentials: "include" });
  if (!response.ok) throw new Error(`Не удалось открыть полный отчёт: HTTP ${response.status}`);
  return response.text();
}

function readTab(value: string | null): ReportTabV2 {
  return value && validTabs.has(value as ReportTabV2) ? value as ReportTabV2 : "result";
}

function readEvidenceView(value: string | null): EvidenceView {
  return value && validEvidenceViews.has(value as EvidenceView) ? value as EvidenceView : "events";
}

function readList(value: string | null) {
  return value?.split(",").map((item) => item.trim()).filter(Boolean) || undefined;
}

export function useAgentRunReportController(runId: number) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [eventFilters, setEventFilters] = useState<AgentRunReportEventFilters>(() => ({
    limit: 50,
    direction: "older",
    q: searchParams.get("q") || undefined,
    severity: readList(searchParams.get("severity")),
    phase: readList(searchParams.get("phase")),
    category: readList(searchParams.get("category")),
    important: searchParams.has("important") ? searchParams.get("important") === "true" : undefined,
  }));
  const [activityFilters, setActivityFilters] = useState<AgentRunActivityFilters>(() => ({
    limit: 50,
    direction: "older",
    kind: readList(searchParams.get("kind")),
    status: readList(searchParams.get("status")),
  }));
  const [preparedAction, setPreparedAction] = useState<PreparedReportAction | null>(null);
  const [replyText, setReplyText] = useState("");
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const tab = readTab(searchParams.get("tab"));
  const evidenceView = readEvidenceView(searchParams.get("view"));
  const selectedEvidence = searchParams.get("evidence") || "";

  const reportQuery = useQuery({
    queryKey: ["agent-run-report-v2", runId],
    queryFn: () => fetchReportWithLegacyFallback(runId),
    enabled: runId > 0,
    retry: false,
    refetchInterval: (query) => {
      const raw = query.state.data;
      if (!raw) return false;
      const active = isReportV2(raw)
        ? raw.lifecycle.is_active
        : ["running", "pending", "paused", "waiting", "plan_review"].includes(raw.run.status);
      return active ? 2500 : false;
    },
  });

  const viewModel = useMemo(
    () => reportQuery.data ? createReportViewModel(reportQuery.data) : null,
    [reportQuery.data],
  );
  const isV2 = Boolean(reportQuery.data && isReportV2(reportQuery.data));

  useEffect(() => {
    if (viewModel?.run.id && viewModel.run.agentName) {
      pushRecentRun({ id: viewModel.run.id, agentName: viewModel.run.agentName });
    }
  }, [viewModel?.run.agentName, viewModel?.run.id]);

  const eventsQuery = useQuery({
    queryKey: ["agent-run-report-events-v2", runId, eventFilters],
    queryFn: () => fetchAgentRunReportEventsV2(runId, eventFilters),
    enabled: runId > 0 && isV2 && tab === "evidence" && evidenceView === "events",
    retry: false,
    placeholderData: keepPreviousData,
  });

  const needsActivity = tab === "execution" || (tab === "evidence" && ["activity", "outputs"].includes(evidenceView));
  const activityQuery = useQuery({
    queryKey: ["agent-run-activity-v2", runId, activityFilters],
    queryFn: () => fetchAgentRunActivityV2(runId, activityFilters),
    enabled: runId > 0 && isV2 && needsActivity,
    retry: false,
    placeholderData: keepPreviousData,
  });

  const artifactsQuery = useQuery({
    queryKey: ["agent-run-artifacts-v2", runId],
    queryFn: () => fetchAgentRunArtifactsV2(runId),
    enabled: runId > 0 && isV2 && tab === "evidence" && evidenceView === "artifacts",
    retry: false,
  });

  const documentPath = isV2
    ? (reportQuery.data as AgentRunReportV2Response | undefined)?.document?.detail_url || `/servers/api/agents/runs/${runId}/report/document/`
    : "";
  const documentQuery = useQuery({
    queryKey: ["agent-run-report-document", runId, documentPath],
    queryFn: () => fetchDocumentText(documentPath),
    enabled: Boolean(documentPath && tab === "evidence" && evidenceView === "document" && viewModel?.document.available),
    retry: false,
  });

  const setUrlState = useCallback((next: { tab?: ReportTabV2; view?: EvidenceView; evidence?: string | null }) => {
    const params = new URLSearchParams(searchParams);
    if (next.tab) params.set("tab", next.tab);
    if (next.view) params.set("view", next.view);
    if (next.evidence === null) params.delete("evidence");
    else if (next.evidence !== undefined) params.set("evidence", next.evidence);
    setSearchParams(params, { replace: true });
  }, [searchParams, setSearchParams]);

  const selectTab = useCallback((next: ReportTabV2) => setUrlState({ tab: next }), [setUrlState]);
  const selectEvidenceView = useCallback((next: EvidenceView) => setUrlState({ tab: "evidence", view: next, evidence: null }), [setUrlState]);
  const selectEvidence = useCallback((id: string | null) => setUrlState({ tab: "evidence", evidence: id }), [setUrlState]);

  const updateEventFilters = useCallback((patch: Partial<AgentRunReportEventFilters>) => {
    setEventFilters((current) => ({ ...current, ...patch, cursor: Object.hasOwn(patch, "cursor") ? patch.cursor : null }));
    const params = new URLSearchParams(searchParams);
    const next = { ...eventFilters, ...patch };
    const setList = (name: string, values?: string[]) => values?.length ? params.set(name, values.join(",")) : params.delete(name);
    if (next.q?.trim()) params.set("q", next.q.trim());
    else params.delete("q");
    setList("severity", next.severity);
    setList("phase", next.phase);
    setList("category", next.category);
    if (next.important === undefined) params.delete("important");
    else params.set("important", String(next.important));
    setSearchParams(params, { replace: true });
  }, [eventFilters, searchParams, setSearchParams]);

  const updateActivityFilters = useCallback((patch: Partial<AgentRunActivityFilters>) => {
    setActivityFilters((current) => ({ ...current, ...patch, cursor: Object.hasOwn(patch, "cursor") ? patch.cursor : null }));
    const params = new URLSearchParams(searchParams);
    const next = { ...activityFilters, ...patch };
    if (next.kind?.length) params.set("kind", next.kind.join(","));
    else params.delete("kind");
    if (next.status?.length) params.set("status", next.status.join(","));
    else params.delete("status");
    setSearchParams(params, { replace: true });
  }, [activityFilters, searchParams, setSearchParams]);

  const refresh = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["agent-run-report-v2", runId] }),
      queryClient.invalidateQueries({ queryKey: ["agent-run-report-events-v2", runId] }),
      queryClient.invalidateQueries({ queryKey: ["agent-run-activity-v2", runId] }),
      queryClient.invalidateQueries({ queryKey: ["agent-run-report-document", runId] }),
      queryClient.invalidateQueries({ queryKey: ["agent-run-artifacts-v2", runId] }),
      queryClient.invalidateQueries({ queryKey: ["agents"] }),
    ]);
  }, [queryClient, runId]);

  const prepare = useCallback((kind: PreparedReportMutation) => {
    setActionError(null);
    const actions: Record<PreparedReportMutation, PreparedReportAction> = {
      stop: { kind, title: "Остановить запуск?", description: "Агент прекратит текущую работу. Уже собранные доказательства останутся в отчёте.", confirmLabel: "Остановить", destructive: true },
      approve: { kind, title: "Подтвердить план?", description: "После подтверждения агент перейдёт к выполнению подготовленного плана.", confirmLabel: "Подтвердить", destructive: false },
      cleanup: { kind, title: "Снять зависший запуск?", description: "Будет очищен только этот запуск и связанные с ним зависшие dispatch-записи.", confirmLabel: "Снять зависший", destructive: true },
      "retry-delivery": { kind, title: "Повторить доставку?", description: "Сформированный отчёт будет повторно отправлен в настроенный канал.", confirmLabel: "Повторить", destructive: false },
      reply: { kind, title: "Отправить ответ агенту?", description: "Агент продолжит работу с этим ответом как с операторским вводом.", confirmLabel: "Отправить", destructive: false },
    };
    setPreparedAction(actions[kind]);
  }, []);

  const confirmPrepared = useCallback(async () => {
    if (!preparedAction || !viewModel) return;
    setActionPending(true);
    setActionError(null);
    setActionNotice(null);
    try {
      if (preparedAction.kind === "stop") await stopAgent(viewModel.run.agentId, viewModel.run.id);
      if (preparedAction.kind === "approve") await approvePipelinePlan(viewModel.run.id);
      if (preparedAction.kind === "cleanup") await cleanupStaleAgentRun(viewModel.run.id);
      if (preparedAction.kind === "retry-delivery") await retryAgentRunReportDelivery(viewModel.run.id);
      if (preparedAction.kind === "reply") {
        const answer = replyText.trim();
        if (!answer) throw new Error("Введите ответ для агента.");
        await replyToAgent(viewModel.run.id, answer);
        setReplyText("");
      }
      const notices: Record<PreparedReportMutation, string> = {
        stop: "Остановка запуска запрошена.",
        approve: "План подтверждён.",
        cleanup: "Зависший запуск очищен.",
        "retry-delivery": "Повторная доставка поставлена в очередь.",
        reply: "Ответ отправлен агенту.",
      };
      setActionNotice(notices[preparedAction.kind]);
      setPreparedAction(null);
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Действие не выполнено.");
    } finally {
      setActionPending(false);
    }
  }, [preparedAction, refresh, replyText, viewModel]);

  return {
    tab,
    evidenceView,
    selectedEvidence,
    selectTab,
    selectEvidenceView,
    selectEvidence,
    reportQuery,
    eventsQuery,
    activityQuery,
    artifactsQuery,
    documentQuery,
    viewModel,
    isV2,
    eventFilters,
    setEventFilters: updateEventFilters,
    activityFilters,
    setActivityFilters: updateActivityFilters,
    refresh,
    preparedAction,
    setPreparedAction,
    prepare,
    confirmPrepared,
    actionPending,
    actionError,
    actionNotice,
    replyText,
    setReplyText,
  };
}
