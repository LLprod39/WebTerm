import { AlertTriangle, CheckCircle2, ChevronDown, Loader2, RefreshCw, XCircle } from "lucide-react";

import type { PlaybookRunValidation, PlaybookValidationStage } from "@/api/playbook-preflight";
import type { PlaybookBindingProfile, PlaybookRevision } from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RunPolicyOptions, RunTargetContext } from "../runPreflightState";

interface ReviewValidationStepProps {
  lang: string;
  playbookName: string;
  revision: PlaybookRevision | null;
  bindingProfile: PlaybookBindingProfile | null;
  context: RunTargetContext;
  extraVars: Record<string, unknown>;
  policy: RunPolicyOptions;
  validation: PlaybookRunValidation | null;
  validating: boolean;
  validationError: string;
  onRetry: () => void;
}

export function ReviewValidationStep({
  lang,
  playbookName,
  revision,
  bindingProfile,
  context,
  extraVars,
  policy,
  validation,
  validating,
  validationError,
  onRetry,
}: ReviewValidationStepProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const ready = validation?.status === "ready";
  const targetCount = context.serverIds.length + context.groupIds.length;
  const technicalStages = Object.entries(validation?.stages || {}).filter(
    ([name, stage]) => !(name === "bundle" && stage.status === "not_attached"),
  );

  return (
    <section className="overflow-hidden rounded-xl border border-border/80 bg-card/55" aria-labelledby="validation-title">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-5 py-4">
        <div>
          <h2 id="validation-title" className="text-base font-semibold text-foreground">
            {tr("Проверка перед запуском", "Pre-run check")}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr("WebTerm проверяет именно выбранную версию и цели.", "WebTerm validates the exact revision and targets you selected.")}
          </p>
        </div>
        {!validating ? (
          <Button size="sm" variant="ghost" className="h-8 gap-1.5" onClick={onRetry}>
            <RefreshCw className="h-3.5 w-3.5" />
            {tr("Проверить снова", "Check again")}
          </Button>
        ) : null}
      </div>

      {validating ? (
        <div className="flex min-h-56 flex-col items-center justify-center px-5 py-10 text-center" role="status">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Loader2 className="h-5 w-5 animate-spin" />
          </span>
          <p className="mt-4 text-sm font-medium text-foreground">{tr("Проверяем конфигурацию…", "Checking configuration…")}</p>
          <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
            {tr("Синтаксис, готовность запуска, параметры и выбранные серверы.", "Syntax, execution readiness, settings, and selected servers.")}
          </p>
        </div>
      ) : validationError ? (
        <div role="alert" className="flex min-h-56 flex-col items-center justify-center px-5 py-10 text-center">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <XCircle className="h-5 w-5" />
          </span>
          <p className="mt-4 text-sm font-semibold text-foreground">{tr("Не удалось завершить проверку", "The check could not finish")}</p>
          <p className="mt-1 max-w-xl text-xs leading-5 text-muted-foreground">{validationError}</p>
          <Button size="sm" variant="outline" className="mt-4" onClick={onRetry}>{tr("Повторить", "Retry")}</Button>
        </div>
      ) : validation ? (
        <>
          <div className={cn(
            "flex flex-col items-center px-5 py-8 text-center",
            ready ? "bg-success/[0.035]" : "bg-destructive/[0.035]",
          )}>
            <span className={cn(
              "flex h-12 w-12 items-center justify-center rounded-full",
              ready ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
            )}>
              {ready ? <CheckCircle2 className="h-6 w-6" /> : <XCircle className="h-6 w-6" />}
            </span>
            <h3 className="mt-4 text-lg font-semibold text-foreground">
              {ready ? tr("Можно запускать", "Ready to run") : tr("Нужно исправить настройки", "Settings need attention")}
            </h3>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              {ready
                ? tr("Проверка пройдена. Конфигурация зафиксирована для этого запуска.", "All checks passed. This configuration is locked for the run.")
                : tr("Проект нельзя запустить, пока остаются блокирующие проблемы.", "The project cannot run while blocking issues remain.")}
            </p>
          </div>

          <dl className="grid border-y border-border/70 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryItem label={tr("Проект", "Project")} value={playbookName} />
            <SummaryItem label={tr("Версия", "Revision")} value={revision ? `#${revision.revision_number}` : "—"} />
            <SummaryItem label={tr("Цели", "Targets")} value={tr(`${targetCount} выбрано`, `${targetCount} selected`)} />
            <SummaryItem label={tr("Режим", "Mode")} value={policy.dryRun ? "Dry-run" : tr("Обычный", "Standard")} />
          </dl>

          {validation.issues?.length ? (
            <div className="divide-y divide-border/70 px-5">
              {validation.issues.map((issue, index) => (
                <div key={`${issue.code}-${index}`} className="flex items-start gap-3 py-4">
                  <AlertTriangle className={cn("mt-0.5 h-4 w-4 shrink-0", issue.severity === "error" ? "text-destructive" : "text-warning")} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">{issue.message}</p>
                    {issue.remediation ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{issue.remediation}</p> : null}
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          <details className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3 text-xs text-muted-foreground marker:content-none hover:text-foreground">
              <span>{tr("Технические детали", "Technical details")} · #{validation.id}</span>
              <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
            </summary>
            <div className="grid gap-px border-t border-border/70 bg-border/70 sm:grid-cols-2 lg:grid-cols-3">
              {technicalStages.map(([name, stage]) => (
                <ValidationStageRow key={name} lang={lang} name={name} stage={stage} />
              ))}
              <div className="bg-card px-4 py-3 text-xs">
                <p className="text-muted-foreground">{tr("Профиль", "Profile")}</p>
                <p className="mt-1 truncate text-foreground">{bindingProfile?.name || tr("Разовый выбор", "Ad-hoc")}</p>
              </div>
              <div className="bg-card px-4 py-3 text-xs">
                <p className="text-muted-foreground">{tr("Переменные", "Variables")}</p>
                <p className="mt-1 text-foreground">{Object.keys(extraVars).length || tr("Нет", "None")}</p>
              </div>
              <div className="bg-card px-4 py-3 text-xs">
                <p className="text-muted-foreground">{tr("Параллельность", "Concurrency")}</p>
                <p className="mt-1 text-foreground">{policy.concurrency}</p>
              </div>
            </div>
          </details>
        </>
      ) : null}
    </section>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-border/70 px-5 py-3.5 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <dt className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-1 truncate text-sm font-medium text-foreground">{value}</dd>
    </div>
  );
}

function ValidationStageRow({ lang, name, stage }: { lang: string; name: string; stage: PlaybookValidationStage }) {
  const status = stage.status || stage.execution?.status || (stage.passed === true ? "passed" : "unknown");
  const passed = ["passed", "ready", "complete", "clean", "not_required", "verified"].includes(status);
  const labels: Record<string, [string, string]> = {
    input_guard: ["Входные данные", "Input"],
    parse: ["Синтаксис YAML", "YAML syntax"],
    static_analysis: ["Статический анализ", "Static analysis"],
    compatibility: ["Совместимость", "Compatibility"],
    bindings: ["Привязки", "Bindings"],
    variables: ["Переменные", "Variables"],
    runtime: ["Готовность Ansible", "Ansible readiness"],
    targets: ["Цели", "Targets"],
    readiness: ["Готовность", "Readiness"],
    bundle: ["Файлы проекта", "Project files"],
  };
  const label = labels[name]?.[lang === "ru" ? 0 : 1] || name.replaceAll("_", " ");
  return (
    <div className="flex items-center justify-between gap-3 bg-card px-4 py-3 text-xs">
      <span className="truncate text-muted-foreground">{label}</span>
      <span className={passed ? "text-success" : status === "unknown" ? "text-muted-foreground" : "text-destructive"}>
        {passed ? (lang === "ru" ? "Пройдено" : "Passed") : status}
      </span>
    </div>
  );
}
