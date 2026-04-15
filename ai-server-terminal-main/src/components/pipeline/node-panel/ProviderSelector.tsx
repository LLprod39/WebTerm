import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

import type { AgentProviderCardOption } from "./shared";

type ProviderSelectorProps = {
  options: AgentProviderCardOption[];
  value: string;
  onChange: (provider: string) => void;
};

export function ProviderSelector({
  options,
  value,
  onChange,
}: ProviderSelectorProps) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {options.map((option) => {
        const isActive = option.value === value;

        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={isActive}
            onClick={() => onChange(option.value)}
            className={cn(
              "group flex min-h-[88px] flex-col justify-between rounded-2xl border px-3 py-3 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              isActive
                ? "border-primary/60 bg-primary/10 shadow-[0_10px_30px_rgba(0,0,0,0.14)]"
                : "border-border/70 bg-background/70 hover:border-primary/30 hover:bg-muted/30",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-foreground">{option.label}</span>
              {isActive ? <Sparkles className="h-3.5 w-3.5 text-primary" /> : null}
            </div>
            <div className="space-y-1">
              <p className="line-clamp-2 text-xs font-medium text-muted-foreground">
                {option.modelLabel}
              </p>
              <p className="text-[11px] text-muted-foreground/80">
                {option.hint}
              </p>
            </div>
          </button>
        );
      })}
    </div>
  );
}
