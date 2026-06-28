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
  return (
    <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
            <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Обзор", "Review")}</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {summaryRows.map((row) => {
                const Icon = row.icon;
                return (
                  <div key={row.label} className="rounded-lg border border-border/70 bg-background/30 p-4">
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-primary"><Icon className="h-4 w-4" /></div>
                    <div className="text-xs text-muted-foreground">{row.label}</div>
                    <div className="mt-1 text-sm font-semibold text-foreground">{row.value}</div>
                  </div>
                );
              })}
            </div>
            <div className="rounded-lg border border-border/70 bg-background/30 p-4">
              <div className="grid gap-3 text-sm md:grid-cols-4">
                <div><span className="block text-xs leading-4 text-muted-foreground">{localize(lang, "Команды", "Commands")}</span><strong>{commandCount}</strong></div>
                <div><span className="block text-xs leading-4 text-muted-foreground">{localize(lang, "Скиллы", "Skills")}</span><strong>{selectedSkillSlugs.length}</strong></div>
                <div><span className="block text-xs leading-4 text-muted-foreground">{localize(lang, "Материалы", "Materials")}</span><strong>{inputArtifacts.length}</strong></div>
                <div><span className="block text-xs leading-4 text-muted-foreground">Telegram</span><strong>{telegramEnabled ? localize(lang, "Да", "Yes") : localize(lang, "Нет", "No")}</strong></div>
                <div><span className="block text-xs leading-4 text-muted-foreground">{localize(lang, "Готовность", "Readiness")}</span><strong>{readiness}%</strong></div>
              </div>
            </div>
            {readiness < 100 ? (
              <InlineAlert
                tone="warning"
                title={localize(lang, "Preflight ещё не пройден", "Preflight is not complete")}
                description={localize(
                  lang,
                  readinessChecks.filter((check) => !check.passed).map((check) => check.labelRu).join(" · "),
                  readinessChecks.filter((check) => !check.passed).map((check) => check.labelEn).join(" · "),
                )}
              />
            ) : (
              <InlineAlert
                tone="success"
                title={localize(lang, "Preflight пройден", "Preflight passed")}
                description={localize(lang, "Конфигурация готова к созданию агента.", "Configuration is ready to create the agent.")}
              />
            )}
    </section>
  );
}
