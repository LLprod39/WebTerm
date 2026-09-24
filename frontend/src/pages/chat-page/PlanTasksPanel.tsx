import { Check, Circle, ListChecks, Loader2, X } from "lucide-react";

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

/** Plan steps content for the shared context rail (no outer chrome / fixed width). */
export function PlanTasksPanel({ plan }: { plan: PlanData | null }) {
  const { lang } = useI18n();
  const steps = plan?.steps || [];

  if (!plan || !steps.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <ListChecks className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
        <p className="max-w-[14rem] text-[12px] leading-relaxed text-muted-foreground">
          {localize(
            lang,
            "План задач появится здесь, когда агент начнёт работу.",
            "A task plan will appear here when the agent starts working.",
          )}
        </p>
      </div>
    );
  }

  const done = steps.filter((s) => stepState(s.status) === "done").length;
  const failed = steps.some((s) => stepState(s.status) === "failed");
  const total = steps.length;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const complete = plan.status === "completed" || done === total;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 px-3 pt-3">
        <div className="mb-2 flex items-center gap-2">
          <span className="rounded-sm bg-muted px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-muted-foreground">
            {done}/{total}
          </span>
          {plan.title ? (
            <div className="line-clamp-2 min-w-0 text-[12.5px] font-medium leading-snug text-foreground">
              {plan.title}
            </div>
          ) : null}
        </div>
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
    </div>
  );
}
