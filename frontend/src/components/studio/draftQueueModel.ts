import type { StudioPipelineAssistantResponse, StudioPipelineDraftSession } from "@/lib/studioPipelineDraftsApi";

export type DraftFilter = "active" | "ready" | "needs_fix" | "applied";

export const DRAFT_FILTERS: Array<{ value: DraftFilter; labelRu: string; labelEn: string }> = [
  { value: "active", labelRu: "Активные", labelEn: "Active" },
  { value: "ready", labelRu: "Готовые", labelEn: "Ready" },
  { value: "needs_fix", labelRu: "Нужны правки", labelEn: "Needs fix" },
  { value: "applied", labelRu: "Применены", labelEn: "Applied" },
];

export function getDraftResponse(session: StudioPipelineDraftSession | null): StudioPipelineAssistantResponse | null {
  return session?.latest_revision?.response || null;
}

export function canReviseDraft(session: StudioPipelineDraftSession | null): boolean {
  return Boolean(session && session.status !== "applied" && session.status !== "discarded");
}

export function isDraftReady(session: StudioPipelineDraftSession): boolean {
  const response = getDraftResponse(session);
  return Boolean(response && response.validation?.ok !== false && response.risk?.level !== "dangerous");
}

export function matchesDraftFilter(session: StudioPipelineDraftSession, filter: DraftFilter): boolean {
  const response = getDraftResponse(session);
  if (filter === "applied") return session.status === "applied";
  if (filter === "ready") return session.status !== "discarded" && isDraftReady(session);
  if (filter === "needs_fix") {
    return session.status !== "discarded" && Boolean(response?.validation?.ok === false || response?.risk?.level === "dangerous");
  }
  return session.status !== "discarded" && session.status !== "applied";
}
