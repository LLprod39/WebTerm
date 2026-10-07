import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";

import { NODE_PALETTE } from "@/components/pipeline/nodes";
import { getNodePaletteText } from "@/components/pipeline/nodes/nodeMeta";
import { Input } from "@/components/ui/input";

import { localize } from "./presentation";

export type QuickPickerPosition = {
  /** Screen (client) coordinates for fixed positioning. */
  x: number;
  y: number;
  /** Optional flow coordinates when the caller already converted. */
  flowX?: number;
  flowY?: number;
};

type PaletteEntry = {
  type: string;
  label: string;
  description: string;
  category: string;
};

function collectPaletteEntries(lang: "en" | "ru"): PaletteEntry[] {
  return (
    NODE_PALETTE as Array<{
      category: string;
      nodes: Array<{ type: string; label: string; description: string }>;
    }>
  ).flatMap((group) =>
    group.nodes.map((node) => {
      const text = getNodePaletteText(node.type, lang);
      return {
        type: node.type,
        label: text.label === node.type ? node.label : text.label,
        description: text.label === node.type ? node.description : text.description,
        category: group.category,
      };
    }),
  );
}

export function QuickNodePicker({
  open,
  position,
  onPick,
  onClose,
  lang = "en",
  excludeTriggers = false,
}: {
  open: boolean;
  position: QuickPickerPosition | null;
  onPick: (type: string) => void;
  onClose: () => void;
  lang?: "en" | "ru";
  /** When connecting from a handle / inserting on an edge, hide trigger types. */
  excludeTriggers?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setSearch("");
      setActive(0);
      return;
    }
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const entries = useMemo(() => {
    const query = search.trim().toLowerCase();
    return collectPaletteEntries(lang).filter((entry) => {
      if (excludeTriggers && entry.type.startsWith("trigger/")) return false;
      if (!query) return true;
      return (
        entry.label.toLowerCase().includes(query) ||
        entry.description.toLowerCase().includes(query) ||
        entry.type.toLowerCase().includes(query) ||
        entry.category.toLowerCase().includes(query)
      );
    });
  }, [excludeTriggers, lang, search]);

  useEffect(() => {
    setActive(0);
  }, [search, excludeTriggers]);

  if (!open || !position) return null;

  const select = (index: number) => {
    const entry = entries[index];
    if (entry) onPick(entry.type);
  };

  const left = Math.min(
    Math.max(8, position.x),
    typeof window !== "undefined" ? window.innerWidth - 288 : position.x,
  );
  const top = Math.min(
    Math.max(8, position.y),
    typeof window !== "undefined" ? window.innerHeight - 360 : position.y,
  );

  return (
    <div
      className="fixed z-[80] w-72 overflow-hidden rounded-md border border-border/80 bg-popover/98 shadow-lg"
      style={{ left, top }}
      role="dialog"
      aria-label={localize(lang, "Добавить шаг", "Add step")}
    >
      <div className="flex items-center gap-2 border-b border-border/70 px-2 py-2">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <Input
          ref={inputRef}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={localize(lang, "Поиск…", "Search…")}
          className="h-7 border-0 bg-transparent px-0 text-xs shadow-none focus-visible:ring-0"
          aria-label={localize(lang, "Поиск шагов", "Search steps")}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((value) => Math.min(value + 1, Math.max(entries.length - 1, 0)));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((value) => Math.max(value - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              select(active);
            } else if (event.key === "Escape") {
              event.preventDefault();
              onClose();
            }
          }}
        />
        <button
          type="button"
          aria-label={localize(lang, "Закрыть", "Close")}
          className="grid h-6 w-6 shrink-0 place-items-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={onClose}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="max-h-72 overflow-auto p-1">
        {entries.map((entry, index) => (
          <button
            key={entry.type}
            type="button"
            className={`flex w-full flex-col rounded px-2.5 py-2 text-left transition-colors ${
              index === active ? "bg-primary/10 text-foreground" : "hover:bg-muted/50"
            }`}
            onMouseEnter={() => setActive(index)}
            onClick={() => onPick(entry.type)}
          >
            <span className="truncate text-[12px] font-medium">{entry.label}</span>
            <span className="truncate text-[11px] text-muted-foreground">{entry.description}</span>
          </button>
        ))}
        {!entries.length ? (
          <p className="px-2.5 py-3 text-xs text-muted-foreground">
            {localize(lang, "Ничего не найдено.", "No matching steps.")}
          </p>
        ) : null}
      </div>
    </div>
  );
}
