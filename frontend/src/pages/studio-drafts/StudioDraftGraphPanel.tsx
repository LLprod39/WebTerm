import { DraftGraphCanvas } from "@/components/studio/DraftGraphCanvas";
import { cn } from "@/lib/utils";
import type { StudioPipelineDraftSession } from "@/lib/studioPipelineDraftsApi";

import type { StudioDraftMobilePane } from "./studioDraftsModel";

export function StudioDraftGraphPanel({
  lang,
  mobilePane,
  activeDraft,
  loading,
}: {
  lang: string;
  mobilePane: StudioDraftMobilePane;
  activeDraft: StudioPipelineDraftSession | null;
  loading: boolean;
}) {
  return (
    <main className={cn("min-h-[520px] min-w-0 border-b border-border/70 xl:block xl:min-h-0 xl:border-b-0", mobilePane === "graph" ? "block" : "hidden")}>
      <DraftGraphCanvas session={activeDraft} lang={lang} loading={loading} />
    </main>
  );
}
