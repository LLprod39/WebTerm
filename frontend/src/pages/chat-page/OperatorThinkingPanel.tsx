import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import type { StreamToolStep } from "./useOperatorChatWs";

export type ThinkingPhase = "thinking" | "tools" | "streaming" | "idle";

type Props = {
  phase: ThinkingPhase;
  startedAt: number | null;
  iteration?: number | null;
  reasoningText?: string;
  /** True when real thinking tokens arrived (not only status heartbeats). */
  hasReasoningStream?: boolean;
  /** Backend status line, e.g. "Генерация JSON…". */
  statusMessage?: string;
  toolSteps?: StreamToolStep[];
  compact?: boolean;
  /** Prefer expanded reasoning (user enabled thinking mode). */
  preferExpanded?: boolean;
};

function formatElapsed(ms: number) {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

type ActivityKind = "waiting" | "reasoning" | "generating" | "tools" | "writing";

function resolveActivity(opts: {
  phase: ThinkingPhase;
  hasReasoning: boolean;
  reasoningText: string;
  statusMessage: string;
  hasTools: boolean;
}): ActivityKind {
  if (opts.phase === "tools" || opts.hasTools) return "tools";
  if (opts.phase === "streaming") return "writing";
  if (opts.hasReasoning || opts.reasoningText.trim()) return "reasoning";
  const status = opts.statusMessage.toLowerCase();
  if (status.includes("генерац") || status.includes("generat") || status.includes("симв")) {
    return "generating";
  }
  if (status.includes("без thinking") || status.includes("без размыш")) {
    return "generating";
  }
  return "waiting";
}

/** Minimal GPT/Grok-style activity row: collapsible reasoning, quiet tools. */
export function OperatorThinkingPanel({
  phase,
  startedAt,
  iteration,
  reasoningText = "",
  hasReasoningStream = false,
  statusMessage = "",
  toolSteps = [],
  compact = false,
  preferExpanded = false,
}: Props) {
  const { lang } = useI18n();
  const [now, setNow] = useState(() => Date.now());
  const [expanded, setExpanded] = useState(preferExpanded);
  const scrollRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    if (!startedAt || phase === "idle") return;
    const t = window.setInterval(() => setNow(Date.now()), 400);
    return () => window.clearInterval(t);
  }, [startedAt, phase]);

  useEffect(() => {
    if (!expanded || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [reasoningText, expanded]);

  useEffect(() => {
    if (hasReasoningStream || reasoningText.trim()) {
      setExpanded(preferExpanded || true);
    }
  }, [hasReasoningStream, reasoningText, preferExpanded]);

  if (phase === "idle") return null;

  const elapsedMs = startedAt ? Math.max(0, now - startedAt) : 0;
  const elapsed = startedAt ? formatElapsed(elapsedMs) : "";
  const running = toolSteps.find((s) => s.status === "running");
  const hasReasoning = hasReasoningStream || Boolean(reasoningText.trim());
  const activity = resolveActivity({
    phase,
    hasReasoning,
    reasoningText,
    statusMessage,
    hasTools: Boolean(running) || phase === "tools",
  });

  const labels: Record<ActivityKind, { ru: string; en: string }> = {
    waiting: { ru: "Думает", en: "Thinking" },
    reasoning: { ru: "Размышляет", en: "Reasoning" },
    generating: { ru: "Пишет", en: "Writing" },
    tools: { ru: running?.name || "Инструменты", en: running?.name || "Tools" },
    writing: { ru: "Пишет", en: "Writing" },
  };

  const label = localize(lang, labels[activity].ru, labels[activity].en);
  const showBody = expanded && (hasReasoning || toolSteps.length > 0 || Boolean(statusMessage));

  return (
    <div className={cn("max-w-[min(42rem,100%)]", compact && "text-[12px]")}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="group inline-flex items-center gap-1.5 rounded-full px-1 py-0.5 text-left text-[13px] text-muted-foreground transition-colors hover:text-foreground"
      >
        {showBody || hasReasoning ? (
          expanded ? (
            <ChevronDown className="h-3.5 w-3.5 opacity-60" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 opacity-60" />
          )
        ) : (
          <Loader2 className="h-3.5 w-3.5 animate-spin opacity-70" />
        )}
        <span className="font-medium tracking-tight">{label}</span>
        {elapsed ? (
          <span className="font-mono text-[11px] tabular-nums text-muted-foreground/70">{elapsed}</span>
        ) : null}
        {iteration != null && iteration > 1 ? (
          <span className="text-[11px] text-muted-foreground/50">· {iteration}</span>
        ) : null}
      </button>

      {showBody ? (
        <div className="mt-1.5 space-y-2 border-l border-border/60 pl-3">
          {statusMessage && !hasReasoning ? (
            <p className="text-[12px] text-muted-foreground/80">{statusMessage}</p>
          ) : null}

          {hasReasoning && reasoningText.trim() ? (
            <pre
              ref={scrollRef}
              className="max-h-36 overflow-y-auto whitespace-pre-wrap break-words font-sans text-[12.5px] leading-relaxed text-muted-foreground/90"
            >
              {reasoningText}
            </pre>
          ) : null}

          {toolSteps.length > 0 ? (
            <ul className="space-y-0.5 text-[12px] text-muted-foreground">
              {toolSteps.slice(-5).map((step) => (
                <li key={step.id} className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      "h-1 w-1 rounded-full",
                      step.status === "running" && "animate-pulse bg-foreground/50",
                      step.status === "done" && "bg-foreground/30",
                      step.status === "error" && "bg-destructive",
                    )}
                  />
                  <span className="font-mono text-[11px]">{step.name}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
