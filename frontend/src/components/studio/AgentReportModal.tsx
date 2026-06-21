import { useState } from "react";
import ReactMarkdown from "react-markdown";
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
  const [activeTab, setActiveTab] = useState<"report" | "console">("report");
  const report = result.final_report || result.ai_analysis || "";
  const hasConsole = result.commands_output.length > 0;
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
      <DialogContent className="flex max-h-[86vh] w-[min(92vw,860px)] flex-col gap-0 overflow-hidden rounded-xl border-border/80 bg-card/95 p-0">
        <DialogDescription className="sr-only">{t("run.report_modal_desc")}</DialogDescription>
        <div className="flex shrink-0 items-start gap-3 border-b border-border px-5 py-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-background/70 text-primary">
            <FileText className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <DialogTitle className="truncate text-base font-semibold text-foreground">
              {tr("run.report_for_server", { server: result.server_name })}
            </DialogTitle>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge label={t(status.labelKey)} tone={status.tone} pulse={status.pulse} />
              <span className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-border/70 bg-secondary/50 px-2.5 py-1 text-xs font-medium text-muted-foreground">
                <Activity className="h-3.5 w-3.5" />
                {formatDuration(result.duration_ms)}
              </span>
              {hasConsole ? (
                <span className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-border/70 bg-secondary/50 px-2.5 py-1 text-xs font-medium text-muted-foreground">
                  <Terminal className="h-3.5 w-3.5" />
                  {tr("run.commands_count", { count: result.commands_output.length })}
                </span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label={t("agent.close_report")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {hasConsole ? (
          <div className="flex shrink-0 border-b border-border bg-background/35 px-5">
            <button
              type="button"
              onClick={() => setActiveTab("report")}
              className={`min-h-11 border-b-2 px-3 text-sm font-medium transition-colors ${activeTab === "report" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              <FileText className="mr-1 inline h-3.5 w-3.5" />
              {t("run.tab_report")}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("console")}
              className={`min-h-11 border-b-2 px-3 text-sm font-medium transition-colors ${activeTab === "console" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              <Terminal className="mr-1 inline h-3.5 w-3.5" />
              {t("run.console_output")}
            </button>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {activeTab === "report" ? (
            <div className="mx-auto max-w-[720px] px-6 py-6 font-sans">
              {report ? (
                <div
                  className="
                    [&_h1]:mb-3 [&_h1]:mt-0 [&_h1]:text-[22px] [&_h1]:font-semibold [&_h1]:leading-snug [&_h1]:text-foreground
                    [&_h2]:mb-3 [&_h2]:mt-8 [&_h2]:border-b [&_h2]:border-border/40 [&_h2]:pb-2 [&_h2]:text-xs [&_h2]:font-semibold [&_h2]:uppercase [&_h2]:tracking-wide [&_h2]:text-muted-foreground
                    [&_h3]:mb-2 [&_h3]:mt-6 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-foreground
                    [&_p]:mb-4 [&_p]:text-[15px] [&_p]:leading-7 [&_p]:text-foreground/85
                    [&_ul]:mb-5 [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5 [&_ul]:marker:text-muted-foreground/60
                    [&_ol]:mb-5 [&_ol]:list-decimal [&_ol]:space-y-1.5 [&_ol]:pl-5 [&_ol]:marker:text-muted-foreground/60
                    [&_li]:text-[15px] [&_li]:leading-7 [&_li]:text-foreground/85
                    [&_strong]:font-semibold [&_strong]:text-foreground
                    [&_code]:rounded [&_code]:bg-secondary/40 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[13px]
                    [&_pre]:my-5 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:border-border/50 [&_pre]:bg-background/80 [&_pre]:p-5 [&_pre]:font-mono [&_pre]:text-xs [&_pre]:text-foreground/80
                    [&_th]:border [&_th]:border-border/30 [&_th]:px-4 [&_th]:py-2.5 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-muted-foreground
                    [&_td]:border [&_td]:border-border/20 [&_td]:px-4 [&_td]:py-3 [&_td]:align-top [&_td]:text-[13px] [&_td]:leading-snug [&_td]:text-foreground/85
                  "
                >
                  <ReactMarkdown>{report}</ReactMarkdown>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <FileText className="mb-3 h-10 w-10 text-muted-foreground/35" />
                  <p className="text-sm text-muted-foreground">{t("run.no_report")}</p>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3 p-4">
              {result.commands_output.map((cmd, i) => (
                <div key={i} className="overflow-hidden rounded-lg border border-border/60 bg-[#0d1117]">
                  <div className="flex items-center gap-2 border-b border-border/20 bg-secondary/10 px-3 py-2">
                    <span className="font-mono text-xs text-success">$</span>
                    <span className="min-w-0 flex-1 break-all font-mono text-xs text-foreground">{cmd.cmd}</span>
                    <span className={`rounded-md px-1.5 py-0.5 text-xs font-semibold ${cmd.exit_code === 0 ? "bg-success/20 text-success" : "bg-destructive/20 text-destructive"}`}>
                      exit {cmd.exit_code}
                    </span>
                    <span className="text-xs text-muted-foreground">{cmd.duration_ms}ms</span>
                  </div>
                  {cmd.stdout ? <pre className="overflow-x-auto whitespace-pre-wrap px-3 py-2.5 font-mono text-xs text-foreground/80">{cmd.stdout}</pre> : null}
                  {cmd.stderr ? <pre className="whitespace-pre-wrap border-t border-destructive/20 px-3 py-2.5 font-mono text-xs text-destructive">{cmd.stderr}</pre> : null}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t border-border bg-background/40 px-5 py-4">
          <Button variant="outline" onClick={onClose}>{t("agent.close_report")}</Button>
          <Button asChild>
            <Link to={`/agents/run/${result.run_id}`}>{t("run.open_full_report")}</Link>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
