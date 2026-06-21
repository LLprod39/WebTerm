import { CheckCircle2, Lock } from "lucide-react";

import { localize } from "@/lib/i18n";

import { AGENT_WIZARD_STEPS, type AgentWizardStep } from "./agentPageUtils";

type AgentWizardProgressProps = {
  step: AgentWizardStep;
  currentStepIndex: number;
  lang: string;
  onStepChange: (step: AgentWizardStep) => void;
  canVisitStep: (step: AgentWizardStep) => boolean;
};

export function AgentWizardProgress({ step, currentStepIndex, lang, onStepChange, canVisitStep }: AgentWizardProgressProps) {
  return (
    <div className="border-b border-border/70 bg-secondary/10 px-4 py-3 sm:px-6">
      <div className="flex gap-2 overflow-x-auto pb-1">
        {AGENT_WIZARD_STEPS.map((item, index) => {
          const Icon = item.icon;
          const active = item.key === step;
          const complete = index < currentStepIndex;
          const canVisit = canVisitStep(item.key);
          return (
            <button
              key={item.key}
              type="button"
              disabled={!canVisit}
              onClick={() => onStepChange(item.key)}
              className={`flex min-h-14 w-[210px] shrink-0 items-center gap-3 rounded-lg border px-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${
                active
                  ? "border-primary/80 bg-primary/10 text-foreground"
                  : complete
                    ? "border-primary/25 bg-secondary/30 text-foreground hover:border-primary/50"
                    : "border-border/60 bg-background/20 text-muted-foreground hover:border-primary/35 hover:text-foreground"
              }`}
            >
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-sm font-semibold ${active || complete ? "border-primary bg-primary/15 text-primary" : "border-border/80 bg-secondary/30"}`}>
                {complete ? <CheckCircle2 className="h-4 w-4" /> : !canVisit ? <Lock className="h-4 w-4" /> : active ? index + 1 : <Icon className="h-4 w-4" />}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{localize(lang, item.labelRu, item.labelEn)}</span>
                <span className="block truncate text-xs leading-4 text-muted-foreground">{localize(lang, item.detailRu, item.detailEn)}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
