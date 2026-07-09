import { Check } from "lucide-react";

import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { AGENT_WIZARD_STEPS, type AgentWizardStep } from "./agentPageUtils";

type AgentWizardProgressProps = {
  step: AgentWizardStep;
  currentStepIndex: number;
  lang: string;
  onStepChange: (step: AgentWizardStep) => void;
  canVisitStep: (step: AgentWizardStep) => boolean;
};

/** Minimal one-line stepper: numbered labels, completed = check, thin progress track. */
export function AgentWizardProgress({ step, currentStepIndex, lang, onStepChange, canVisitStep }: AgentWizardProgressProps) {
  return (
    <div className="border-b border-border/50 px-6">
      <div className="flex items-center gap-1 overflow-x-auto">
        {AGENT_WIZARD_STEPS.map((item, index) => {
          const active = item.key === step;
          const complete = index < currentStepIndex;
          const canVisit = canVisitStep(item.key);
          return (
            <button
              key={item.key}
              type="button"
              disabled={!canVisit}
              onClick={() => onStepChange(item.key)}
              aria-current={active ? "step" : undefined}
              className={cn(
                "relative flex shrink-0 items-center gap-1.5 px-2.5 py-2.5 text-sm transition-colors disabled:cursor-not-allowed",
                active
                  ? "font-medium text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-primary"
                  : complete
                    ? "text-muted-foreground hover:text-foreground"
                    : "text-muted-foreground/50",
              )}
            >
              <span
                className={cn(
                  "flex h-4.5 w-4.5 min-h-[18px] min-w-[18px] items-center justify-center rounded-full text-2xs font-semibold",
                  active
                    ? "bg-primary text-primary-foreground"
                    : complete
                      ? "bg-success/15 text-success"
                      : "bg-surface-2 text-muted-foreground/70",
                )}
                aria-hidden
              >
                {complete ? <Check className="h-3 w-3" /> : index + 1}
              </span>
              {localize(lang, item.labelRu, item.labelEn)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
