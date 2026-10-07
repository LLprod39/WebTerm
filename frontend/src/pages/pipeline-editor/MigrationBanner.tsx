import { LayoutGrid, X } from "lucide-react";

import { Button } from "@/components/ui/button";

import { localize } from "./presentation";

export function MigrationBanner({
  lang,
  onOrganize,
  onDismiss,
}: {
  lang: "en" | "ru";
  onOrganize: () => void;
  onDismiss: () => void;
}) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-2 border-b border-border/80 bg-muted/40 px-3 py-2 text-xs text-muted-foreground sm:px-4"
    >
      <LayoutGrid className="h-3.5 w-3.5 shrink-0 text-foreground/70" aria-hidden />
      <p className="min-w-0 flex-1 leading-5">
        {localize(
          lang,
          "Граф выглядит сверху вниз. Выровнять слева направо?",
          "This graph looks top-to-bottom. Organize left-to-right?",
        )}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" className="h-8 gap-1.5" onClick={onOrganize}>
          {localize(lang, "Выровнять слева направо", "Organize left to right")}
        </Button>
        <Button size="sm" variant="ghost" className="h-8 gap-1.5" onClick={onDismiss}>
          {localize(lang, "Оставить как есть", "Keep as is")}
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 text-muted-foreground"
          onClick={onDismiss}
          aria-label={localize(lang, "Скрыть", "Dismiss")}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
