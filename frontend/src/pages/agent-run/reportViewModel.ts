import type {
  AgentRunActivityV2Item,
  AgentRunReportRecommendation,
  AgentRunReportArtifact,
  AgentRunReportEvent,
  AgentRunReportFinding,
  AgentRunReportLog,
  AgentRunReportResponse,
  AgentRunReportSeverity,
  AgentRunReportStep,
  AgentRunReportV2Action,
  AgentRunReportV2EvidenceRef,
  AgentRunReportV2Finding,
  AgentRunReportV2Phase,
  AgentRunReportV2Response,
  AgentRunReportV2Severity,
} from "@/lib/api";
import type { StatusTone } from "@/design/status";

export type ReportSource = AgentRunReportV2Response | AgentRunReportResponse;
export type ReportTabV2 = "result" | "execution" | "evidence";
export type EvidenceView = "activity" | "events" | "outputs" | "artifacts" | "document";

export interface ReportStateAxis {
  id: "lifecycle" | "outcome" | "evidence" | "generation" | "delivery";
  label: string;
  value: string;
  detail: string;
  tone: StatusTone;
  pulse?: boolean;
}

export interface ReportIndicatorViewModel {
  id: string;
  label: string;
  value: string;
  hint: string;
  tone: StatusTone;
  role: string;
  valueKind: string;
  unit: string;
  numerator: number | null;
  denominator: number | null;
  priority: number;
  evidenceRefs: string[];
}

export interface ReportEvidenceLinkViewModel {
  id: string;
  kind: string;
  label: string;
  summary: string;
  view: EvidenceView;
  href: string;
  targetId: string;
  occurredAt: string | null;
  downloadUrl: string;
  contentType: string;
  sizeBytes: number;
  truncated: boolean;
}

export interface ReportFindingViewModel {
  id: string;
  title: string;
  summary: string;
  details: string;
  severity: AgentRunReportSeverity;
  tone: StatusTone;
  confidence: string;
  scope: string;
  source: string;
  evidence: ReportEvidenceLinkViewModel[];
}

export interface ReportActionViewModel {
  id: string;
  title: string;
  summary: string;
  details: string;
  priority: string;
  status: string;
  owner: string;
  cta: {
    kind: string;
    label: string;
    target: string;
    enabled: boolean;
    isMutation: boolean;
    requiresConfirmation: boolean;
  };
  evidence: ReportEvidenceLinkViewModel[];
}

export interface ReportPhaseItemViewModel {
  id: string;
  title: string;
  summary: string;
  status: string;
  tone: StatusTone;
  kind: string;
  raw: string;
  evidence: ReportEvidenceLinkViewModel[];
  startedAt: string | null;
  completedAt: string | null;
}

export interface ReportPhaseViewModel {
  id: "goal" | "action" | "observation" | "conclusion" | string;
  label: string;
  status: string;
  tone: StatusTone;
  summary: string;
  items: ReportPhaseItemViewModel[];
}

export interface ReportDocumentViewModel {
  available: boolean;
  title: string;
  contentType: string;
  sizeBytes: number;
  checksum: string;
  preview: string;
  previewTruncated: boolean;
  downloadUrl: string;
}

export interface ReportViewModel {
  sourceVersion: "v2" | "legacy";
  run: {
    id: number;
    agentId: number;
    agentName: string;
    agentType: string;
    agentMode: string;
    serverId: number | null;
    serverName: string;
    lifecycleStatus: string;
    isActive: boolean;
    isTerminal: boolean;
    canCleanup: boolean;
    canApprove: boolean;
    pendingQuestion: string;
    startedAt: string | null;
    completedAt: string | null;
    durationMs: number;
  };
  header: {
    title: string;
    summary: string;
    statusLabel: string;
    statusTone: StatusTone;
    pulse: boolean;
  };
  axes: ReportStateAxis[];
  indicators: ReportIndicatorViewModel[];
  findings: ReportFindingViewModel[];
  actions: ReportActionViewModel[];
  phases: ReportPhaseViewModel[];
  evidenceLinks: ReportEvidenceLinkViewModel[];
  evidenceEndpoints: {
    events: string;
    activity: string;
    artifacts: string;
    auditExport: string;
  };
  counts: {
    events: number;
    importantEvents: number;
    problems: number;
    activities: number;
    processedActivities: number;
    failedActivities: number;
    artifacts: number;
  };
  delivery: {
    enabled: boolean;
    channel: string;
    status: string;
    label: string;
    summary: string;
    target: string;
    tone: StatusTone;
    canRetry: boolean;
    blockedReason: string;
    nextAction: string;
    setupUrl: string;
  };
  document: ReportDocumentViewModel;
  provenance: {
    source: string;
    revision: string;
    generatedAt: string | null;
    checksum: string;
    eventWatermark: string;
  };
  embedded: {
    events: AgentRunReportEvent[];
    activity: AgentRunActivityV2Item[];
    artifacts: AgentRunReportArtifact[];
  };
}

const phaseLabels: Record<string, string> = {
  goal: "Цель",
  action: "Действия",
  observation: "Наблюдения",
  conclusion: "Вывод",
};

const severityOrder: Record<string, number> = {
  fatal: 6,
  critical: 5,
  high: 4,
  warning: 3,
  info: 2,
  success: 1,
};

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value.trim() : value == null ? fallback : String(value);
}

function numberOrNull(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function reportTone(value: unknown): StatusTone {
  const normalized = text(value).toLowerCase();
  if (["fatal", "critical", "danger", "error", "failed", "blocked"].includes(normalized)) return "danger";
  if (["high", "warning", "warn", "partial", "waiting", "plan_review", "ready_with_fallback", "ready_with_warnings"].includes(normalized)) return "warning";
  if (["success", "ok", "ready", "completed", "delivered", "succeeded"].includes(normalized)) return "success";
  if (["info", "running", "active", "executing", "pending"].includes(normalized)) return "info";
  return "neutral";
}

export function isReportV2(value: unknown): value is AgentRunReportV2Response {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<AgentRunReportV2Response>;
  return Boolean(candidate.run && candidate.lifecycle && candidate.outcome && candidate.evidence_state);
}

function evidenceView(kind: string): EvidenceView {
  const normalized = kind.toLowerCase();
  if (normalized.includes("artifact") || normalized.includes("file")) return "artifacts";
  if (normalized.includes("document") || normalized.includes("report")) return "document";
  if (normalized.includes("event") || normalized.includes("signal")) return "events";
  if (normalized.includes("output") || normalized.includes("log") || normalized.includes("command")) return "outputs";
  return "activity";
}

function evidenceLink(runId: number, item: AgentRunReportV2EvidenceRef): ReportEvidenceLinkViewModel {
  const view = evidenceView(text(item.kind));
  const id = text(item.ref, `${view}-evidence`);
  const href = `/agents/run/${runId}?tab=evidence&view=${view}&evidence=${encodeURIComponent(id)}`;
  return {
    id,
    kind: text(item.kind, view),
    label: text(item.label, "Доказательство"),
    summary: "",
    view,
    href,
    targetId: id,
    occurredAt: null,
    downloadUrl: "",
    contentType: "",
    sizeBytes: 0,
    truncated: false,
  };
}

function normalizeRefs(runId: number, refs: unknown): ReportEvidenceLinkViewModel[] {
  if (!Array.isArray(refs)) return [];
  return refs.flatMap((ref) => {
    if (ref && typeof ref === "object") return [evidenceLink(runId, ref as AgentRunReportV2EvidenceRef)];
    const id = text(ref);
    if (!id) return [];
    return [evidenceLink(runId, { kind: "activity", ref: id, label: id, href: "" })];
  });
}

function v2Finding(runId: number, item: AgentRunReportV2Finding): ReportFindingViewModel {
  return {
    id: text(item.id),
    title: text(item.title, "Наблюдение"),
    summary: text(item.description),
    details: "",
    severity: item.severity,
    tone: reportTone(item.severity),
    confidence: text(item.confidence),
    scope: text(item.scope),
    source: text(item.confidence),
    evidence: normalizeRefs(runId, item.evidence_refs),
  };
}

function v2Action(runId: number, item: AgentRunReportV2Action): ReportActionViewModel {
  const cta = item.cta;
  return {
    id: text(item.id),
    title: text(item.title, "Следующий шаг"),
    summary: text(item.description),
    details: "",
    priority: text(item.priority),
    status: text(item.status),
    owner: text(item.owner),
    cta: {
      kind: text(cta?.type),
      label: text(cta?.label),
      target: text(cta?.href || cta?.ref),
      enabled: Boolean(cta?.enabled),
      isMutation: item.safety === "review_required" || cta?.type === "retry_delivery",
      requiresConfirmation: item.safety === "review_required" || cta?.type === "retry_delivery",
    },
    evidence: normalizeRefs(runId, item.evidence_refs),
  };
}

function v2Phase(phase: AgentRunReportV2Phase): ReportPhaseViewModel {
  const id = text(phase.id, "action");
  const fallbackSummary = phase.count ? `${phase.count} элементов · важных ${phase.important} · проблем ${phase.problems}` : "Нет записей";
  return {
    id,
    label: text(phase.label, phaseLabels[id] || id),
    status: text(phase.status),
    tone: reportTone(phase.status),
    summary: text(phase.summary || phase.goal || phase.action || phase.observation || phase.conclusion, fallbackSummary),
    items: [],
  };
}

function presentationPhaseId(id: string, index: number, total: number): "goal" | "action" | "observation" | "conclusion" {
  const normalized = id.toLowerCase();
  if (/goal|plan|queue|start/.test(normalized)) return "goal";
  if (/action|execut|tool|activity|step|iteration/.test(normalized)) return "action";
  if (/observ|synth|evidence|deliver|waiting/.test(normalized)) return "observation";
  if (/conclusion|ready|complete|failed|stopped|report/.test(normalized)) return "conclusion";
  const bucket = Math.min(3, Math.floor((index * 4) / Math.max(total, 1)));
  return (["goal", "action", "observation", "conclusion"] as const)[bucket];
}

function presentationPhases(phases: AgentRunReportV2Phase[]): ReportPhaseViewModel[] {
  const ids = ["goal", "action", "observation", "conclusion"] as const;
  return ids.map((id) => {
    const members = phases.filter((phase, index) => presentationPhaseId(phase.id, index, phases.length) === id);
    const problems = members.reduce((sum, phase) => sum + (phase.problems || 0), 0);
    const important = members.reduce((sum, phase) => sum + (phase.important || 0), 0);
    const count = members.reduce((sum, phase) => sum + (phase.count || 0), 0);
    const active = members.some((phase) => phase.status === "active" || phase.status === "active_problem");
    const status = active ? (problems ? "active_problem" : "active") : problems ? "problem" : members.length ? "completed" : "pending";
    const fallbackSummary = count ? `${count} элементов · важных ${important} · проблем ${problems}` : "Нет записей";
    const summary = members.map((phase) => phase.summary || phase[id]).find(Boolean);
    return {
      id,
      label: phaseLabels[id],
      status,
      tone: reportTone(status),
      summary: text(summary, fallbackSummary),
      items: members.map(v2Phase).flatMap((phase) => phase.items),
    };
  });
}

function legacyStatus(status: string, severity: AgentRunReportSeverity) {
  const normalized = status.toLowerCase();
  if (normalized === "waiting") return { label: "Ждёт вас", tone: "warning" as const, pulse: true };
  if (normalized === "plan_review") return { label: "Нужно подтверждение", tone: "warning" as const, pulse: true };
  if (["running", "pending"].includes(normalized)) return { label: normalized === "running" ? "Выполняется" : "В очереди", tone: "info" as const, pulse: true };
  if (normalized === "failed") return { label: "Ошибка", tone: "danger" as const, pulse: false };
  if (normalized === "stopped") return { label: "Остановлен", tone: "neutral" as const, pulse: false };
  if (["warning", "high", "critical", "fatal"].includes(severity)) return { label: "С замечаниями", tone: reportTone(severity), pulse: false };
  return { label: "Завершён", tone: "success" as const, pulse: false };
}

function legacyEvidence(runId: number, report: AgentRunReportResponse) {
  const eventLinks = report.events.map((event, index): ReportEvidenceLinkViewModel => {
    const id = text(event.id, `event-${index + 1}`);
    return {
      id,
      kind: "event",
      label: text(event.title, `Событие ${index + 1}`),
      summary: text(event.summary || event.message),
      view: "events",
      href: `/agents/run/${runId}?tab=evidence&view=events&evidence=${encodeURIComponent(id)}`,
      targetId: id,
      occurredAt: event.created_at || null,
      downloadUrl: "",
      contentType: "",
      sizeBytes: 0,
      truncated: false,
    };
  });
  const artifactLinks = report.artifacts.map((artifact, index): ReportEvidenceLinkViewModel => {
    const id = text(artifact.id, `artifact-${index + 1}`);
    return {
      id,
      kind: "artifact",
      label: text(artifact.name, `Файл ${index + 1}`),
      summary: text(artifact.description),
      view: "artifacts",
      href: `/agents/run/${runId}?tab=evidence&view=artifacts&evidence=${encodeURIComponent(id)}`,
      targetId: id,
      occurredAt: artifact.created_at || null,
      downloadUrl: text(artifact.download_url),
      contentType: text(artifact.content_type),
      sizeBytes: artifact.size_bytes || 0,
      truncated: Boolean(artifact.truncated),
    };
  });
  return [...eventLinks, ...artifactLinks];
}

function legacyFinding(item: AgentRunReportFinding, index: number, links: ReportEvidenceLinkViewModel[]): ReportFindingViewModel {
  return {
    id: text(item.id, `finding-${index + 1}`),
    title: text(item.title, "Наблюдение"),
    summary: text(item.description),
    details: "",
    severity: item.severity,
    tone: reportTone(item.severity),
    confidence: "",
    scope: "",
    source: text(item.source),
    evidence: links[index] ? [links[index]] : [],
  };
}

function legacyAction(item: AgentRunReportRecommendation, index: number): ReportActionViewModel {
  return {
    id: text(item.id, `action-${index + 1}`),
    title: text(item.title, "Следующий шаг"),
    summary: text(item.description),
    details: "",
    priority: text(item.priority),
    status: item.done ? "done" : "open",
    owner: text(item.owner),
    cta: { kind: "", label: "", target: "", enabled: false, isMutation: false, requiresConfirmation: false },
    evidence: [],
  };
}

function legacyPhaseItem(item: AgentRunReportStep | AgentRunReportLog, kind: string, index: number): ReportPhaseItemViewModel {
  const isLog = "stdout" in item;
  const raw = isLog
    ? [text(item.command), text(item.stdout), text(item.stderr)].filter(Boolean).join("\n\n")
    : [text(item.command), text(item.details), text(item.error)].filter(Boolean).join("\n\n");
  return {
    id: text(item.id, `${kind}-${index + 1}`),
    title: text(item.title, `Шаг ${index + 1}`),
    summary: isLog ? text(item.stderr || item.stdout) : text(item.description || item.error),
    status: text(item.status),
    tone: reportTone(item.severity || item.status),
    kind,
    raw,
    evidence: [],
    startedAt: isLog ? item.timestamp : item.started_at,
    completedAt: isLog ? item.timestamp : item.completed_at,
  };
}

function documentPreviewSummary(markdown: string | undefined) {
  for (const rawLine of (markdown || "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || /^#{1,6}\s/.test(line) || /^[-*+]\s/.test(line) || /^(?:Outcome|Статус):/i.test(line)) continue;
    return line
      .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/[*_`~]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }
  return "";
}

function localizedTechnicalText(value: unknown) {
  return text(value)
    .replace(/\bLLM call failed\b/gi, "ошибка LLM")
    .replace(/\btelegram_not_configured\b/gi, "Telegram не настроен");
}

function v2ViewModel(report: AgentRunReportV2Response): ReportViewModel {
  const indicatorSource = report.indicators || report.dynamic_indicators || [];
  const refSource = [
    ...indicatorSource.flatMap((item) => item.evidence_refs || []),
    ...(report.findings || []).flatMap((item) => item.evidence_refs || []),
    ...(report.actions || []).flatMap((item) => item.evidence_refs || []),
  ];
  const links = Array.from(
    new Map(normalizeRefs(report.run.id, refSource).map((item) => [`${item.kind}:${item.id}`, item])).values(),
  );
  const lifecycleTone = reportTone(report.lifecycle.status);
  const reservedSystemIndicator = (value: unknown) => {
    const normalized = text(value).toLowerCase().replace(/[^a-z0-9а-яё]+/g, "");
    return new Set(["outcome", "reportdelivery", "reportgeneration", "delivery"]).has(normalized);
  };
  const schemaIndicators = [...indicatorSource]
    .filter((item) => !reservedSystemIndicator(item.id) && !reservedSystemIndicator(item.role))
    .sort((a, b) => (numberOrNull(a.priority) ?? 999) - (numberOrNull(b.priority) ?? 999))
    .map((item, index): ReportIndicatorViewModel => ({
      id: text(item.id, `indicator-${index + 1}`),
      label: text(item.label),
      value: text(item.value),
      hint: item.denominator != null ? `${item.numerator ?? 0} из ${item.denominator} ${item.unit}`.trim() : text(item.unit),
      tone: reportTone(item.tone),
      role: text(item.role),
      valueKind: text(item.value_kind),
      unit: text(item.unit),
      numerator: numberOrNull(item.numerator),
      denominator: numberOrNull(item.denominator),
      priority: numberOrNull(item.priority) ?? index,
      evidenceRefs: (item.evidence_refs || []).map((ref) => text(ref.ref)),
    }));
  const delivery = report.delivery;
  const outcomeTone = reportTone(report.outcome.severity || report.outcome.status);
  const transitionDelivery = delivery as typeof delivery & { summary?: string };
  const mandatoryIndicators: ReportIndicatorViewModel[] = [
    {
      id: "outcome",
      label: "Результат",
      value: text(report.outcome.label, report.outcome.status),
      hint: "",
      tone: outcomeTone,
      role: "primary",
      valueKind: "status",
      unit: "",
      numerator: null,
      denominator: null,
      priority: -2,
      evidenceRefs: [],
    },
    {
      id: "report-delivery",
      label: "Отчёт и доставка",
      value: text(report.report_generation.label, report.report_generation.ready ? "Отчёт готов" : report.report_generation.status),
      hint: [localizedTechnicalText(report.report_generation.error), delivery.label ? `Доставка: ${delivery.label}` : "", localizedTechnicalText(delivery.description || transitionDelivery.summary || delivery.blocked_reason)].filter(Boolean).join(" · "),
      tone: reportTone(report.report_generation.status),
      role: "supporting",
      valueKind: "status",
      unit: "",
      numerator: null,
      denominator: null,
      priority: -1,
      evidenceRefs: [],
    },
  ];
  const seenIndicators = new Set<string>();
  const indicators = [...mandatoryIndicators, ...schemaIndicators]
    .filter((item) => {
      const key = `${item.role}:${item.id}`;
      if (seenIndicators.has(key)) return false;
      seenIndicators.add(key);
      return true;
    })
    .slice(0, 4);
  const watermark = report.event_high_watermark
    ? `${report.event_high_watermark.sequence_no}/${report.event_high_watermark.total}`
    : text(report.event_watermark);
  return {
    sourceVersion: "v2",
    run: {
      id: report.run.id,
      agentId: report.run.agent_id,
      agentName: text(report.run.agent_name),
      agentType: text(report.run.agent_type),
      agentMode: text(report.run.agent_mode),
      serverId: report.run.server_id,
      serverName: text(report.run.server_name),
      lifecycleStatus: text(report.lifecycle.status),
      isActive: Boolean(report.lifecycle.is_active),
      isTerminal: Boolean(report.lifecycle.is_terminal),
      canCleanup: Boolean(report.lifecycle.can_cleanup),
      canApprove: report.lifecycle.status === "plan_review",
      pendingQuestion: "",
      startedAt: report.lifecycle.started_at,
      completedAt: report.lifecycle.completed_at,
      durationMs: report.lifecycle.duration_ms || 0,
    },
    header: {
      title: text(report.run.agent_name, `Отчёт #${report.run.id}`),
      summary: localizedTechnicalText(report.outcome.reason || documentPreviewSummary(report.document?.preview) || report.evidence_state.summary) || "Отчёт пока формируется.",
      statusLabel: text(report.outcome.label, report.outcome.status),
      statusTone: outcomeTone,
      pulse: false,
    },
    axes: [
      { id: "lifecycle", label: "Запуск", value: text(report.lifecycle.label), detail: text(report.lifecycle.status), tone: lifecycleTone, pulse: report.lifecycle.is_active },
      { id: "outcome", label: "Результат", value: text(report.outcome.label), detail: localizedTechnicalText(report.outcome.reason || report.outcome.exit_reason), tone: reportTone(report.outcome.severity || report.outcome.status) },
      { id: "evidence", label: "Доказательства", value: text(report.evidence_state.label), detail: text(report.evidence_state.summary), tone: reportTone(report.evidence_state.status) },
      { id: "generation", label: "Отчёт", value: text(report.report_generation.label), detail: localizedTechnicalText(report.report_generation.error), tone: reportTone(report.report_generation.status) },
      { id: "delivery", label: "Доставка", value: text(delivery.label), detail: text(delivery.description || transitionDelivery.summary || delivery.blocked_reason), tone: reportTone(delivery.severity || delivery.status) },
    ],
    indicators,
    findings: (report.findings || []).map((item) => v2Finding(report.run.id, item)),
    actions: (report.actions || []).map((item) => v2Action(report.run.id, item)),
    phases: presentationPhases(report.phases || []),
    evidenceLinks: links,
    evidenceEndpoints: {
      events: text(report.evidence_links?.events),
      activity: text(report.evidence_links?.activity),
      artifacts: text(report.evidence_links?.artifacts),
      auditExport: text(report.evidence_links?.audit_export),
    },
    counts: {
      events: report.counts.events_total || 0,
      importantEvents: report.counts.important_events || 0,
      problems: (report.counts.execution_problem_events || 0) + (report.counts.delivery_problem_events || 0),
      activities: report.counts.operations_total ?? report.counts.activities_total ?? 0,
      processedActivities: report.counts.operations_total != null
        ? (report.counts.operations_succeeded || 0) + (report.counts.operations_failed || 0) + (report.counts.operations_unknown || 0)
        : (report.counts.activities_succeeded || 0) + (report.counts.activities_failed || 0) + (report.counts.activities_unknown || 0),
      failedActivities: report.counts.operations_failed ?? report.counts.activities_failed ?? 0,
      artifacts: report.counts.artifacts || 0,
    },
    delivery: {
      enabled: Boolean(delivery.enabled),
      channel: text(delivery.channel),
      status: text(delivery.status),
      label: text(delivery.label),
      summary: text(delivery.description || transitionDelivery.summary),
      target: text(delivery.target),
      tone: reportTone(delivery.severity || delivery.status),
      canRetry: Boolean(delivery.can_retry),
      blockedReason: text(delivery.blocked_reason),
      nextAction: text(delivery.next_action),
      setupUrl: text(delivery.setup_url, "/settings/notifications"),
    },
    document: {
      available: Boolean(report.document?.available),
      title: text(report.document?.title, `Отчёт #${report.run.id}`),
      contentType: text(report.document?.content_type, "text/markdown"),
      sizeBytes: report.document?.size_bytes || 0,
      checksum: text(report.document?.checksum_sha256),
      preview: text(report.document?.preview),
      previewTruncated: Boolean(report.document?.preview_truncated),
      downloadUrl: text(report.document?.download_url),
    },
    provenance: {
      source: text(report.outcome.source, "report/v2"),
      revision: text(report.report_revision || report.revision),
      generatedAt: report.updated_at || report.generated_at || report.report_generation.generated_at || null,
      checksum: text(report.document?.checksum_sha256),
      eventWatermark: watermark,
    },
    embedded: { events: [], activity: [], artifacts: [] },
  };
}

function legacyViewModel(report: AgentRunReportResponse): ReportViewModel {
  const run = report.run;
  const status = legacyStatus(run.status, report.report.severity);
  const links = legacyEvidence(run.id, report);
  const findings = [...report.report.findings, ...report.report.risks].map((item, index) => legacyFinding(item, index, links));
  const delivery = report.delivery_state;
  const activity: AgentRunActivityV2Item[] = report.logs.map((item, index) => ({
    id: item.id,
    ordinal: index + 1,
    kind: "command",
    status: item.status,
    success: item.exit_code === 0,
    title: item.title,
    summary: item.stderr || item.stdout,
    tool: "",
    server: report.run.server_name,
    command: item.command,
    exit_code: item.exit_code,
    duration_ms: item.duration_ms,
    started_at: item.timestamp,
    completed_at: item.timestamp,
    error: item.stderr,
    evidence_refs: [],
  }));
  return {
    sourceVersion: "legacy",
    run: {
      id: run.id,
      agentId: run.agent_id,
      agentName: run.agent_name,
      agentType: run.agent_type,
      agentMode: run.agent_mode,
      serverId: run.server_id,
      serverName: run.server_name,
      lifecycleStatus: run.status,
      isActive: ["running", "pending", "paused", "waiting"].includes(run.status),
      isTerminal: Boolean(report.report_state?.is_terminal),
      canCleanup: Boolean(report.report_state?.execution_state?.can_cleanup),
      canApprove: run.status === "plan_review",
      pendingQuestion: run.pending_question,
      startedAt: run.started_at,
      completedAt: run.completed_at,
      durationMs: run.duration_ms,
    },
    header: {
      title: text(report.report.title, run.agent_name),
      summary: text(report.report.root_cause || report.report.summary || report.report_state?.headline, "Отчёт пока формируется."),
      statusLabel: status.label,
      statusTone: status.tone,
      pulse: status.pulse,
    },
    axes: [
      { id: "lifecycle", label: "Запуск", value: status.label, detail: run.status, tone: status.tone, pulse: status.pulse },
      { id: "outcome", label: "Результат", value: report.report.status_label, detail: report.report.summary, tone: reportTone(report.report.severity) },
      { id: "evidence", label: "Доказательства", value: report.artifact_state.ready ? "Собраны" : "Неполные", detail: report.artifact_state.description, tone: report.artifact_state.ready ? "success" : "warning" },
      { id: "generation", label: "Отчёт", value: report.report_state.report_ready ? "Готов" : "Формируется", detail: report.report_state.description, tone: report.report_state.report_ready ? "success" : "info" },
      ...(delivery ? [{ id: "delivery" as const, label: "Доставка", value: delivery.label, detail: delivery.description, tone: reportTone(delivery.severity || delivery.status) }] : []),
    ],
    indicators: report.report.kpis.slice(0, 4).map((item, index) => ({
      id: item.id || `indicator-${index + 1}`,
      label: item.label,
      value: item.value,
      hint: item.hint,
      tone: reportTone(item.severity),
      role: "legacy",
      valueKind: "text",
      unit: "",
      numerator: null,
      denominator: null,
      priority: index,
      evidenceRefs: [],
    })),
    findings,
    actions: report.report.recommendations.map(legacyAction),
    phases: [
      { id: "goal", label: "Цель", status: run.status, tone: status.tone, summary: report.report.subtitle || report.report.summary, items: [] },
      { id: "action", label: "Действия", status: run.status, tone: status.tone, summary: report.report_state.current_step, items: report.agent_steps.map((item, index) => legacyPhaseItem(item, "step", index)) },
      { id: "observation", label: "Наблюдения", status: report.report.status, tone: reportTone(report.report.severity), summary: report.report.summary, items: report.logs.map((item, index) => legacyPhaseItem(item, "command", index)) },
      { id: "conclusion", label: "Вывод", status: report.report.status, tone: reportTone(report.report.severity), summary: report.report.root_cause || report.report.summary, items: [] },
    ],
    evidenceLinks: links,
    evidenceEndpoints: { events: "", activity: "", artifacts: "", auditExport: "" },
    counts: {
      events: report.event_summary?.total ?? report.events.length,
      importantEvents: report.event_summary?.important ?? report.events.filter((item) => item.important).length,
      problems: report.event_summary?.problems ?? findings.filter((item) => severityOrder[item.severity] >= severityOrder.warning).length,
      activities: activity.length,
      processedActivities: activity.length,
      failedActivities: activity.filter((item) => reportTone(item.status) === "danger").length,
      artifacts: report.artifacts.length,
    },
    delivery: {
      enabled: Boolean(delivery?.enabled),
      channel: text(delivery?.channel),
      status: text(delivery?.status),
      label: text(delivery?.label),
      summary: text(delivery?.description),
      target: text(delivery?.target),
      tone: reportTone(delivery?.severity || delivery?.status),
      canRetry: Boolean(
        delivery?.enabled
        && ["failed", "error"].includes(text(delivery?.status).toLowerCase())
        && !/(not.?configured|disabled|skipped|blocked|token|chat.?id|не настро)/i.test(
          [delivery?.status, delivery?.description, delivery?.next_action].filter(Boolean).join(" "),
        )
      ),
      blockedReason: /(not.?configured|disabled|skipped|blocked|token|chat.?id|не настро)/i.test(
        [delivery?.status, delivery?.description, delivery?.next_action].filter(Boolean).join(" "),
      ) ? text(delivery?.description || delivery?.next_action) : "",
      nextAction: text(delivery?.next_action),
      setupUrl: "/settings/notifications",
    },
    document: {
      available: Boolean(report.report.markdown),
      title: report.report.title || `Отчёт #${run.id}`,
      contentType: "text/markdown",
      sizeBytes: new Blob([report.report.markdown || ""]).size,
      checksum: "",
      preview: report.report.markdown || "",
      previewTruncated: false,
      downloadUrl: "",
    },
    provenance: { source: "report/v1", revision: text(report.schema_version), generatedAt: report.generated_at || null, checksum: "", eventWatermark: "" },
    embedded: { events: report.events, activity, artifacts: report.artifacts },
  };
}

export function createReportViewModel(report: ReportSource): ReportViewModel {
  return isReportV2(report) ? v2ViewModel(report) : legacyViewModel(report);
}
