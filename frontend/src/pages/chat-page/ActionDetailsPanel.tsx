import { Link } from "react-router-dom";
import { MapPin, ShieldCheck, Terminal } from "lucide-react";

import type { AssistantAction } from "@/api";
import { Button } from "@/components/ui/button";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import {
  actionCommandLine,
  actionResultOutput,
  actionServerLabel,
  actionTargetLabel,
} from "./actionPreview";
import { actionRiskLabel, actionStatusLabel, statusTone } from "./chatHelpers";

type Props = {
  action: AssistantAction | null;
  hasSession?: boolean;
  onOpenTerminal?: () => void;
};

/**
 * Full action inspector for the Context Rail `details` tab.
 * Stream shows a compact chip; this panel holds description / where / command / result.
 */
export function ActionDetailsPanel({ action, hasSession, onOpenTerminal }: Props) {
  const { lang } = useI18n();

  if (!action) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-[12px] text-muted-foreground">
        {localize(
          lang,
          "Выберите действие в чате, чтобы увидеть детали.",
          "Select an action in the chat to see details.",
        )}
      </div>
    );
  }

  const server = actionServerLabel(action);
  const blast = (action.blast_radius || {}) as Record<string, unknown>;
  const serverNames = Array.isArray(blast.server_names)
    ? blast.server_names.map(String).filter(Boolean)
    : [];
  const serverIds = Array.isArray(blast.server_ids) ? blast.server_ids : [];
  const targetCount = Number(blast.count || serverIds.length || serverNames.length || 0);
  const cmd = actionCommandLine(action);
  const output = action.status === "completed" ? actionResultOutput(action) : "";
  const target = actionTargetLabel(action);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 border-b border-border/50 px-3 py-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold tracking-tight text-foreground">
              {action.title || action.action_type}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-muted-foreground/65">
              {action.action_type}
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-1">
            <span className={cn("rounded-sm border px-1.5 py-0.5 text-[10px] font-medium", statusTone(action.status))}>
              {actionStatusLabel(action.status, lang)}
            </span>
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[10px] font-medium",
                action.risk === "dangerous"
                  ? "border-destructive/35 bg-destructive/10 text-destructive"
                  : action.risk === "read"
                    ? "border-success/30 bg-success/10 text-success"
                    : "border-warning/30 bg-warning/10 text-warning",
              )}
            >
              <ShieldCheck className="h-3 w-3" />
              {actionRiskLabel(action.risk, lang)}
            </span>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {action.description ? (
          <section>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {localize(lang, "Что произойдёт", "What will happen")}
            </div>
            <p className="mt-1 text-[12px] leading-5 text-foreground/90">{action.description}</p>
          </section>
        ) : null}

        {target || server || targetCount > 0 ? (
          <section className="rounded-sm border border-border/50 bg-background/45 px-3 py-2">
            <div className="flex items-start gap-2">
              <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                  {localize(lang, "Где", "Where")}
                </div>
                <div className="mt-0.5 break-words text-[12px] font-medium text-foreground">
                  {target || server || localize(lang, `${targetCount} целей`, `${targetCount} targets`)}
                </div>
                {targetCount > 1 ? (
                  <div className="mt-0.5 text-[10.5px] text-warning">
                    {localize(lang, `Охват: ${targetCount} целей`, `Blast radius: ${targetCount} targets`)}
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        ) : null}

        {cmd ? (
          <section>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {localize(lang, "Команда / операция", "Command / operation")}
            </div>
            <pre className="mt-1 overflow-x-auto rounded-sm border border-border/50 bg-background/60 px-3 py-2 font-mono text-[11px] leading-4 text-foreground">
              $ {cmd}
            </pre>
          </section>
        ) : null}

        {output ? (
          <section>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {localize(lang, "Результат", "Result")}
            </div>
            <pre className="mt-1 max-h-[min(50vh,24rem)] overflow-auto whitespace-pre-wrap break-words rounded-sm border border-success/20 bg-success/[0.04] px-3 py-2 font-mono text-[10.5px] leading-4 text-muted-foreground/90">
              {output.length > 12000 ? `${output.slice(0, 12000)}\n…` : output}
            </pre>
          </section>
        ) : null}

        {action.error ? (
          <p className="text-[11px] text-destructive/90">{action.error}</p>
        ) : null}
      </div>

      {(action.target_url && action.status === "completed") || (hasSession && onOpenTerminal) ? (
        <div className="flex shrink-0 flex-wrap gap-2 border-t border-border/50 px-3 py-2">
          {hasSession && onOpenTerminal ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 gap-1.5 px-2 text-[11px]"
              onClick={onOpenTerminal}
            >
              <Terminal className="h-3 w-3" />
              {localize(lang, "в терминал", "terminal")}
            </Button>
          ) : null}
          {action.target_url && action.status === "completed" ? (
            <Button asChild size="sm" variant="outline" className="h-7 px-2 text-[11px]">
              <Link to={action.target_url}>{localize(lang, "открыть", "open")}</Link>
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
