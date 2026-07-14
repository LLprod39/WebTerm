import { Link } from "react-router-dom";
import { Activity, FileText, Terminal, X } from "lucide-react";

import type { AgentRunResult } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { agentRunStatusPresentation } from "@/design/status";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

function formatDuration(ms: number): string {
  if (!ms) return "--";
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ${secs % 60}s`;
}

function summarizeReport(text: string): string {
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !line.startsWith("#") && !line.startsWith("---"));
  const firstContent = lines.find((line) => line.replace(/^[-*]\s+/, "").trim());
  return firstContent ? firstContent.replace(/^[-*]\s+/, "").trim() : "";
}

export function AgentReportModal({
  result,
  open,
  onClose,
}: {
  result: AgentRunResult;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const reportText = result.final_report || result.ai_analysis || "";
  const summary = summarizeReport(reportText);
  const status = agentRunStatusPresentation(result.status);
  const tr = (key: string, vars?: Record<string, string | number>) => {
    let text = t(key);
    if (!vars) return text;
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
    return text;
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-[min(92vw,560px)] gap-0 overflow-hidden rounded-sm border-border bg-card p-0 shadow-elev-3">
        <DialogDescription className="sr-only">{t("run.report_modal_desc")}</DialogDescription>
        <div aria-hidden className="h-0.5 w-full bg-primary" />
        <div className="flex items-start gap-3 border-b border-border px-5 py-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-primary/30 bg-primary/10 text-primary">
            <FileText className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="type-label text-muted-foreground">Mini · отчёт</p>
            <DialogTitle className="mt-1 truncate font-display text-lg font-bold tracking-tight text-foreground">
              {tr("run.report_for_server", { server: result.server_name })}
            </DialogTitle>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge label={t(status.labelKey)} tone={status.tone} pulse={status.pulse} />
              <span className="inline-flex min-h-7 items-center gap-1.5 rounded-sm border border-border bg-surface-0 px-2.5 py-1 text-xs font-medium text-muted-foreground">
                <Activity className="h-3.5 w-3.5" />
                {formatDuration(result.duration_ms)}
              </span>
              {result.commands_output.length ? (
                <span className="inline-flex min-h-7 items-center gap-1.5 rounded-sm border border-border bg-surface-0 px-2.5 py-1 text-xs font-medium text-muted-foreground">
                  <Terminal className="h-3.5 w-3.5" />
                  {tr("run.commands_count", { count: result.commands_output.length })}
                </span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label={t("agent.close_report")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 py-6">
          {summary ? (
            <p className="text-[15px] leading-7 text-foreground/90">{summary}</p>
          ) : (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <FileText className="mb-3 h-10 w-10 text-muted-foreground/35" />
              <p className="text-sm text-muted-foreground">{t("run.no_report")}</p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-border bg-surface-0 px-5 py-4">
          <Button variant="outline" onClick={onClose}>
            {t("agent.close_report")}
          </Button>
          {result.run_id > 0 ? (
            <Button asChild className="shadow-elev-1">
              <Link to={`/agents/run/${result.run_id}`}>{t("run.open_full_report")}</Link>
            </Button>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
