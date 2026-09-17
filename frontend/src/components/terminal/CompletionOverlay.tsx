/**
 * Floating autocomplete overlay for terminal command-history suggestions.
 */

import React, { useRef, useEffect } from "react";

import { useI18n } from "@/lib/i18n";

interface CompletionOverlayProps {
  suggestions: string[];
  selectedIdx: number;
  visible: boolean;
}

export const CompletionOverlay: React.FC<CompletionOverlayProps> = ({
  suggestions,
  selectedIdx,
  visible,
}) => {
  const { t } = useI18n();
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const el = listRef.current?.children[selectedIdx] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIdx]);

  if (!visible || suggestions.length === 0) return null;

  return (
    <div className="absolute bottom-4 left-3 z-50 w-72 overflow-hidden rounded-sm border border-border bg-card shadow-elev-2">
      <div className="flex items-center gap-1.5 border-b border-border px-3 py-1.5">
        <span className="text-2xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
          {t("terminal.completionTitle")}
        </span>
        <span className="ml-auto rounded-sm border border-border bg-secondary px-1.5 py-0.5 text-xs tabular-nums text-muted-foreground">
          {suggestions.length}
        </span>
      </div>
      <ul ref={listRef} className="max-h-40 overflow-y-auto py-0.5">
        {suggestions.map((cmd, i) => (
          <li
            key={`${i}-${cmd}`}
            className={`flex items-center gap-2 truncate px-3 py-1 font-mono text-[13px] transition-colors ${
              i === selectedIdx
                ? "bg-primary/15 text-foreground"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground"
            }`}
          >
            <span className="truncate">{cmd}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-2.5 border-t border-border px-3 py-1">
        <kbd className="rounded-sm border border-border bg-secondary px-1 py-0.5 text-xs font-medium text-muted-foreground">↑↓</kbd>
        <span className="text-xs text-muted-foreground">{t("terminal.completionNav")}</span>
        <kbd className="rounded-sm border border-border bg-secondary px-1 py-0.5 text-xs font-medium text-muted-foreground">Tab</kbd>
        <span className="text-xs text-muted-foreground">{t("terminal.completionAccept")}</span>
        <kbd className="ml-auto rounded-sm border border-border bg-secondary px-1 py-0.5 text-xs font-medium text-muted-foreground">Esc</kbd>
      </div>
    </div>
  );
};
