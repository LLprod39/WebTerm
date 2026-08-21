import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";
import {
  adaptPlaybookCompatibility,
  adaptPlaybookSource,
  analyzePlaybookCompatibility,
  analyzePlaybookSource,
  applyPlaybookCompatibility,
  type PlaybookCompatibilityReport,
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
  canAdapt?: boolean;
  onApplied: (playbook: PlaybookDetail) => void;
  onSourceAccepted?: (sourceYaml: string, report: PlaybookCompatibilityReport) => void;
}

export function PlaybookCompatibilityPanel({
  lang,
  playbookId,
  sourceYaml,
  report: initialReport,
  canAdapt = true,
  onApplied,
  onSourceAccepted,
}: PlaybookCompatibilityPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [report, setReport] = useState<PlaybookCompatibilityReport>(initialReport || {});
  const [busy, setBusy] = useState<"analyze" | "adapt" | "apply" | null>(null);
  const [lastFailure, setLastFailure] = useState("");
  const [proposal, setProposal] = useState<
    Awaited<ReturnType<typeof adaptPlaybookCompatibility>>["proposal"] | null
  >(null);

  useEffect(() => setReport(initialReport || {}), [initialReport]);

  useEffect(() => setProposal(null), [canAdapt, playbookId, sourceYaml]);

  useEffect(() => {
    if (!playbookId || !sourceYaml || (initialReport?.analyzer_version || 0) >= 3) return;
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
    setBusy("analyze");
    setLastFailure("");
    try {
      const result = playbookId
        ? await analyzePlaybookCompatibility(playbookId, { source_yaml: sourceYaml })
        : await analyzePlaybookSource(sourceYaml);
      setReport(result.report || {});
      notify.success({ title: tr("Проверка завершена", "Compatibility checked") });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLastFailure(message);
      notify.error({ title: tr("Проверка не удалась", "Compatibility check failed"), description: message });
    } finally {
      setBusy(null);
    }
  };

  const prepareAdaptation = async () => {
    setBusy("adapt");
    setLastFailure("");
    try {
      const result = playbookId
        ? await adaptPlaybookCompatibility(playbookId)
        : await adaptPlaybookSource(sourceYaml);
      const nextProposal = result.proposal;
      setReport(nextProposal.report || report);
      if (!nextProposal.semantic_guard?.passed || !nextProposal.adapted_yaml) {
        const reason = (nextProposal.semantic_guard?.violations || []).join("; ") || tr("Предложение не прошло semantic guard.", "The proposal did not pass the semantic guard.");
        setLastFailure(reason);
        notify.error({
          title: tr("ИИ-патч отклонён", "AI patch rejected"),
          description: reason,
        });
        return;
      }
      setProposal(nextProposal);
      notify.success({
        title: tr("Предложение готово к проверке", "Proposal ready for review"),
        description: tr(
          "Изменения ещё не применены. Проверьте YAML и подтвердите отдельно.",
          "Nothing has been applied yet. Review the YAML and confirm separately.",
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

  const applyProposal = async () => {
    if (!proposal?.semantic_guard?.passed || !proposal.adapted_yaml) return;
    setBusy("apply");
    setLastFailure("");
    try {
      if (!playbookId) {
        onSourceAccepted?.(proposal.adapted_yaml, proposal.report || {});
        setReport(proposal.report || {});
      } else {
        const applied = await applyPlaybookCompatibility(playbookId, {
          adapted_yaml: proposal.adapted_yaml,
          changes: proposal.changes,
        });
        onApplied(applied.playbook);
        setReport(applied.revision.report || {});
      }
      setProposal(null);
      notify.success({
        title: playbookId ? tr("Адаптация сохранена в черновик", "Adaptation saved to draft") : tr("Адаптация добавлена в редактор", "Adaptation added to the editor"),
        description: tr(
          "Проверьте текст и сохраните Ansible, когда будете готовы.",
          "Review the text and save the Ansible when ready.",
        ),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLastFailure(message);
      notify.error({ title: tr("Не удалось применить предложение", "Failed to apply proposal"), description: message });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4 shadow-elev-1">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{tr("AI-проверка", "AI check")}</h3>
            <span className={cn("rounded-sm border px-2 py-0.5 text-2xs font-medium", statusMeta.className)}>
              {statusMeta.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr(
              "Проверим YAML. Если нужна адаптация, вы сначала увидите предложение и только потом примените его.",
              "Check the YAML. If adaptation is needed, you review the proposal before applying it.",
            )}
          </p>
        </div>
        <Button size="sm" variant="outline" className="h-8 gap-1.5" disabled={busy !== null || Boolean(proposal)} onClick={() => void analyze()}>
          <RefreshCw className={cn("h-3.5 w-3.5", busy === "analyze" && "animate-spin")} />
          {tr("Проверить", "Analyze")}
        </Button>
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

      {proposal && canAdapt ? (
        <section className="space-y-3 rounded-sm border border-primary/30 bg-primary/5 p-3" aria-label={tr("Проверка предложения", "Proposal review")}>
          <div>
            <h4 className="text-sm font-semibold text-foreground">{tr("Проверьте изменения перед применением", "Review before applying")}</h4>
            <p className="mt-1 text-xs text-muted-foreground">
              {tr("Ни одно изменение ещё не применено.", "No changes have been applied yet.")}
            </p>
          </div>
          {(proposal.changes || []).length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              {proposal.changes.map((change, index) => <li key={`${change}-${index}`}>{change}</li>)}
            </ul>
          ) : null}
          <details className="rounded-sm border border-border bg-surface-0">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-foreground">
              {tr("Показать предложенный YAML", "Show proposed YAML")}
            </summary>
            <pre className="max-h-80 overflow-auto border-t border-border p-3 font-mono text-xs text-foreground whitespace-pre-wrap">
              {proposal.adapted_yaml}
            </pre>
          </details>
          <div className="flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => setProposal(null)}>
              {tr("Отклонить", "Discard")}
            </Button>
            <Button size="sm" disabled={busy !== null} onClick={() => void applyProposal()}>
              {busy === "apply" ? tr("Применение…", "Applying…") : tr("Применить проверенное предложение", "Apply reviewed proposal")}
            </Button>
          </div>
        </section>
      ) : null}

      {canAdapt && status !== "ready" ? (
        <div className="space-y-2 border-t border-border pt-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-2xl text-xs text-muted-foreground">
              {tr(
                hasErrors
                  ? "Система подготовит ограниченное предложение. Перед применением вы увидите изменения и полный YAML."
                  : "WebTerm подготовит предложение с учётом ограничений и отчёта. Применение всегда требует отдельного подтверждения.",
                hasErrors
                  ? "WebTerm will prepare a bounded proposal. You will review the changes and full YAML before applying it."
                  : "WebTerm will prepare a proposal using its constraints and report. Applying always requires separate confirmation.",
              )}
            </p>
            <Button
              size="sm"
              className="h-9 gap-1.5"
              disabled={busy !== null || Boolean(proposal)}
              onClick={() => void prepareAdaptation()}
            >
              <Bot className="h-3.5 w-3.5" />
              {busy === "adapt" ? tr("Подготовка…", "Preparing…") : tr("Подготовить адаптацию", "Prepare adaptation")}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
