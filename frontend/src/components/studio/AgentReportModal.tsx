import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Activity, AlertTriangle, CheckCircle2, FileText, Terminal, X } from "lucide-react";

import type { AgentRunResult } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { Dialog, DialogContent, DialogDescription } from "@/components/ui/dialog";

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
  const { lang } = useI18n();
  const [activeTab, setActiveTab] = useState<"report" | "console">("report");
  const report = result.final_report || result.ai_analysis || "";
  const hasConsole = result.commands_output.length > 0;
  const isCompleted = result.status === "completed";

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="flex h-[90vh] w-[95vw] max-w-5xl flex-col gap-0 rounded-[1.75rem] p-0">
        <DialogDescription className="sr-only">
          {localize(lang, "Отчёт запуска агента и вывод выполненных команд.", "Agent run report and command output.")}
        </DialogDescription>
        <div className="flex shrink-0 items-center gap-3 border-b border-border bg-card px-5 py-3">
          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${isCompleted ? "bg-green-500/10" : "bg-red-500/10"}`}>
            {isCompleted ? <CheckCircle2 className="h-4 w-4 text-green-400" /> : <AlertTriangle className="h-4 w-4 text-red-400" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-foreground">{localize(lang, "Отчёт агента", "Agent report")} - {result.server_name}</p>
            <div className="mt-0.5 flex items-center gap-3 text-[10px] text-muted-foreground">
              <span className={`font-bold uppercase ${isCompleted ? "text-green-400" : "text-red-400"}`}>{result.status}</span>
              <span className="flex items-center gap-0.5"><Activity className="h-2.5 w-2.5" />{formatDuration(result.duration_ms)}</span>
              {hasConsole && <span className="flex items-center gap-0.5"><Terminal className="h-2.5 w-2.5" />{localize(lang, `${result.commands_output.length} команд`, `${result.commands_output.length} commands`)}</span>}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label={localize(lang, "Закрыть отчёт", "Close report")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {hasConsole && (
          <div className="flex shrink-0 border-b border-border bg-card/50 px-5">
            <button
              type="button"
              onClick={() => setActiveTab("report")}
              className={`min-h-10 border-b-2 px-3 text-xs font-medium transition-colors ${activeTab === "report" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              <FileText className="mr-1 inline h-3 w-3" />{localize(lang, "Отчёт", "Report")}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("console")}
              className={`min-h-10 border-b-2 px-3 text-xs font-medium transition-colors ${activeTab === "console" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              <Terminal className="mr-1 inline h-3 w-3" />{localize(lang, "Консоль", "Console")} ({result.commands_output.length})
            </button>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {activeTab === "report" ? (
            <div className="mx-auto max-w-[720px] px-8 py-8 font-sans">
              {report ? (
                <div
                  className="
                    [&_h1]:mb-3 [&_h1]:mt-0 [&_h1]:text-[22px] [&_h1]:font-bold [&_h1]:leading-snug [&_h1]:text-foreground
                    [&_h2]:mb-3 [&_h2]:mt-9 [&_h2]:border-b [&_h2]:border-border/30 [&_h2]:pb-2 [&_h2]:text-[13px] [&_h2]:font-semibold [&_h2]:uppercase [&_h2]:tracking-widest [&_h2]:text-muted-foreground
                    [&_h3]:mb-2 [&_h3]:mt-6 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-foreground
                    [&_p]:mb-4 [&_p]:text-[15px] [&_p]:leading-[1.8] [&_p]:text-foreground/80
                    [&_ul]:mb-5 [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5 [&_ul]:marker:text-muted-foreground/60
                    [&_ol]:mb-5 [&_ol]:list-decimal [&_ol]:space-y-1.5 [&_ol]:pl-5 [&_ol]:marker:text-muted-foreground/60
                    [&_li]:text-[15px] [&_li]:leading-[1.8] [&_li]:text-foreground/80
                    [&_strong]:font-semibold [&_strong]:text-foreground
                    [&_em]:italic [&_em]:text-foreground/65
                    [&_blockquote]:my-5 [&_blockquote]:rounded-r-lg [&_blockquote]:border-l-4 [&_blockquote]:border-primary/40 [&_blockquote]:bg-secondary/10 [&_blockquote]:py-2 [&_blockquote]:pl-5 [&_blockquote]:text-[15px] [&_blockquote]:text-foreground/70
                    [&_code]:rounded [&_code]:bg-secondary/40 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[13px] [&_code]:text-foreground/85
                    [&_pre]:my-5 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-border/30 [&_pre]:bg-secondary/20 [&_pre]:p-5 [&_pre]:font-mono [&_pre]:text-[12px] [&_pre]:text-foreground/75
                    [&_hr]:my-8 [&_hr]:border-border/25
                    [&_table]:my-6 [&_table]:w-full [&_table]:border-collapse [&_table]:overflow-hidden [&_table]:rounded-lg [&_table]:border [&_table]:border-border/40 [&_table]:text-sm
                    [&_thead]:bg-secondary/40
                    [&_th]:border [&_th]:border-border/30 [&_th]:px-4 [&_th]:py-2.5 [&_th]:text-left [&_th]:text-[11px] [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-muted-foreground
                    [&_td]:border [&_td]:border-border/20 [&_td]:px-4 [&_td]:py-3 [&_td]:align-top [&_td]:text-[13px] [&_td]:leading-snug [&_td]:text-foreground/80
                    [&_tr:nth-child(even)_td]:bg-secondary/10
                    [&_tr:hover_td]:bg-primary/5
                  "
                >
                  <ReactMarkdown>{report}</ReactMarkdown>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <FileText className="mb-3 h-10 w-10 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">{localize(lang, "Отчёт пока пуст", "No report available")}</p>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3 p-4">
              {result.commands_output.map((cmd, i) => (
                <div key={i} className="overflow-hidden rounded-lg border border-border/30 bg-[#0d1117]">
                  <div className="flex items-center gap-2 border-b border-border/20 bg-secondary/10 px-3 py-2">
                    <span className="font-mono text-[11px] text-green-400">$</span>
                    <span className="flex-1 font-mono text-xs text-foreground">{cmd.cmd}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${cmd.exit_code === 0 ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                      exit {cmd.exit_code}
                    </span>
                    <span className="text-[9px] text-muted-foreground">{cmd.duration_ms}ms</span>
                  </div>
                  {cmd.stdout && (
                    <pre className="overflow-x-auto whitespace-pre-wrap px-3 py-2.5 font-mono text-[11px] text-foreground/80">{cmd.stdout}</pre>
                  )}
                  {cmd.stderr && (
                    <pre className="whitespace-pre-wrap border-t border-red-500/10 px-3 py-2.5 font-mono text-[11px] text-red-400/80">{cmd.stderr}</pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
