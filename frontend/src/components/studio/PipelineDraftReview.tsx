import type { ReactNode } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  HelpCircle,
  Route,
  Server,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getAssistantPatchStats } from "@/components/pipeline/assistantPatch";
import { getPipelineDraftStatus } from "@/components/studio/pipelineDraftStatus";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { StudioPipelineAssistantResponse, StudioPipelineDraftResourceItem } from "@/lib/studioPipelineDraftsApi";

function formatDiagnostic(message: string): string {
  const text = String(message || "").trim();
  const cycleMatch = text.match(/^AI edge '([^']+)->([^']+)' would create a cycle and was dropped\.$/);
  if (cycleMatch) return `Удалена связь ${cycleMatch[1]} -> ${cycleMatch[2]}: она создавала цикл в DAG.`;
  const missingMatch = text.match(/^AI edge '([^']+)->([^']+)' referenced a missing node and was dropped\.$/);
  if (missingMatch) return `Удалена связь ${missingMatch[1]} -> ${missingMatch[2]}: одна из нод не найдена.`;
  const repairedMatch = text.match(/^AI graph repair added edge '([^']+)->([^']+)' \(([^)]+)\)\.$/);
  if (repairedMatch) return `Добавлена связь ${repairedMatch[1]} -> ${repairedMatch[2]}: автоматический ремонт графа.`;
  return text;
}

function confidenceToPercent(confidence?: number | null): number | null {
  if (typeof confidence !== "number" || Number.isNaN(confidence)) return null;
  const normalized = confidence <= 1 ? confidence * 100 : confidence;
  return Math.max(0, Math.min(100, Math.round(normalized)));
}

function EmptyLine({ children }: { children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg border border-dashed border-border/70 bg-background/35 px-3 py-3 text-xs text-muted-foreground [overflow-wrap:anywhere]">
      {children}
    </div>
  );
}

function TextList({
  icon,
  items,
  empty,
  tone = "default",
}: {
  icon: ReactNode;
  items?: string[];
  empty: string;
  tone?: "default" | "warning" | "danger" | "question";
}) {
  const visibleItems = (items || []).filter(Boolean).slice(0, 6);
  const toneClass =
    tone === "danger"
      ? "border-red-500/25 bg-red-500/10 text-red-100"
      : tone === "warning"
        ? "border-amber-500/25 bg-amber-500/10 text-amber-100"
        : tone === "question"
          ? "border-sky-500/25 bg-sky-500/10 text-sky-100"
          : "border-border/70 bg-background/45 text-muted-foreground";

  if (!visibleItems.length) return <EmptyLine>{empty}</EmptyLine>;

  return (
    <div className={cn("flex min-w-0 flex-col gap-2 rounded-lg border px-3 py-3 text-xs leading-5", toneClass)}>
      {visibleItems.map((item, index) => (
        <div key={`${item}-${index}`} className="flex min-w-0 gap-2">
          <span className="mt-0.5 shrink-0">{icon}</span>
          <span className="min-w-0 [overflow-wrap:anywhere]">{formatDiagnostic(item)}</span>
        </div>
      ))}
    </div>
  );
}

function ResourceRow({
  icon,
  label,
  items,
  empty,
}: {
  icon: ReactNode;
  label: string;
  items?: StudioPipelineDraftResourceItem[];
  empty: string;
}) {
  const visible = (items || []).slice(0, 5);
  return (
    <div className="min-w-0 rounded-lg border border-border/70 bg-background/45 px-3 py-3">
      <div className="mb-2 flex min-w-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {icon}
        <span className="min-w-0 truncate">{label}</span>
      </div>
      {visible.length ? (
        <div className="flex flex-col gap-2">
          {visible.map((item, index) => (
            <div key={`${item.id || item.slug || item.name || index}`} className="min-w-0 rounded-md border border-border/60 bg-card/70 px-2.5 py-2">
              <div className="truncate text-xs font-medium text-foreground">{item.name || item.slug || item.id}</div>
              {item.reason ? <div className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-muted-foreground">{item.reason}</div> : null}
              {Array.isArray(item.tools) && item.tools.length ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {item.tools.slice(0, 4).map((tool) => (
                    <span key={tool} className="min-w-0 rounded border border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground [overflow-wrap:anywhere]">
                      {tool}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
          {(items || []).length > visible.length ? (
            <div className="text-[11px] text-muted-foreground">+{(items || []).length - visible.length}</div>
          ) : null}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground/75">{empty}</div>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border/70 bg-card/70 px-3 py-2 text-center">
      <div className="text-lg font-semibold text-foreground">{value}</div>
      <div className="truncate text-[10px] uppercase tracking-[0.08em] text-muted-foreground">{label}</div>
    </div>
  );
}

function GraphNodes({
  response,
  compact,
  lang,
  graphCounts,
}: {
  response: StudioPipelineAssistantResponse;
  compact: boolean;
  lang: string;
  graphCounts?: { nodes: number; edges: number };
}) {
  const graphNodes = response.graph_patch?.nodes || [];
  if (!graphNodes.length) {
    if (graphCounts?.nodes) {
      return (
        <EmptyLine>
          {localize(lang, "Граф показан на canvas превью.", "The graph is shown on the canvas preview.")}
        </EmptyLine>
      );
    }
    return <EmptyLine>{localize(lang, "Изменения графа пусты.", "Graph patch is empty.")}</EmptyLine>;
  }

  return (
    <ScrollArea className={cn("pr-3", compact ? "max-h-44" : "max-h-64")}>
      <div className="flex flex-col gap-2">
        {graphNodes.slice(0, compact ? 6 : 12).map((node, index) => (
          <div key={node.ref} className="min-w-0 rounded-lg border border-border/70 bg-card/70 px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-[10px] font-semibold text-primary">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-foreground">{node.label || node.ref}</div>
                <div className="truncate text-[11px] text-muted-foreground">{node.type}</div>
              </div>
            </div>
            {response.node_explanations?.[node.ref] ? (
              <div className="mt-2 text-[11px] leading-4 text-muted-foreground [overflow-wrap:anywhere]">{response.node_explanations[node.ref]}</div>
            ) : null}
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}

export function PipelineDraftReview({
  response,
  lang,
  actions,
  compact = false,
  hideQuestions = false,
  graphCounts,
}: {
  response: StudioPipelineAssistantResponse;
  lang: "en" | "ru" | string;
  actions?: ReactNode;
  compact?: boolean;
  hideQuestions?: boolean;
  graphCounts?: { nodes: number; edges: number };
}) {
  const stats = getAssistantPatchStats(response);
  const displayNodes = graphCounts?.nodes ?? stats.addedNodes;
  const displayEdges = graphCounts?.edges ?? stats.addedEdges;
  const status = getPipelineDraftStatus(response, lang);
  const StatusIcon = status.icon;
  const warnings = [...(response.warnings || []), ...(response.validation?.warnings || [])];
  const errors = response.validation?.errors || [];
  const riskItems = response.risk?.items || [];
  const resourcePlan = response.resource_plan || {};
  const confidencePercent = confidenceToPercent(response.confidence);
  const tabListClass = compact ? "grid h-auto w-full grid-cols-2" : "grid h-auto w-full grid-cols-4";

  const summaryContent = (
    <div className="flex flex-col gap-3">
      <TextList
        icon={<CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" />}
        items={response.requirements}
        empty={localize(lang, "Требования пока не выделены.", "No parsed requirements yet.")}
      />
      {!compact ? (
        <>
          <TextList
            icon={<ChevronRight className="h-3.5 w-3.5 text-primary" />}
            items={response.assumptions}
            empty={localize(lang, "Допущений нет.", "No assumptions.")}
          />
          {!hideQuestions ? (
            <TextList
              icon={<HelpCircle className="h-3.5 w-3.5" />}
              items={response.questions}
              empty={localize(lang, "Вопросов нет.", "No open questions.")}
              tone="question"
            />
          ) : null}
        </>
      ) : null}
    </div>
  );

  const graphContent = (
    <div className="flex flex-col gap-3">
      <GraphNodes response={response} compact={compact} lang={lang} graphCounts={graphCounts} />
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded-lg border border-border/70 bg-background/45 px-3 py-2">
          <span className="text-muted-foreground">{localize(lang, "Связи", "Edges")}</span>
          <span className="ml-2 font-semibold text-foreground">{displayEdges}</span>
        </div>
        <div className="rounded-lg border border-border/70 bg-background/45 px-3 py-2">
          <span className="text-muted-foreground">{localize(lang, "Обновления", "Updates")}</span>
          <span className="ml-2 font-semibold text-foreground">{response.graph_patch?.update_nodes?.length || 0}</span>
        </div>
      </div>
      <TextList
        icon={<AlertTriangle className="h-3.5 w-3.5" />}
        items={warnings}
        empty={localize(lang, "Предупреждений нет.", "No warnings.")}
        tone="warning"
      />
      <TextList
        icon={<XCircle className="h-3.5 w-3.5" />}
        items={errors}
        empty={localize(lang, "Ошибок валидации нет.", "No validation errors.")}
        tone="danger"
      />
    </div>
  );

  const resourcesContent = (
    <div className="grid gap-2">
      <ResourceRow
        icon={<Server className="h-3.5 w-3.5 text-primary" />}
        label={localize(lang, "Серверы", "Servers")}
        items={resourcePlan.servers}
        empty={localize(lang, "Не выбраны явно", "None selected")}
      />
      <ResourceRow
        icon={<Wrench className="h-3.5 w-3.5 text-primary" />}
        label="MCP"
        items={resourcePlan.mcp_servers}
        empty={localize(lang, "MCP не требуется или недоступен", "No MCP required or available")}
      />
      {!compact ? (
        <ResourceRow
          icon={<Bot className="h-3.5 w-3.5 text-primary" />}
          label={localize(lang, "Skills", "Skills")}
          items={resourcePlan.skills}
          empty={localize(lang, "Без дополнительных skills", "No extra skills")}
        />
      ) : null}
      <TextList
        icon={<ChevronRight className="h-3.5 w-3.5 text-primary" />}
        items={[...(resourcePlan.missing || []), ...(resourcePlan.notes || [])]}
        empty={localize(lang, "Нет пропущенных ресурсов.", "No missing resources.")}
      />
    </div>
  );

  const riskContent = (
    <div className="flex flex-col gap-3">
      {riskItems.length ? (
        <div className="flex flex-col gap-2 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-3 text-xs leading-5 text-red-100">
          {riskItems.slice(0, compact ? 3 : 8).map((item, index) => (
          <div key={`${item.node_id}-${item.command || index}`} className="flex min-w-0 gap-2">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 [overflow-wrap:anywhere]">{item.node_label || item.node_id}: {item.reasons?.join(", ") || item.command || item.level}</span>
          </div>
        ))}
        </div>
      ) : (
        <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-3 text-xs text-emerald-100">
          <ShieldCheck className="mr-2 inline h-3.5 w-3.5" />
          {localize(lang, "Опасные действия не обнаружены.", "No dangerous actions detected.")}
        </div>
      )}
      <TextList
        icon={<ClipboardList className="h-3.5 w-3.5 text-primary" />}
        items={response.suggested_next_actions}
        empty={localize(lang, "Следующие действия не предложены.", "No suggested next actions.")}
      />
    </div>
  );

  return (
    <div className="flex h-full min-w-0 flex-col gap-4">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground">
            {localize(lang, "Проверенный черновик", "Verified draft")}
          </h3>
          <p className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">
            {response.patch_summary || response.reply || localize(lang, "Изменения графа подготовлены.", "Graph changes are ready.")}
          </p>
        </div>
        <Badge variant="outline" className={cn("shrink-0 gap-1", status.className)}>
          <StatusIcon className="h-3 w-3" />
          {status.label}
        </Badge>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Metric label={localize(lang, "нод", "nodes")} value={displayNodes} />
        <Metric label={localize(lang, "связей", "edges")} value={displayEdges} />
        <Metric label={localize(lang, "правок", "edits")} value={stats.updatedNodes} />
      </div>

      {confidencePercent !== null ? (
        <div className="rounded-lg border border-border/70 bg-background/45 px-3 py-2">
          <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>{localize(lang, "Уверенность", "Confidence")}</span>
            <span>{confidencePercent}%</span>
          </div>
          <Progress value={confidencePercent} className="h-1.5 bg-secondary/70" />
        </div>
      ) : null}

      {compact ? (
        <div className="flex flex-col gap-3">
          {summaryContent}
          {graphContent}
          {resourcesContent}
          {riskItems.length ? riskContent : null}
        </div>
      ) : (
        <Tabs defaultValue="summary" className="min-h-0 flex-1">
          <TabsList className={tabListClass}>
            <TabsTrigger value="summary" className="text-xs">
              {localize(lang, "Сводка", "Summary")}
            </TabsTrigger>
            <TabsTrigger value="graph" className="text-xs">
              {localize(lang, "Граф", "Graph")}
            </TabsTrigger>
            <TabsTrigger value="resources" className="text-xs">
              {localize(lang, "Ресурсы", "Resources")}
            </TabsTrigger>
            <TabsTrigger value="risk" className="text-xs">
              {localize(lang, "Риски", "Risk")}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="summary" className="mt-3">
            {summaryContent}
          </TabsContent>
          <TabsContent value="graph" className="mt-3">
            {graphContent}
          </TabsContent>
          <TabsContent value="resources" className="mt-3">
            {resourcesContent}
          </TabsContent>
          <TabsContent value="risk" className="mt-3">
            {riskContent}
          </TabsContent>
        </Tabs>
      )}

      {actions ? <div className="mt-auto">{actions}</div> : null}
    </div>
  );
}
