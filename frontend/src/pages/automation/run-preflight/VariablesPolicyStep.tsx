import { Braces, KeyRound, Shield } from "lucide-react";

import type { PlaybookBindingProfile } from "@/api/playbooks";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ExtraVarsParseError, RunPolicyOptions } from "../runPreflightState";

interface VariablesPolicyStepProps {
  lang: string;
  bindingProfile: PlaybookBindingProfile | null;
  extraVarsText: string;
  extraVarsError: ExtraVarsParseError;
  availableVariableNames: string[];
  requiredVariableNames: string[];
  policy: RunPolicyOptions;
  onExtraVarsChange: (source: string) => void;
  onPolicyChange: (patch: Partial<RunPolicyOptions>) => void;
}

export function VariablesPolicyStep({
  lang,
  bindingProfile,
  extraVarsText,
  extraVarsError,
  availableVariableNames,
  requiredVariableNames,
  policy,
  onExtraVarsChange,
  onPolicyChange,
}: VariablesPolicyStepProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const missingNames = requiredVariableNames.filter((name) => !availableVariableNames.includes(name));
  const jsonError = extraVarsError === "invalid_json"
    ? tr("Некорректный JSON: проверьте кавычки, запятые и скобки.", "Invalid JSON: check quotes, commas, and braces.")
    : extraVarsError === "object_required"
      ? tr("Ожидается JSON-объект вида {\"key\": value}.", "Expected a JSON object such as {\"key\": value}.")
      : "";

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
        <div className="flex items-center gap-2">
          <Braces className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            {tr("Typed runtime variables", "Typed runtime variables")}
          </h3>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {tr(
            "Числа, boolean, массивы и объекты сохраняют свой тип. Значения существуют только в контексте запуска.",
            "Numbers, booleans, arrays, and objects keep their JSON type. Values exist only in the run context.",
          )}
        </p>

        {bindingProfile ? (
          <div className="mt-3 rounded-sm border border-border bg-surface-0 px-3 py-2.5">
            <div className="flex items-center gap-1.5">
              <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs font-medium text-foreground">{bindingProfile.name}</p>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {tr(
                "Из профиля загружаются только имена переменных. Секретные значения браузеру не возвращаются.",
                "Only variable names are loaded from the profile. Secret values are never returned to the browser.",
              )}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {availableVariableNames.map((name) => (
                <span key={name} className="rounded-sm border border-border bg-card px-2 py-1 font-mono text-2xs text-foreground">
                  {name}{bindingProfile.secret_variables.includes(name) ? " · secret" : ""}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-4 space-y-1.5">
          <Label htmlFor="run-extra-vars">extra_vars JSON</Label>
          <Textarea
            id="run-extra-vars"
            value={extraVarsText}
            rows={12}
            spellCheck={false}
            aria-invalid={Boolean(extraVarsError)}
            aria-describedby={extraVarsError ? "run-extra-vars-error" : undefined}
            className="font-mono text-xs"
            onChange={(event) => onExtraVarsChange(event.target.value)}
          />
          {jsonError ? (
            <p id="run-extra-vars-error" role="alert" className="text-xs text-destructive">{jsonError}</p>
          ) : (
            <p className="text-xs text-muted-foreground">
              {tr("Пример: {\"release\": 42, \"enabled\": true}", "Example: {\"release\": 42, \"enabled\": true}")}
            </p>
          )}
        </div>

        {missingNames.length ? (
          <div className="mt-3 rounded-sm border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            {tr("Пока не заданы", "Not provided yet")}: {missingNames.join(", ")}
          </div>
        ) : null}
      </section>

      <section className="space-y-4 rounded-sm border border-border bg-card p-4 shadow-elev-1">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">{tr("Политика запуска", "Run policy")}</h3>
        </div>

        <div className="space-y-2">
          <Label htmlFor="run-concurrency">{tr("Параллельность (forks)", "Concurrency (forks)")}</Label>
          <input
            id="run-concurrency"
            type="range"
            min={1}
            max={12}
            value={policy.concurrency}
            onChange={(event) => onPolicyChange({ concurrency: Number(event.target.value) })}
            className="w-full accent-[hsl(var(--primary))]"
          />
          <p className="font-mono text-sm text-foreground">{policy.concurrency}</p>
        </div>

        <label className="flex cursor-pointer items-start gap-3 rounded-sm border border-border bg-surface-0 p-3">
          <input
            type="checkbox"
            checked={policy.become}
            onChange={(event) => onPolicyChange({ become: event.target.checked })}
            className="mt-1"
          />
          <span>
            <span className="block text-sm font-medium text-foreground">become (sudo)</span>
            <span className="mt-1 block text-xs text-muted-foreground">ansible-playbook --become</span>
          </span>
        </label>

        <label className="flex cursor-pointer items-start gap-3 rounded-sm border border-border bg-surface-0 p-3">
          <input
            type="checkbox"
            checked={policy.dryRun}
            onChange={(event) => onPolicyChange({ dryRun: event.target.checked })}
            className="mt-1"
          />
          <span>
            <span className="block text-sm font-medium text-foreground">Check / dry-run</span>
            <span className="mt-1 block text-xs text-muted-foreground">--check --diff</span>
          </span>
        </label>

        <div className="space-y-1.5">
          <Label htmlFor="run-tags">tags</Label>
          <Input id="run-tags" value={policy.tags} onChange={(event) => onPolicyChange({ tags: event.target.value })} placeholder="deploy,config" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="run-skip-tags">skip_tags</Label>
          <Input id="run-skip-tags" value={policy.skipTags} onChange={(event) => onPolicyChange({ skipTags: event.target.value })} placeholder="dangerous" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="run-limit">limit</Label>
          <Input id="run-limit" value={policy.limit} onChange={(event) => onPolicyChange({ limit: event.target.value })} placeholder="web:&online" />
        </div>
      </section>
    </div>
  );
}
