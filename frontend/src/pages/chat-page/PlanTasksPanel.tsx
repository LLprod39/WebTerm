import { ListChecks } from "lucide-react";

import { AgentProgress } from "@/boardui/components/application/agent-progress/agent-progress";
import type { AgentProgressStep } from "@/boardui/components/application/agent-progress/agent-progress";
import { localize, useI18n } from "@/lib/i18n";

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

/** Map backend step status → AgentProgress glyph. awaiting_confirm is waiting, not running. */
export function mapStepStatus(status?: string): AgentProgressStep["status"] {
  if (status === "done" || status === "completed") return "done";
  if (status === "failed" || status === "error") return "error";
  if (status === "running") return "running";
  if (status === "awaiting_confirm" || status === "waiting") return "waiting";
  return "pending";
}

export function planToAgentProgressSteps(
  plan: PlanData | null | undefined,
  { turnActive = true }: { turnActive?: boolean } = {},
): AgentProgressStep[] {
  return (plan?.steps || []).map((step, index) => {
    let status = mapStepStatus(step.status);
    // Stuck running with no busy turn must not look like execution.
    if (!turnActive && status === "running") status = "waiting";
    return {
      id: step.id ?? index,
      label: cleanStepTitle(step.text),
      status,
    };
  });
}

/** Plan steps content for the shared context rail — BoardUI Agent Progress. */
export function PlanTasksPanel({
  plan,
  turnActive = true,
}: {
  plan: PlanData | null;
  /** When false, stuck `running` steps render as waiting (static). */
  turnActive?: boolean;
}) {
  const { lang } = useI18n();
  const steps = planToAgentProgressSteps(plan, { turnActive });

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

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 overflow-y-auto p-2.5">
      {plan.title ? (
        <div className="px-1 text-[12.5px] font-medium leading-snug text-foreground">
          {plan.title}
        </div>
      ) : null}
      <AgentProgress steps={steps} controlled defaultExpanded className="max-w-none" />
    </div>
  );
}
