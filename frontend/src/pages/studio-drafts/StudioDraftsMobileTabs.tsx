import { Button } from "@/components/ui/button";
import { localize } from "@/lib/i18n";

import { STUDIO_DRAFT_MOBILE_PANES, type StudioDraftMobilePane } from "./studioDraftsModel";

export function StudioDraftsMobileTabs({
  lang,
  mobilePane,
  onMobilePaneChange,
}: {
  lang: string;
  mobilePane: StudioDraftMobilePane;
  onMobilePaneChange: (pane: StudioDraftMobilePane) => void;
}) {
  return (
    <div className="grid grid-cols-4 gap-1 border-b border-border/70 bg-card/35 p-2 xl:hidden">
      {STUDIO_DRAFT_MOBILE_PANES.map((item) => (
        <Button
          key={item.value}
          type="button"
          variant={mobilePane === item.value ? "secondary" : "ghost"}
          size="sm"
          className="h-9 min-w-0 px-2 text-xs"
          aria-pressed={mobilePane === item.value}
          onClick={() => onMobilePaneChange(item.value)}
        >
          <span className="truncate">{localize(lang, item.labelRu, item.labelEn)}</span>
        </Button>
      ))}
    </div>
  );
}
