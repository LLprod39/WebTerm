import type { AgentRunReportBlock, AgentRunReportBlockType } from "@/api/agent-report-v2-types";

import type {
  ReportActionViewModel,
  ReportFindingViewModel,
  ReportIndicatorViewModel,
  ReportViewModel,
} from "./reportViewModel";

const KNOWN = new Set<string>([
  "verdict",
  "metrics",
  "findings",
  "actions",
  "before_after",
  "bars",
  "chart",
  "kv",
  "table",
  "callout",
  "checklist",
  "done_steps",
  "code",
  "markdown",
]);

const FENCE_RE = /```report-blocks\s*([\s\S]*?)```/i;

export function stripReportBlocksFence(markdown: string): string {
  return (markdown || "").replace(FENCE_RE, "").trim();
}

export function parseReportBlocksFromMarkdown(markdown: string): AgentRunReportBlock[] {
  const match = (markdown || "").match(FENCE_RE);
  if (!match?.[1]) return [];
  try {
    const parsed = JSON.parse(match[1].trim()) as unknown;
    return normalizeReportBlocks(parsed);
  } catch {
    return [];
  }
}

export function normalizeReportBlocks(raw: unknown): AgentRunReportBlock[] {
  if (!Array.isArray(raw)) return [];
  const out: AgentRunReportBlock[] = [];
  raw.forEach((item, index) => {
    if (!item || typeof item !== "object") return;
    const block = item as AgentRunReportBlock;
    const type = String(block.type || "").trim().toLowerCase();
    if (!KNOWN.has(type)) return;
    if (!blockHasContent(type as AgentRunReportBlockType, block)) return;
    out.push({
      ...block,
      id: block.id || `block-${index + 1}`,
      type,
      span: block.span === "half" ? "half" : "full",
    });
  });
  return out.slice(0, 16);
}

function blockHasContent(type: AgentRunReportBlockType, block: AgentRunReportBlock): boolean {
  switch (type) {
    case "verdict":
    case "callout":
    case "markdown":
      return Boolean(String(block.text || "").trim());
    case "metrics":
    case "findings":
    case "actions":
    case "bars":
    case "kv":
    case "checklist":
      return Array.isArray(block.items) && block.items.length > 0;
    case "before_after":
      return Boolean(block.before?.value || block.after?.value);
    case "chart":
      return Array.isArray(block.series) && block.series.filter((n) => Number.isFinite(n)).length >= 2;
    case "table":
      return Array.isArray(block.rows) && block.rows.length > 0;
    case "done_steps":
      return Array.isArray(block.steps) && block.steps.length > 0;
    case "code":
      return Boolean(String(block.code || "").trim());
    default:
      return false;
  }
}

/** Prefer explicit API blocks → fence in markdown → synthesized default shell. */
export function resolveReportBlocks(viewModel: ReportViewModel, apiBlocks?: unknown): AgentRunReportBlock[] {
  const fromApi = normalizeReportBlocks(apiBlocks);
  if (fromApi.length) return fromApi;

  const fromMd = parseReportBlocksFromMarkdown(viewModel.document.preview || "");
  if (fromMd.length) return fromMd;

  return synthesizeDefaultBlocks(viewModel);
}

export function synthesizeDefaultBlocks(viewModel: ReportViewModel): AgentRunReportBlock[] {
  const blocks: AgentRunReportBlock[] = [];
  const verdict = String(viewModel.header.summary || "").trim();
  if (verdict) {
    blocks.push({
      id: "verdict",
      type: "verdict",
      text: verdict,
      tone: viewModel.header.statusTone,
    });
  }

  const metrics = viewModel.indicators.filter((item) => item.value && item.value !== "—").slice(0, 4);
  if (metrics.length) {
    blocks.push({
      id: "metrics",
      type: "metrics",
      items: metrics.map(indicatorToMetric),
    });
  }

  blocks.push({
    id: "findings",
    type: "findings",
    title: "Что нашли",
    span: "half",
    items: viewModel.findings.slice(0, 5).map(findingToItem),
  });

  blocks.push({
    id: "actions",
    type: "actions",
    title: "Что сделать",
    span: "half",
    items: viewModel.actions.slice(0, 4).map(actionToItem),
  });

  return blocks;
}

function indicatorToMetric(item: ReportIndicatorViewModel) {
  return {
    label: item.label,
    value: item.value,
    hint: item.hint || undefined,
    tone: item.tone,
  };
}

function findingToItem(item: ReportFindingViewModel) {
  return {
    title: item.title,
    summary: item.summary || undefined,
    tone: item.severity,
    meta: item.severity,
  };
}

function actionToItem(item: ReportActionViewModel) {
  return {
    title: item.title,
    summary: item.summary || undefined,
    tone: item.priority,
  };
}
