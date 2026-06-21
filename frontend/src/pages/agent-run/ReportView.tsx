import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  Terminal,
} from "lucide-react";

import type { AgentRunDetail } from "@/lib/api";

import { formatDateTime, formatDuration } from "./formatters";
import { StatusBadge } from "./StatusBadge";

export function ReportView({ run, t }: {
  run: AgentRunDetail;
  t: (key: string) => string;
}) {
  const report = run.final_report || run.ai_analysis;
  const isComplete = run.status === "completed";
  const isFailed = run.status === "failed";

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-5 sm:px-6">
      <div className="rounded-lg border border-border/80 bg-card/95">
        <div className="border-b border-border/70 px-5 py-5">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 rounded-md border border-border/70 bg-background/60 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <FileText className="h-3 w-3" />
                {t("run.report_kicker")}
              </div>
              <div className="mt-4 flex items-start gap-3">
                <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border ${isComplete ? "border-emerald-500/25 bg-emerald-500/10" : isFailed ? "border-red-500/25 bg-red-500/10" : "border-border/70 bg-background/60"}`}>
                  {isComplete ? <CheckCircle2 className="h-5 w-5 text-emerald-300" /> : isFailed ? <AlertTriangle className="h-5 w-5 text-red-300" /> : <FileText className="h-5 w-5 text-muted-foreground" />}
                </div>
                <div className="min-w-0">
                  <h2 className="text-2xl font-semibold tracking-normal text-foreground">{run.agent_name}</h2>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {t("run.report_desc")}
                  </p>
                </div>
              </div>
            </div>
            <StatusBadge status={run.status} />
          </div>
        </div>

        <div className="grid gap-3 px-5 py-5 sm:grid-cols-2 xl:grid-cols-4">
          <MetaCard icon={<Clock className="h-3.5 w-3.5" />} label={t("agent.duration")} value={formatDuration(run.duration_ms)} />
          <MetaCard
            icon={<Activity className="h-3.5 w-3.5" />}
            label={run.agent_mode === "multi" ? t("run.tasks") : t("agent.iterations")}
            value={run.agent_mode === "multi" ? String(run.plan_tasks?.length || 0) : String(run.total_iterations)}
          />
          <MetaCard
            icon={<Terminal className="h-3.5 w-3.5" />}
            label={t("run.servers")}
            value={run.connected_servers.length > 0 ? run.connected_servers.map((s) => s.server_name).join(", ") : run.server_name}
          />
          <MetaCard
            icon={<Clock className="h-3.5 w-3.5" />}
            label={isComplete ? t("agent.completed_at") : t("agent.failed_at")}
            value={formatDateTime(run.completed_at)}
          />
        </div>
      </div>

      {run.agent_mode === "mini" && run.commands_output.length > 0 && (
        <div className="rounded-lg border border-border/80 bg-card/95 px-5 py-5">
          <div className="mb-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("run.console_output")}</div>
          <div className="space-y-3">
            {run.commands_output.map((cmd, i) => (
              <div key={i} className="overflow-hidden rounded-lg border border-border/70 bg-[#0f141c]">
                <div className="flex flex-wrap items-center gap-2 border-b border-white/5 bg-white/[0.03] px-4 py-3">
                  <span className="font-mono text-xs text-success">$</span>
                  <span className="min-w-0 flex-1 break-all font-mono text-xs text-foreground">{cmd.cmd}</span>
                  <span className={`rounded-md px-2 py-1 text-xs font-semibold ${cmd.exit_code === 0 ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive"}`}>
                    exit {cmd.exit_code}
                  </span>
                  <span className="text-xs text-muted-foreground">{cmd.duration_ms}ms</span>
                </div>
                {cmd.stdout && <pre className="max-h-56 overflow-x-auto px-4 py-3 font-mono text-xs whitespace-pre-wrap text-foreground/80">{cmd.stdout.slice(0, 4000)}</pre>}
                {cmd.stderr && <pre className="border-t border-destructive/20 px-4 py-3 font-mono text-xs whitespace-pre-wrap text-destructive">{cmd.stderr.slice(0, 800)}</pre>}
              </div>
            ))}
          </div>
        </div>
      )}

      {report ? (
        <div className="rounded-lg border border-border/80 bg-card/95 px-5 py-6">
          <div
            className="
              [&_h1]:mt-0 [&_h1]:mb-4 [&_h1]:text-[26px] [&_h1]:font-semibold [&_h1]:tracking-normal [&_h1]:text-foreground
              [&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:border-b [&_h2]:border-border/50 [&_h2]:pb-2 [&_h2]:text-xs [&_h2]:font-semibold [&_h2]:uppercase [&_h2]:tracking-wide [&_h2]:text-muted-foreground
              [&_h3]:mt-6 [&_h3]:mb-2 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-foreground
              [&_p]:mb-4 [&_p]:text-[15px] [&_p]:leading-8 [&_p]:text-foreground/82
              [&_ul]:mb-5 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-5
              [&_ol]:mb-5 [&_ol]:list-decimal [&_ol]:space-y-2 [&_ol]:pl-5
              [&_li]:text-[15px] [&_li]:leading-8 [&_li]:text-foreground/82
              [&_strong]:font-semibold [&_strong]:text-foreground
              [&_em]:text-foreground/72
              [&_blockquote]:my-6 [&_blockquote]:rounded-r-2xl [&_blockquote]:border-l-2 [&_blockquote]:border-primary/50 [&_blockquote]:bg-background/50 [&_blockquote]:px-5 [&_blockquote]:py-4 [&_blockquote]:text-foreground/72
              [&_code]:rounded-md [&_code]:bg-background/80 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[13px]
              [&_pre]:my-5 [&_pre]:overflow-x-auto [&_pre]:rounded-[20px] [&_pre]:border [&_pre]:border-border/70 [&_pre]:bg-background/80 [&_pre]:p-5 [&_pre]:font-mono [&_pre]:text-[12px] [&_pre]:leading-6 [&_pre]:text-foreground/78
              [&_hr]:my-8 [&_hr]:border-border/40
              [&_table]:my-6 [&_table]:w-full [&_table]:overflow-hidden [&_table]:rounded-2xl [&_table]:border [&_table]:border-border/60
              [&_thead]:bg-background/80
              [&_th]:border-b [&_th]:border-border/60 [&_th]:px-4 [&_th]:py-3 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-muted-foreground
              [&_td]:border-t [&_td]:border-border/40 [&_td]:px-4 [&_td]:py-3 [&_td]:align-top [&_td]:text-[13px] [&_td]:leading-6 [&_td]:text-foreground/82
            "
          >
            <ReactMarkdown>{report}</ReactMarkdown>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border border-border/80 bg-card/95 px-6 py-20 text-center">
          <FileText className="mb-4 h-9 w-9 text-muted-foreground/35" />
          <p className="text-sm text-muted-foreground">
            {["running", "pending"].includes(run.status) ? t("run.report_pending") : t("run.report_unavailable")}
          </p>
        </div>
      )}
    </div>
  );
}

function MetaCard({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/55 px-4 py-4">
      <div className="mb-2 flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-sm font-medium leading-6 text-foreground">{value || "—"}</p>
    </div>
  );
}
