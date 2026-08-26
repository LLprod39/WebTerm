import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Pin, Server } from "lucide-react";

import { fetchFrontendBootstrap, type FrontendServer } from "@/api";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { detectComposeTrigger, replaceComposeRange } from "./composeCommands";

export type PinnedServer = { id: number; name: string; host?: string };
export type PinnedUser = { id: number; username: string };

export type ComposePaletteHandle = {
  /** Returns true if the key was handled (parent should not submit). */
  handleKeyDown: (event: React.KeyboardEvent) => boolean;
};

type Props = {
  draft: string;
  caret: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDraftChange: (next: string, caret?: number) => void;
  pinnedServers: PinnedServer[];
  onPinServer: (server: PinnedServer) => void;
  onUnpinServer: (id: number) => void;
};

/**
 * Compose helper: `@` server picker only. Typing `@` opens a server list to pin /
 * mention. No slash commands — plain text goes straight to the operator.
 */
export const ComposeCommandPalette = forwardRef<ComposePaletteHandle, Props>(function ComposeCommandPalette(
  { draft, caret, open, onOpenChange, onDraftChange, pinnedServers, onPinServer, onUnpinServer },
  ref,
) {
  const { lang } = useI18n();
  const [highlight, setHighlight] = useState(0);
  const [filter, setFilter] = useState("");
  const listRef = useRef<HTMLDivElement | null>(null);

  const trigger = useMemo(() => detectComposeTrigger(draft, caret), [draft, caret]);
  // Only `@` mentions drive the picker — `/` is intentionally inert now.
  const mentionTrigger = trigger?.type === "mention" ? trigger : null;

  useEffect(() => {
    if (mentionTrigger) {
      onOpenChange(true);
      setFilter(mentionTrigger.query);
      setHighlight(0);
    } else {
      onOpenChange(false);
    }
  }, [mentionTrigger, onOpenChange]);

  const serversQuery = useQuery({
    queryKey: ["compose", "servers"],
    queryFn: fetchFrontendBootstrap,
    enabled: open && Boolean(mentionTrigger),
    staleTime: 30_000,
  });

  const serverItems = useMemo(() => {
    if (!mentionTrigger) return [];
    const servers = serversQuery.data?.servers || [];
    const q = filter.toLowerCase();
    return servers
      .filter(
        (s) =>
          !q ||
          s.name.toLowerCase().includes(q) ||
          s.host.toLowerCase().includes(q) ||
          String(s.id).includes(q),
      )
      .slice(0, 40);
  }, [filter, mentionTrigger, serversQuery.data?.servers]);

  useEffect(() => {
    setHighlight(0);
  }, [filter]);

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${highlight}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [highlight]);

  const pickServer = useCallback(
    (server: FrontendServer) => {
      onPinServer({ id: server.id, name: server.name, host: server.host });
      if (trigger) {
        const next = replaceComposeRange(draft, trigger.start, trigger.end, `@${server.name} `);
        onDraftChange(next, trigger.start + `@${server.name} `.length);
      }
      onOpenChange(false);
    },
    [draft, onDraftChange, onOpenChange, onPinServer, trigger],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent): boolean => {
      if (!open || !mentionTrigger) return false;
      if (event.key === "Escape") {
        onOpenChange(false);
        return true;
      }
      if (event.key === "ArrowDown") {
        setHighlight((current) => Math.min(Math.max(serverItems.length - 1, 0), current + 1));
        return true;
      }
      if (event.key === "ArrowUp") {
        setHighlight((current) => Math.max(0, current - 1));
        return true;
      }
      if (event.key === "Enter" && !event.shiftKey && serverItems[highlight]) {
        pickServer(serverItems[highlight]);
        return true;
      }
      return false;
    },
    [highlight, mentionTrigger, onOpenChange, open, pickServer, serverItems],
  );

  useImperativeHandle(ref, () => ({ handleKeyDown }), [handleKeyDown]);

  if (!open || !mentionTrigger) return null;

  return (
    <div
      className="absolute bottom-full left-0 right-0 z-30 mb-2 overflow-hidden rounded-2xl border border-border/80 bg-card/95 shadow-xl backdrop-blur-sm"
      role="listbox"
    >
      <div className="flex items-center justify-between border-b border-border/60 px-3 py-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
          <Server className="h-3.5 w-3.5 text-primary" />
          {localize(lang, "Серверы", "Servers")}
        </div>
        <span className="text-2xs text-muted-foreground">↑↓ Enter · Esc</span>
      </div>

      <div ref={listRef} className="max-h-64 overflow-y-auto p-1">
        {serversQuery.isLoading ? (
          <div className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
            {localize(lang, "Загрузка серверов…", "Loading servers…")}
          </div>
        ) : serverItems.length ? (
          serverItems.map((s, idx) => {
            const isPinned = pinnedServers.some((p) => p.id === s.id);
            return (
              <button
                key={s.id}
                type="button"
                data-idx={idx}
                role="option"
                aria-selected={idx === highlight}
                className={cn(
                  "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors",
                  idx === highlight ? "bg-primary/15" : "hover:bg-secondary/50",
                )}
                onMouseEnter={() => setHighlight(idx)}
                onClick={() => (isPinned ? onUnpinServer(s.id) : pickServer(s))}
              >
                <Server className="h-4 w-4 shrink-0 text-primary" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{s.name}</span>
                  <span className="block truncate font-mono text-2xs text-muted-foreground">
                    {s.host}:{s.port} · {s.status}
                  </span>
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-2xs",
                    isPinned
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border/60 text-muted-foreground",
                  )}
                >
                  <Pin className="h-3 w-3" />
                  {isPinned ? localize(lang, "открепить", "unpin") : localize(lang, "прикрепить", "pin")}
                </span>
              </button>
            );
          })
        ) : (
          <div className="px-3 py-6 text-center text-xs text-muted-foreground">
            {localize(lang, "Серверы не найдены", "No servers found")}
          </div>
        )}
      </div>
    </div>
  );
});
