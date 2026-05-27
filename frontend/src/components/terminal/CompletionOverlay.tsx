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
    <div className="absolute bottom-4 left-3 z-50 w-72 overflow-hidden rounded-lg border border-white/10 bg-zinc-900/95 shadow-2xl ring-1 ring-black/20 backdrop-blur-md">
      <div className="flex items-center gap-1.5 border-b border-white/5 px-3 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
          {t("terminal.completionTitle")}
        </span>
        <span className="ml-auto rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] tabular-nums text-zinc-500">
          {suggestions.length}
        </span>
      </div>
      <ul ref={listRef} className="max-h-40 overflow-y-auto py-0.5">
        {suggestions.map((cmd, i) => (
          <li
            key={`${i}-${cmd}`}
            className={`flex items-center gap-2 truncate px-3 py-1 font-mono text-[13px] transition-colors ${
              i === selectedIdx
                ? "bg-blue-500/20 text-blue-200"
                : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
            }`}
          >
            <span className="truncate">{cmd}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-2.5 border-t border-white/5 px-3 py-1">
        <kbd className="rounded border border-zinc-700 bg-zinc-800 px-1 py-0.5 text-[9px] font-medium text-zinc-400">↑↓</kbd>
        <span className="text-[10px] text-zinc-500">{t("terminal.completionNav")}</span>
        <kbd className="rounded border border-zinc-700 bg-zinc-800 px-1 py-0.5 text-[9px] font-medium text-zinc-400">Tab</kbd>
        <span className="text-[10px] text-zinc-500">{t("terminal.completionAccept")}</span>
        <kbd className="ml-auto rounded border border-zinc-700 bg-zinc-800 px-1 py-0.5 text-[9px] font-medium text-zinc-400">Esc</kbd>
      </div>
    </div>
  );
};
