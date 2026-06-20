import { useState } from "react";
import { actionPlan, type ActionStep } from "@/data/mockReport";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { UserRound, Plus } from "lucide-react";
import { toast } from "sonner";

const priorityStyles: Record<ActionStep["priority"], string> = {
  P0: "bg-critical/15 text-critical border-critical/30",
  P1: "bg-high/15 text-high border-high/30",
  P2: "bg-info/15 text-info border-info/30",
};

export function ActionPlan() {
  const [steps, setSteps] = useState(actionPlan);

  const toggle = (id: string) =>
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, done: !s.done } : s)));

  const doneCount = steps.filter((s) => s.done).length;

  return (
    <div className="report-card flex flex-col p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-foreground">План действий</h3>
        <span className="text-xs text-muted-foreground">
          {doneCount}/{steps.length} выполнено
        </span>
      </div>

      <ul className="mt-4 space-y-2.5">
        {steps.map((s) => (
          <li
            key={s.id}
            className={cn(
              "rounded-lg border border-border bg-surface/60 p-3 transition-colors hover:border-primary/30",
              s.done && "opacity-60",
            )}
          >
            <div className="flex items-start gap-3">
              <Checkbox
                checked={s.done}
                onCheckedChange={() => toggle(s.id)}
                className="mt-0.5"
                aria-label={`Отметить: ${s.title}`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "rounded border px-1.5 py-0.5 font-mono text-[11px] font-semibold",
                      priorityStyles[s.priority],
                    )}
                  >
                    {s.priority}
                  </span>
                  <p
                    className={cn(
                      "text-sm font-medium text-foreground",
                      s.done && "line-through",
                    )}
                  >
                    {s.title}
                  </p>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{s.description}</p>
                <p className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <UserRound className="h-3 w-3" />
                  {s.owner}
                </p>
              </div>
            </div>
          </li>
        ))}
      </ul>

      <Button
        className="mt-4 h-10 w-full gap-1.5"
        onClick={() => toast.success("Задача создана в трекере", { description: "INC-2026-0616" })}
      >
        <Plus className="h-4 w-4" />
        Создать задачу
      </Button>
    </div>
  );
}
