import { Check, Circle, ListChecks, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type PlanStep = { id?: number; text?: string; status?: string };
export type PlanData = { title?: string; status?: string; steps?: PlanStep[] };

const SHELL_BOUNDARY =
  /\s(?:find|rm|df|du|cat|ls|echo|grep|awk|sed|tail|head|sort|systemctl|docker|journalctl|kill|chmod|chown|tar|gzip|truncate|rsync|mkdir|mv|cp)\b|\s[|&]{1,2}\s|\s>>?\s|\s-exec\b/;

/**
 * Keep the task list minimal: strip the model's "# N." prefix and drop the inline
 * shell command, leaving just the human intent. Full text stays available on hover.
 */
export function cleanStepTitle(text?: string): string {
  const raw = (text || "").trim();
  let t = raw.replace(/^#+\s*\d+[.)]?\s*/, "").replace(/^\d+[.)]\s*/, "");
  const cut = t.search(SHELL_BOUNDARY);
  if (cut > 16) t = t.slice(0, cut);
  t = t.replace(/[\s:;\-–—]+$/, "").trim();
  return t || raw;
}

function stepState(status?: string): "done" | "failed" | "running" | "pending" {
  if (status === "done" || status === "completed") return "done";
  if (status === "failed" || status === "error") return "failed";
  if (status === "running") return "running";
  return "pending";
}

/** Cursor-style task tracker docked on the right: live plan steps with progress. */
export function PlanTasksPanel({
  plan,
  open,
  onClose,
}: {
  plan: PlanData | null;
  open: boolean;
  onClose: () => void;
}) {
  const { lang } = useI18n();
  const steps = plan?.steps || [];
  if (!open || !plan || !steps.length) return null;

  const done = steps.filter((s) => stepState(s.status) === "done").length;
  const failed = steps.some((s) => stepState(s.status) === "failed");
  const total = steps.length;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const complete = plan.status === "completed" || done === total;

  return (
    <aside className="hidden w-72 shrink-0 flex-col border-l border-border/70 bg-card/50 lg:flex">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border/70 px-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ListChecks className="h-4 w-4 text-primary" />
          {localize(lang, "Задачи", "Tasks")}
          <span className="rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-muted-foreground">
            {done}/{total}
          </span>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0"
          onClick={onClose}
          aria-label={localize(lang, "Скрыть", "Hide")}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="shrink-0 px-3 pt-3">
        {plan.title ? (
          <div className="mb-2 line-clamp-2 text-[12.5px] font-medium leading-snug text-foreground">
            {plan.title}
          </div>
        ) : null}
        <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500 motion-reduce:transition-none",
              failed ? "bg-destructive" : complete ? "bg-success" : "bg-primary",
            )}
            style={{ width: `${Math.max(pct, failed ? 8 : 0)}%` }}
          />
        </div>
      </div>

      <ol className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-2.5">
        {steps.map((step, idx) => {
          const state = stepState(step.status);
          return (
            <li
              key={step.id ?? idx}
              className={cn(
                "flex items-start gap-2 rounded-md px-2 py-1.5 text-[12.5px] leading-snug transition-colors",
                state === "running" && "bg-primary/[0.06]",
              )}
            >
              <span className="mt-0.5 shrink-0">
                {state === "done" ? (
                  <Check className="h-3.5 w-3.5 text-success" />
                ) : state === "failed" ? (
                  <X className="h-3.5 w-3.5 text-destructive" />
                ) : state === "running" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary motion-reduce:animate-none" />
                ) : (
                  <Circle className="h-3.5 w-3.5 text-muted-foreground/40" />
                )}
              </span>
              <span
                title={step.text}
                className={cn(
                  "line-clamp-2 min-w-0",
                  state === "done" && "text-muted-foreground line-through",
                  state === "failed" && "text-destructive",
                  state === "pending" && "text-muted-foreground",
                  state === "running" && "font-medium text-foreground",
                )}
              >
                <span className="mr-1.5 font-mono text-[10px] text-muted-foreground/40">
                  {idx + 1}
                </span>
                {cleanStepTitle(step.text)}
              </span>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
