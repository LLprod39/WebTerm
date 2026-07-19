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

/** Catalog stepper: sharp pills, acid active rail, check for completed steps. */
export function AgentWizardProgress({ step, currentStepIndex, lang, onStepChange, canVisitStep }: AgentWizardProgressProps) {
  const total = AGENT_WIZARD_STEPS.length;
  const progressPct = Math.round(((currentStepIndex + 1) / total) * 100);

  return (
    <div className="border-b border-border bg-surface-0/40">
      <div className="h-0.5 w-full bg-surface-2">
        <div
          className="h-full bg-primary transition-[width] duration-500 ease-[var(--ease-standard)]"
          style={{ width: `${progressPct}%` }}
        />
      </div>
      <div className="flex items-stretch gap-0.5 overflow-x-auto px-4 sm:px-6">
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
                "relative flex min-h-11 shrink-0 items-center gap-2 px-2.5 py-2.5 text-sm transition-colors disabled:cursor-not-allowed sm:px-3",
                active
                  ? "font-semibold text-foreground after:absolute after:inset-x-1 after:bottom-0 after:h-0.5 after:bg-primary"
                  : complete
                    ? "text-muted-foreground hover:text-foreground"
                    : "text-muted-foreground/45",
              )}
            >
              <span
                className={cn(
                  "flex h-[18px] w-[18px] items-center justify-center rounded-sm font-mono text-[10px] font-semibold",
                  active
                    ? "bg-primary text-primary-foreground shadow-elev-1"
                    : complete
                      ? "border border-success/40 bg-success/15 text-success"
                      : "border border-border bg-surface-2 text-muted-foreground/70",
                )}
                aria-hidden
              >
                {complete ? <Check className="h-3 w-3" /> : index + 1}
              </span>
              <span className="hidden sm:inline">{localize(lang, item.labelRu, item.labelEn)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
