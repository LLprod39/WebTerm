import { applyAssistantGraphPatch, getAssistantPatchStats } from "@/components/pipeline/assistantPatch";
import type { PipelineEdge, PipelineNode } from "@/lib/api";
import type { StudioPipelineAssistantResponse, StudioPipelineDraftSession } from "@/lib/studioPipelineDraftsApi";

export type DraftCanvasModel = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  source: "preview" | "patch" | "empty";
  stats: ReturnType<typeof getAssistantPatchStats> | null;
};

export function responseFromDraftSession(session: StudioPipelineDraftSession | null): StudioPipelineAssistantResponse | null {
  return session?.latest_revision?.response || null;
}

export function buildDraftCanvasModel(session: StudioPipelineDraftSession | null): DraftCanvasModel {
  const revision = session?.latest_revision || null;
  const response = responseFromDraftSession(session);
  if (revision?.preview_nodes?.length || revision?.preview_edges?.length) {
    return {
      nodes: revision.preview_nodes || [],
      edges: revision.preview_edges || [],
      source: "preview",
      stats: response ? getAssistantPatchStats(response) : null,
    };
  }
  if (response) {
    const patched = applyAssistantGraphPatch({ nodes: [], edges: [], response });
    return {
      nodes: patched.nodes,
      edges: patched.edges,
      source: "patch",
      stats: patched.stats,
    };
  }
  return { nodes: [], edges: [], source: "empty", stats: null };
}
