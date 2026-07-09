import type { LucideIcon } from "lucide-react";
import { InlineAlert } from "@/components/system/InlineAlert";
import type { AgentInputArtifact } from "@/lib/api";
import { localize } from "@/lib/i18n";
import type { AgentWizardCheck } from "./agentPageUtils";

export type SummaryRow = { icon: LucideIcon; label: string; value: string };

type AgentWizardReviewStepProps = {
  lang: string;
  summaryRows: SummaryRow[];
  commandCount: number;
  selectedSkillSlugs: string[];
  inputArtifacts: AgentInputArtifact[];
  telegramEnabled: boolean;
  readiness: number;
  readinessChecks: AgentWizardCheck[];
};

export function AgentWizardReviewStep({
  lang,
  summaryRows,
  commandCount,
  selectedSkillSlugs,
  inputArtifacts,
  telegramEnabled,
  readiness,
  readinessChecks,
}: AgentWizardReviewStepProps) {
  const extras: string[] = [];
  if (commandCount) extras.push(localize(lang, `${commandCount} команд`, `${commandCount} commands`));
  if (selectedSkillSlugs.length) extras.push(localize(lang, `${selectedSkillSlugs.length} скиллов`, `${selectedSkillSlugs.length} skills`));
  if (inputArtifacts.length) extras.push(localize(lang, `${inputArtifacts.length} материалов`, `${inputArtifacts.length} materials`));
  if (telegramEnabled) extras.push("Telegram");

  return (
    <section className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-foreground">{localize(lang, "Проверьте перед созданием", "Check before creating")}</h3>
        <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
          {localize(lang, "Убедитесь, что агент настроен так, как вы ожидаете.", "Make sure the agent is set up as you expect.")}
        </p>
      </div>

      <dl className="divide-y divide-border/40 rounded-xl border border-border/50">
        {summaryRows.map((row) => {
          const Icon = row.icon;
          return (
            <div key={row.label} className="flex items-center gap-3 px-4 py-3">
              <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <dt className="w-36 shrink-0 text-sm text-muted-foreground">{row.label}</dt>
              <dd className="min-w-0 truncate text-sm font-medium text-foreground">{row.value}</dd>
            </div>
          );
        })}
        {extras.length ? (
          <div className="flex items-center gap-3 px-4 py-3">
            <span className="h-4 w-4 shrink-0" aria-hidden />
            <dt className="w-36 shrink-0 text-sm text-muted-foreground">{localize(lang, "Дополнительно", "Extras")}</dt>
            <dd className="min-w-0 truncate text-sm text-foreground">{extras.join(" · ")}</dd>
          </div>
        ) : null}
      </dl>

      {readiness < 100 ? (
        <InlineAlert
          tone="warning"
          title={localize(lang, "Ещё не всё готово", "Not everything is ready yet")}
          description={localize(
            lang,
            readinessChecks.filter((check) => !check.passed).map((check) => check.labelRu).join(" · "),
            readinessChecks.filter((check) => !check.passed).map((check) => check.labelEn).join(" · "),
          )}
        />
      ) : (
        <InlineAlert
          tone="success"
          title={localize(lang, "Всё готово", "All set")}
          description={localize(lang, "Можно создавать агента.", "You can create the agent.")}
        />
      )}
    </section>
  );
}
