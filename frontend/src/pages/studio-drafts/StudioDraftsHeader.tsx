import { AlertTriangle, GitBranch, Wand2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DraftStatusBadge } from "@/components/studio/DraftQueue";
import { localize } from "@/lib/i18n";
import type { StudioPipelineAssistantResponse, StudioPipelineDraftSession } from "@/lib/studioPipelineDraftsApi";

export function StudioDraftsHeader({
  lang,
  activeDraft,
  activeResponse,
  nodeCount,
  edgeCount,
  onOverview,
}: {
  lang: string;
  activeDraft: StudioPipelineDraftSession | null;
  activeResponse: StudioPipelineAssistantResponse | null;
  nodeCount: number;
  edgeCount: number;
  onOverview: () => void;
}) {
  return (
    <div className="flex min-h-14 items-center justify-between gap-3 border-b border-border/70 bg-card/60 px-4">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10">
          <Wand2 className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold text-foreground">
            {localize(lang, "Черновики пайплайнов", "Pipeline drafts")}
          </h1>
          <p className="truncate text-xs text-muted-foreground">
            {localize(lang, "Сборка пайплайна по описанию", "Draft pipelines from an operations request")}
          </p>
        </div>
        <DraftStatusBadge session={activeDraft} lang={lang} />
      </div>

      <div className="hidden shrink-0 items-center gap-2 md:flex">
        <Badge variant="outline" className="gap-1 border-border/70 bg-background/40 text-muted-foreground">
          <GitBranch className="h-3 w-3" />
          {nodeCount} / {edgeCount}
        </Badge>
        {activeResponse?.risk?.level === "dangerous" ? (
          <Badge variant="outline" className="gap-1 border-red-500/25 bg-red-500/10 text-red-300">
            <AlertTriangle className="h-3 w-3" />
            {localize(lang, "Опасно", "Dangerous")}
          </Badge>
        ) : null}
        <Button type="button" variant="outline" size="sm" className="h-9 gap-1.5" onClick={onOverview}>
          {localize(lang, "Обзор", "Overview")}
        </Button>
      </div>
    </div>
  );
}
