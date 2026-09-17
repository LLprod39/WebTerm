import { Sparkles } from "lucide-react";

import { StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import type { ExplainLogsResult } from "./types";

export function ExplainLogsPanel({
  lang,
  result,
}: {
  lang: string;
  result: ExplainLogsResult | null;
}) {
  if (!result) {
    return (
      <div
        data-ui-slot="cockpit-explain"
        className="border-t border-border bg-card px-6 py-6 text-base leading-7 text-muted-foreground"
      >
        <div className="flex flex-wrap items-center gap-2 text-foreground">
          <Sparkles className="h-4 w-4" aria-hidden />
          <span className="text-lg font-semibold">{localize(lang, "ИИ · разбор логов", "AI · log analysis")}</span>
        </div>
        <p className="mt-2 max-w-3xl">
          {localize(
            lang,
            "Нажмите «Разобрать логи». ИИ только предлагает гипотезу и проверки — кластер не меняет.",
            "Click “Explain logs”. AI only proposes a hypothesis and checks — it never changes the cluster.",
          )}
        </p>
      </div>
    );
  }

  return (
    <div data-ui-slot="cockpit-explain" className="space-y-4 border-t border-border bg-card px-5 py-5">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="h-4 w-4 text-foreground" aria-hidden />
        <h3 className="text-base font-semibold text-foreground">
          {localize(lang, "ИИ · разбор логов", "AI · log explain")}
        </h3>
        <StatusBadge
          label={result.confidence}
          tone={result.confidence === "high" ? "success" : result.confidence === "medium" ? "warning" : "neutral"}
        />
        {result.signals.map((signal) => (
          <StatusBadge key={signal} label={signal} tone="info" dot={false} className="normal-case tracking-normal" />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h4 className="text-sm font-semibold text-foreground">{localize(lang, "Гипотеза", "Likely cause")}</h4>
          <p className="mt-1 text-base leading-7 text-foreground/90">{result.likelyCause}</p>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-foreground">{localize(lang, "Кратко", "Summary")}</h4>
          <p className="mt-1 text-base leading-7 text-muted-foreground">{result.summary}</p>
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-foreground">{localize(lang, "Что проверить", "Suggested checks")}</h4>
        <ol className="mt-2 list-decimal space-y-2 pl-5 text-base leading-7 text-foreground/90">
          {result.suggestedChecks.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>

      <p className="border-t border-border pt-3 text-xs text-muted-foreground">{result.disclaimer}</p>
    </div>
  );
}
