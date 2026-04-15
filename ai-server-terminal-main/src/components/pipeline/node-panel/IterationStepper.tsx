import { Minus, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";

import { clampNumber } from "./shared";

type IterationStepperProps = {
  value: number;
  min?: number;
  max?: number;
  onChange: (nextValue: number) => void;
};

export function IterationStepper({
  value,
  min = 1,
  max = 20,
  onChange,
}: IterationStepperProps) {
  const safeValue = clampNumber(value || min, min, max);
  const canDecrement = safeValue > min;
  const canIncrement = safeValue < max;

  return (
    <div className="flex h-11 items-center rounded-2xl border border-border/70 bg-background/70 px-1">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-9 w-9 rounded-xl"
        aria-label="Decrease iterations"
        onClick={() => canDecrement && onChange(safeValue - 1)}
        disabled={!canDecrement}
      >
        <Minus className="h-4 w-4" />
      </Button>
      <div className="flex flex-1 flex-col items-center justify-center">
        <span className="text-lg font-semibold tabular-nums text-foreground" aria-live="polite">
          {safeValue}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {min}-{max}
        </span>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-9 w-9 rounded-xl"
        aria-label="Increase iterations"
        onClick={() => canIncrement && onChange(safeValue + 1)}
        disabled={!canIncrement}
      >
        <Plus className="h-4 w-4" />
      </Button>
    </div>
  );
}
