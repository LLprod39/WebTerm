import { CheckCircle2, FlaskConical, Rocket, Settings2 } from "lucide-react";

import type { PlaybookBindingProfile } from "@/api/playbooks";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface RunEssentialsStepProps {
  lang: string;
  requiredVariableNames: string[];
  profileVariableNames: Set<string>;
  selectedProfile: PlaybookBindingProfile | null;
  extraVars: Record<string, unknown>;
  dryRun: boolean;
  onRequiredVariableChange: (name: string, value: string) => void;
  onDryRunChange: (dryRun: boolean) => void;
}

export function RunEssentialsStep({
  lang,
  requiredVariableNames,
  profileVariableNames,
  selectedProfile,
  extraVars,
  dryRun,
  onRequiredVariableChange,
  onDryRunChange,
}: RunEssentialsStepProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  return (
    <>
      {requiredVariableNames.length ? (
        <section className="rounded-lg border border-border bg-card p-4 shadow-elev-1" aria-labelledby="required-params-title">
          <div className="flex items-start gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Settings2 className="h-4 w-4" />
            </span>
            <div>
              <h2 id="required-params-title" className="text-sm font-semibold text-foreground">{tr("Обязательные параметры", "Required parameters")}</h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{tr("Заполните только то, без чего playbook не сможет стартовать.", "Fill in only what the playbook needs to start.")}</p>
            </div>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {requiredVariableNames.map((name) => {
              const fromProfile = profileVariableNames.has(name);
              const secret = selectedProfile?.secret_variables.includes(name) ?? false;
              return (
                <div key={name} className="space-y-1.5">
                  <Label htmlFor={`required-var-${name}`}>{name}</Label>
                  {fromProfile ? (
                    <div id={`required-var-${name}`} className="flex h-10 items-center rounded-md border border-success/25 bg-success/[0.06] px-3 text-xs text-success">
                      <CheckCircle2 className="mr-2 h-3.5 w-3.5" />
                      {secret ? tr("Секрет взят из сохранённого профиля", "Secret comes from the saved profile") : tr("Значение взято из сохранённого профиля", "Value comes from the saved profile")}
                    </div>
                  ) : (
                    <Input
                      id={`required-var-${name}`}
                      type={secret ? "password" : "text"}
                      autoComplete="off"
                      value={String(extraVars[name] ?? "")}
                      onChange={(event) => onRequiredVariableChange(name, event.target.value)}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="rounded-lg border border-border bg-card p-4 shadow-elev-1" aria-labelledby="run-mode-title">
        <div>
          <h2 id="run-mode-title" className="text-sm font-semibold text-foreground">{tr("Режим запуска", "Run mode")}</h2>
          <p className="mt-1 text-xs text-muted-foreground">{tr("Проверочный прогон безопасно покажет изменения без их применения.", "A dry run safely previews changes without applying them.")}</p>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <RunModeOption
            active={dryRun}
            icon={<FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-primary" />}
            title={tr("Проверить без изменений", "Dry run")}
            description={tr("Рекомендуется для первого запуска", "Recommended for the first run")}
            onClick={() => onDryRunChange(true)}
          />
          <RunModeOption
            active={!dryRun}
            icon={<Rocket className="mt-0.5 h-4 w-4 shrink-0 text-primary" />}
            title={tr("Применить изменения", "Apply changes")}
            description={tr("Запуск с реальным воздействием на серверы", "Run with real changes on the targets")}
            onClick={() => onDryRunChange(false)}
          />
        </div>
      </section>
    </>
  );
}

function RunModeOption({ active, icon, title, description, onClick }: { active: boolean; icon: React.ReactNode; title: string; description: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn("flex items-start gap-3 rounded-md border p-3 text-left", active ? "border-primary bg-primary/[0.06]" : "border-border bg-surface-0/50 hover:border-primary/35")}
    >
      {icon}
      <span><span className="block text-sm font-medium text-foreground">{title}</span><span className="mt-1 block text-xs text-muted-foreground">{description}</span></span>
    </button>
  );
}
