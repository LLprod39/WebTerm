import {
  getDraftResponse,
  matchesDraftFilter,
  type DraftFilter,
} from "@/components/studio/draftQueueModel";
import { localize } from "@/lib/i18n";
import type {
  StudioPipelineAssistantPayload,
  StudioPipelineAssistantResponse,
  StudioPipelineDraftSession,
} from "@/lib/studioPipelineDraftsApi";

export type StudioDraftMobilePane = "queue" | "graph" | "compose" | "review";

export const STUDIO_DRAFT_MOBILE_PANES: Array<{
  value: StudioDraftMobilePane;
  labelRu: string;
  labelEn: string;
}> = [
  { value: "queue", labelRu: "Очередь", labelEn: "Queue" },
  { value: "graph", labelRu: "Граф", labelEn: "Graph" },
  { value: "compose", labelRu: "Запрос", labelEn: "Request" },
  { value: "review", labelRu: "Проверка", labelEn: "Review" },
];

export function getDefaultDraftName(lang: string): string {
  return localize(lang, "Операционный сценарий", "Operations runbook");
}

export function getPromptPresets(lang: string): string[] {
  return [
    localize(
      lang,
      "Ежедневная проверка серверов с отчетом в Telegram и ручным резервным сценарием",
      "Daily server health check with Telegram report and manual fallback",
    ),
    localize(
      lang,
      "Оповещение Docker: диагностика, подтверждение и безопасное восстановление",
      "Monitoring alert for Docker: diagnose, approve, safe remediation",
    ),
    localize(
      lang,
      "Webhook для задач оператора: принять payload, запустить агента, отправить сводку",
      "Operator webhook: receive payload, run agent, send summary",
    ),
  ];
}

export function buildAssistantPayload({
  title,
  message,
  previousResponse,
  compilerMode,
}: {
  title: string;
  message: string;
  previousResponse: StudioPipelineAssistantResponse | null;
  compilerMode?: StudioPipelineAssistantPayload["compiler_mode"];
}): StudioPipelineAssistantPayload {
  return {
    pipeline_id: null,
    pipeline_name: title.trim() || "Operations runbook",
    nodes: [],
    edges: [],
    selected_node: null,
    user_message: message,
    intent: "create",
    compiler_mode: compilerMode,
    draft_mode: true,
    last_validation_errors: previousResponse?.validation?.errors || [],
    history: previousResponse
      ? [
          {
            role: "assistant",
            content: [previousResponse.reply, previousResponse.patch_summary, ...(previousResponse.validation?.errors || [])]
              .filter(Boolean)
              .join("\n"),
          },
        ]
      : [],
  };
}

export function getDraftFilterCounts(draftSessions: StudioPipelineDraftSession[]): Record<DraftFilter, number> {
  return {
    active: draftSessions.filter((session) => matchesDraftFilter(session, "active")).length,
    ready: draftSessions.filter((session) => matchesDraftFilter(session, "ready")).length,
    needs_fix: draftSessions.filter((session) => matchesDraftFilter(session, "needs_fix")).length,
    applied: draftSessions.filter((session) => matchesDraftFilter(session, "applied")).length,
  };
}

export function getVisibleDrafts({
  draftSessions,
  filter,
  search,
}: {
  draftSessions: StudioPipelineDraftSession[];
  filter: DraftFilter;
  search: string;
}): StudioPipelineDraftSession[] {
  const q = search.trim().toLowerCase();
  return draftSessions
    .filter((session) => matchesDraftFilter(session, filter))
    .filter((session) => {
      if (!q) return true;
      return `${session.title} ${session.user_goal} ${getDraftResponse(session)?.patch_summary || ""}`.toLowerCase().includes(q);
    })
    .slice(0, 30);
}

export function buildDraftQuestionAnswerMessage({
  hasOpenQuestions,
  openQuestions,
  prompt,
  questionAnswers,
}: {
  hasOpenQuestions: boolean;
  openQuestions: string[];
  prompt: string;
  questionAnswers: Record<number, string>;
}): string {
  if (!hasOpenQuestions) return prompt.trim();
  const answers = openQuestions
    .map((question, index) => {
      const answer = (questionAnswers[index] || "").trim();
      if (!answer) return "";
      return `Q${index + 1}: ${question}\nA${index + 1}: ${answer}`;
    })
    .filter(Boolean)
    .join("\n\n");
  const extra = prompt.trim();
  return [answers, extra ? `Additional context:\n${extra}` : ""].filter(Boolean).join("\n\n").trim();
}
