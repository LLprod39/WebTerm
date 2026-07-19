import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ChevronDown, ChevronRight, Loader2, Sparkles } from "lucide-react";

import type { AdminInsightsAi, AiInsight, AiVerdict, InsightServer } from "@/api/monitoring-insights";
import { StatusBadge } from "@/components/ui/page-shell";
import { useI18n, localize } from "@/lib/i18n";
import { cn, relativeTime } from "@/lib/utils";

const verdictTone: Record<AiVerdict, "success" | "info" | "warning" | "danger" | "neutral"> = {
  low: "success",
  medium: "info",
  high: "warning",
  critical: "danger",
  unknown: "neutral",
};

function verdictLabel(lang: string, verdict: AiVerdict): string {
  const labels: Record<AiVerdict, [string, string]> = {
    low: ["низкий риск", "low risk"],
    medium: ["средний риск", "medium risk"],
    high: ["высокий риск", "high risk"],
    critical: ["критический", "critical"],
    unknown: ["нет вердикта", "no verdict"],
  };
  return localize(lang, labels[verdict][0], labels[verdict][1]);
}

function InsightMarkdown({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none prose-p:my-1.5 prose-headings:mb-1 prose-headings:mt-3 prose-headings:text-xs prose-headings:uppercase prose-headings:tracking-wide prose-p:text-foreground/85 prose-li:my-0.5 prose-li:text-foreground/85 prose-strong:text-foreground">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}

function EndpointRow({ insight, serverNames }: { insight: AiInsight; serverNames: string }) {
  const { lang } = useI18n();
  const [open, setOpen] = useState(false);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <li className="rounded-sm border border-border bg-surface-1/60">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left"
      >
        <Chevron className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">{serverNames}</span>
        <span className="shrink-0 text-2xs text-muted-foreground/70">{relativeTime(insight.created_at)}</span>
        <StatusBadge label={verdictLabel(lang, insight.verdict)} tone={verdictTone[insight.verdict]} dot={false} />
      </button>
      {open ? (
        <div className="border-t border-border px-3 py-2.5">
          {insight.error ? (
            <div className="text-xs text-destructive">{insight.error}</div>
          ) : (
            <InsightMarkdown content={insight.content} />
          )}
        </div>
      ) : null}
    </li>
  );
}

/** Bare AI content for the insights rail: fleet digest + per-endpoint verdicts. */
export function AiAnalysisContent({
  ai,
  servers,
  running,
}: {
  ai: AdminInsightsAi;
  servers: InsightServer[];
  running: boolean;
}) {
  const { lang } = useI18n();

  const namesByEndpoint = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const server of servers) {
      const names = map.get(server.endpoint_key) ?? [];
      names.push(server.name);
      map.set(server.endpoint_key, names);
    }
    return map;
  }, [servers]);

  const endpointInsights = useMemo(() => {
    const rows = Object.values(ai.by_endpoint).filter((row): row is AiInsight => Boolean(row));
    const verdictRank: Record<AiVerdict, number> = { critical: 0, high: 1, medium: 2, unknown: 3, low: 4 };
    rows.sort((a, b) => verdictRank[a.verdict] - verdictRank[b.verdict]);
    return rows;
  }, [ai.by_endpoint]);

  const isBusy = running || ai.running;

  if (!ai.enabled) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
        <Sparkles className="h-5 w-5 text-muted-foreground/50" />
        <p className="text-xs text-muted-foreground">
          {localize(lang, "AI-анализ выключен (AI_INSIGHTS_ENABLED).", "AI analysis is disabled (AI_INSIGHTS_ENABLED).")}
        </p>
      </div>
    );
  }

  if (!ai.fleet && endpointInsights.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
        {isBusy ? (
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground/60" />
        ) : (
          <Sparkles className="h-5 w-5 text-muted-foreground/50" />
        )}
        <p className="text-xs text-muted-foreground">
          {isBusy
            ? localize(lang, "ИИ анализирует флот…", "The AI is analyzing the fleet…")
            : localize(
                lang,
                "ИИ ещё не анализировал флот — нажмите «AI-анализ» сверху.",
                "The AI has not analyzed the fleet yet — click “AI analysis” above.",
              )}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {isBusy ? (
        <div className="flex items-center gap-1.5 text-2xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          {localize(lang, "Обновляю анализ…", "Refreshing analysis…")}
        </div>
      ) : null}
      {ai.fleet ? (
        <div
          className={cn(
            "rounded-sm border px-3 py-2.5",
            ai.fleet.verdict === "critical" || ai.fleet.verdict === "high"
              ? "border-warning/40 bg-warning/5"
              : "border-border bg-surface-1/60",
          )}
        >
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <span className="text-2xs uppercase tracking-[0.12em] text-muted-foreground/70">
              {localize(lang, "Сводка по флоту", "Fleet digest")}
            </span>
            <StatusBadge label={verdictLabel(lang, ai.fleet.verdict)} tone={verdictTone[ai.fleet.verdict]} dot={false} />
            <span className="text-2xs text-muted-foreground/60">{relativeTime(ai.fleet.created_at)}</span>
          </div>
          <InsightMarkdown content={ai.fleet.content} />
        </div>
      ) : null}

      {endpointInsights.length > 0 ? (
        <ul className="space-y-1.5">
          {endpointInsights.map((insight) => (
            <EndpointRow
              key={insight.id}
              insight={insight}
              serverNames={(namesByEndpoint.get(insight.endpoint_key) ?? [insight.endpoint_key]).join(", ")}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
