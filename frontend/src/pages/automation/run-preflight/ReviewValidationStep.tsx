import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, ShieldCheck, XCircle } from "lucide-react";

import type { PlaybookRunValidation, PlaybookValidationStage } from "@/api/playbook-preflight";
import type { PlaybookBindingProfile, PlaybookRevision } from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RunPolicyOptions, RunTargetContext } from "../runPreflightState";
import { runtimeValueType } from "../runPreflightState";

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

  return (
    <div className="grid gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]">
      <section className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
        <h3 className="text-sm font-semibold text-foreground">{tr("Точный контекст запуска", "Exact run context")}</h3>
        <dl className="mt-3 space-y-2 text-xs">
          <SummaryRow label="Playbook" value={playbookName} />
          <SummaryRow label="Revision" value={revision ? `#${revision.revision_number} · ${revision.content_hash.slice(0, 12)}…` : "—"} mono />
          <SummaryRow label={tr("Цели", "Targets")} value={`${context.serverIds.length} S · ${context.groupIds.length} G`} mono />
          <SummaryRow label={tr("Binding", "Binding")} value={bindingProfile ? `${bindingProfile.name} · v${bindingProfile.version}` : tr("Разовый", "Ad-hoc")} />
          <SummaryRow label="forks" value={String(policy.concurrency)} mono />
          <SummaryRow label="become" value={policy.become ? "yes" : "no"} mono />
          <SummaryRow label="dry-run" value={policy.dryRun ? "yes" : "no"} mono />
          {policy.tags ? <SummaryRow label="tags" value={policy.tags} mono /> : null}
          {policy.skipTags ? <SummaryRow label="skip_tags" value={policy.skipTags} mono /> : null}
          {policy.limit ? <SummaryRow label="limit" value={policy.limit} mono /> : null}
        </dl>

        <div className="mt-4 border-t border-border pt-3">
          <p className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
            {tr("Runtime variables — типы", "Runtime variables — types")}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {Object.entries(extraVars).length ? Object.entries(extraVars).map(([name, value]) => (
              <span key={name} className="rounded-sm border border-border bg-surface-0 px-2 py-1 font-mono text-2xs text-foreground">
                {name}: {runtimeValueType(value)}
              </span>
            )) : <span className="text-xs text-muted-foreground">{tr("Нет дополнительных", "No extra variables")}</span>}
          </div>
          {bindingProfile?.secret_variables.length ? (
            <p className="mt-2 text-xs text-muted-foreground">
              {bindingProfile.secret_variables.length} {tr("секретных значений будут разрешены на backend", "secret values will be resolved on the backend")}
            </p>
          ) : null}
        </div>
      </section>

      <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" aria-labelledby="validation-title">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <h3 id="validation-title" className="text-sm font-semibold text-foreground">Run validation</h3>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {tr("Evidence привязано к revision, runtime, targets и binding version.", "Evidence is bound to the revision, runtime, targets, and binding version.")}
            </p>
          </div>
          <Button size="sm" variant="outline" className="h-8 gap-1.5" disabled={validating} onClick={onRetry}>
            {validating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            {tr("Проверить снова", "Validate again")}
          </Button>
        </div>

        {validating ? (
          <div className="flex items-center gap-2 px-4 py-8 text-sm text-muted-foreground" role="status">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            {tr("Проверяем точный контекст…", "Validating the exact context…")}
          </div>
        ) : validationError ? (
          <div role="alert" className="border-b border-destructive/20 bg-destructive/5 px-4 py-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <div>
                <p className="text-sm font-medium text-destructive">{tr("Validation не выполнена", "Validation failed")}</p>
                <p className="mt-1 text-xs text-muted-foreground">{validationError}</p>
              </div>
            </div>
          </div>
        ) : validation ? (
          <>
            <div className={cn(
              "flex items-start gap-2 border-b px-4 py-3",
              ready ? "border-emerald-500/20 bg-emerald-500/5" : "border-destructive/20 bg-destructive/5",
            )}>
              {ready ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-400" /> : <XCircle className="mt-0.5 h-4 w-4 text-destructive" />}
              <div>
                <p className={cn("text-sm font-medium", ready ? "text-emerald-400" : "text-destructive")}>
                  {ready ? tr("Готово к запуску", "Ready to run") : tr("Запуск заблокирован", "Run blocked")}
                </p>
                <p className="mt-0.5 font-mono text-2xs text-muted-foreground">validation #{validation.id}</p>
              </div>
            </div>

            <div className="grid gap-2 border-b border-border p-4 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(validation.stages || {}).map(([name, stage]) => (
                <ValidationStageCard key={name} name={name} stage={stage} />
              ))}
            </div>

            {validation.issues?.length ? (
              <div className="divide-y divide-border">
                {validation.issues.map((issue, index) => (
                  <div key={`${issue.code}-${index}`} className="px-4 py-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className={cn("mt-0.5 h-4 w-4 shrink-0", issue.severity === "error" ? "text-destructive" : "text-amber-400")} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{issue.message}</p>
                        <p className="mt-1 font-mono text-2xs text-muted-foreground">
                          {[issue.stage, issue.code, issue.path].filter(Boolean).join(" · ")}
                        </p>
                        {issue.remediation ? <p className="mt-1 text-xs text-muted-foreground">{issue.remediation}</p> : null}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : null}
      </section>
    </div>
  );
}

function SummaryRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3 border-b border-border/60 py-1.5 last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn("min-w-0 truncate text-right text-foreground", mono && "font-mono")}>{value}</dd>
    </div>
  );
}

function ValidationStageCard({ name, stage }: { name: string; stage: PlaybookValidationStage }) {
  const status = stage.status || stage.execution?.status || (stage.passed === true ? "passed" : "unknown");
  const ready = ["passed", "ready", "complete", "clean", "not_required"].includes(status);
  return (
    <div className="rounded-sm border border-border bg-surface-0 px-3 py-2">
      <p className="truncate text-2xs font-medium uppercase tracking-wider text-muted-foreground">{name.replaceAll("_", " ")}</p>
      <p className={cn("mt-1 text-xs font-medium", ready ? "text-emerald-400" : status === "unknown" ? "text-muted-foreground" : "text-destructive")}>
        {status}
      </p>
      {stage.message ? <p className="mt-1 line-clamp-2 text-2xs text-muted-foreground">{stage.message}</p> : null}
    </div>
  );
}
