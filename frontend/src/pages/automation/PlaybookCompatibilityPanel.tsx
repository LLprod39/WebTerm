import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";
import {
  adaptPlaybookCompatibility,
  analyzePlaybookCompatibility,
  applyPlaybookCompatibility,
  type PlaybookCompatibilityReport,
  type PlaybookCompatibilityRevision,
  type PlaybookDetail,
} from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { notify } from "@/lib/notify";
import { cn } from "@/lib/utils";

interface PlaybookCompatibilityPanelProps {
  lang: string;
  playbookId: number | null;
  sourceYaml: string;
  report?: PlaybookCompatibilityReport;
  activeRevision?: PlaybookCompatibilityRevision | null;
  onApplied: (playbook: PlaybookDetail) => void;
}

export function PlaybookCompatibilityPanel({
  lang,
  playbookId,
  sourceYaml,
  report: initialReport,
  activeRevision,
  onApplied,
}: PlaybookCompatibilityPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [report, setReport] = useState<PlaybookCompatibilityReport>(initialReport || {});
  const [busy, setBusy] = useState<"analyze" | "adapt" | null>(null);
  const [lastFailure, setLastFailure] = useState("");

  useEffect(() => setReport(initialReport || {}), [initialReport]);

  useEffect(() => {
    if (!playbookId || !sourceYaml || (initialReport?.analyzer_version || 0) >= 2) return;
    let active = true;
    void analyzePlaybookCompatibility(playbookId)
      .then((result) => {
        if (active) setReport(result.report || {});
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [initialReport?.analyzer_version, playbookId, sourceYaml]);

  const status = report.status || "needs_adaptation";
  const hasErrors = useMemo(() => (report.issues || []).some((issue) => issue.severity === "error"), [report]);
  const statusMeta =
    status === "ready"
      ? { label: tr("Готов", "Ready"), className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400" }
      : status === "blocked"
        ? { label: tr("Заблокирован", "Blocked"), className: "border-destructive/40 bg-destructive/10 text-destructive" }
        : status === "needs_binding"
          ? { label: tr("Нужна привязка", "Binding required"), className: "border-amber-500/30 bg-amber-500/10 text-amber-400" }
          : { label: tr("Нужна адаптация", "Adaptation required"), className: "border-amber-500/30 bg-amber-500/10 text-amber-400" };

  if (!sourceYaml) return null;

  const analyze = async () => {
    if (!playbookId) return;
    setBusy("analyze");
    try {
      const result = await analyzePlaybookCompatibility(playbookId);
      setReport(result.report || {});
      notify.success({ title: tr("Проверка завершена", "Compatibility checked") });
    } catch (error) {
      notify.error({ title: tr("Проверка не удалась", "Compatibility check failed"), description: String(error) });
    } finally {
      setBusy(null);
    }
  };

  const adaptAndApply = async () => {
    if (!playbookId) return;
    setBusy("adapt");
    setLastFailure("");
    try {
      const result = await adaptPlaybookCompatibility(playbookId);
      const proposal = result.proposal;
      setReport(proposal.report || report);
      if (!proposal.semantic_guard?.passed || !proposal.adapted_yaml) {
        notify.error({
          title: tr("ИИ-патч отклонён", "AI patch rejected"),
          description: tr("Предложение изменило защищённую логику.", "The proposal changed protected logic."),
        });
        return;
      }
      const applied = await applyPlaybookCompatibility(playbookId, {
        adapted_yaml: proposal.adapted_yaml,
        changes: proposal.changes,
      });
      onApplied(applied.playbook);
      setReport(applied.revision.report || {});
      notify.success({
        title: tr("Playbook адаптирован", "Playbook adapted"),
        description: tr(
          "Логика сохранена, проверенная ревизия применена автоматически.",
          "Logic was preserved and the validated revision was applied automatically.",
        ),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLastFailure(message);
      notify.error({ title: tr("Автоадаптация не удалась", "Automatic adaptation failed"), description: message });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{tr("Совместимость Ansible", "Ansible compatibility")}</h3>
            <span className={cn("rounded-sm border px-2 py-0.5 text-2xs font-medium", statusMeta.className)}>
              {statusMeta.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr(
              "Оригинал хранится отдельно. ИИ не может изменить задачи, роли, условия или порядок.",
              "The original is preserved. AI cannot change tasks, roles, conditions, or order.",
            )}
          </p>
        </div>
        <Button size="sm" variant="outline" className="h-8 gap-1.5" disabled={!playbookId || busy !== null} onClick={() => void analyze()}>
          <RefreshCw className={cn("h-3.5 w-3.5", busy === "analyze" && "animate-spin")} />
          {tr("Проверить", "Analyze")}
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-sm border border-border bg-surface-0 p-3">
          <div className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Селекторы hosts", "Host selectors")}</div>
          <div className="mt-1 font-mono text-xs text-foreground">{report.host_selectors?.join(", ") || "all"}</div>
        </div>
        <div className="rounded-sm border border-border bg-surface-0 p-3">
          <div className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Переменные", "Required vars")}</div>
          <div className="mt-1 font-mono text-xs text-foreground">{report.required_variables?.join(", ") || "—"}</div>
        </div>
        <div className="rounded-sm border border-border bg-surface-0 p-3">
          <div className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Активная ревизия", "Active revision")}</div>
          <div className="mt-1 font-mono text-xs text-foreground">{activeRevision ? `#${activeRevision.id}` : "—"}</div>
        </div>
      </div>

      {(report.issues || []).length > 0 ? (
        <div className="space-y-1.5">
          {(report.issues || []).slice(0, 8).map((issue, index) => (
            <div
              key={`${issue.code}-${issue.path || index}`}
              className={cn(
                "flex items-start gap-2 rounded-sm border px-3 py-2 text-xs",
                issue.severity === "error"
                  ? "border-destructive/30 bg-destructive/5 text-foreground"
                  : "border-amber-500/20 bg-amber-500/5 text-muted-foreground",
              )}
            >
              <AlertTriangle className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", issue.severity === "error" ? "text-destructive" : "text-amber-400")} />
              <span>{issue.message}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs text-emerald-400">
          <CheckCircle2 className="h-4 w-4" />
          {tr("Статических блокеров не найдено.", "No static blockers found.")}
        </div>
      )}

      {lastFailure ? (
        <div className="rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {lastFailure}
        </div>
      ) : null}

      <div className="space-y-2 border-t border-border pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-2xl text-xs text-muted-foreground">
            {tr(
              hasErrors
                ? "Нажмите один раз: система попробует исправить всё автоматически и сообщит только о блокерах, которые нельзя устранить без файлов или секретов."
                : "Инструкции, ограничения WebTerm и отчёт совместимости уже передаются ИИ автоматически. Ничего вводить не нужно.",
              hasErrors
                ? "Click once: the system will fix everything it safely can and report only blockers that require files or secrets."
                : "WebTerm constraints, instructions, and the compatibility report are supplied to AI automatically.",
            )}
          </p>
          <Button
            size="sm"
            className="h-9 gap-1.5"
            disabled={!playbookId || busy !== null}
            onClick={() => void adaptAndApply()}
          >
            <Bot className="h-3.5 w-3.5" />
            {busy === "adapt" ? tr("ИИ адаптирует и проверяет…", "AI adapting and validating…") : tr("Автоадаптировать", "Auto-adapt")}
          </Button>
        </div>
      </div>
    </div>
  );
}
