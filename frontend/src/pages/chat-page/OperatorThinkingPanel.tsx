import { useEffect, useState } from "react";

import { localize, useI18n } from "@/lib/i18n";

import type { StreamToolStep } from "./useOperatorChatWs";

export type ThinkingPhase = "thinking" | "tools" | "streaming" | "idle";

type Props = {
  phase: ThinkingPhase;
  startedAt: number | null;
  iteration?: number | null;
  reasoningText?: string;
  toolSteps?: StreamToolStep[];
  compact?: boolean;
};

function formatElapsed(ms: number) {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Quiet one-line activity — same language as inventory panels. */
export function OperatorThinkingPanel({
  phase,
  startedAt,
  toolSteps = [],
  compact = false,
}: Props) {
  const { lang } = useI18n();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!startedAt || phase === "idle") return;
    const t = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(t);
  }, [startedAt, phase]);

  if (phase === "idle") return null;

  const elapsed = startedAt ? formatElapsed(now - startedAt) : "";
  const running = toolSteps.find((s) => s.status === "running");

  let label = localize(lang, "думает", "thinking");
  if (phase === "tools") {
    label = running
      ? running.name
      : localize(lang, "tools", "tools");
  } else if (phase === "streaming") {
    label = localize(lang, "пишет", "writing");
  }

  return (
    <div
      className={
        compact
          ? "text-[11px] text-muted-foreground/75"
          : "text-[12px] text-muted-foreground"
      }
    >
      <span className="inline-flex items-baseline gap-1.5">
        <span className="h-1 w-1 shrink-0 self-center rounded-full bg-muted-foreground/50" />
        <span>{label}</span>
        {elapsed ? <span className="font-mono tabular-nums text-muted-foreground/60">{elapsed}</span> : null}
      </span>
    </div>
  );
}
