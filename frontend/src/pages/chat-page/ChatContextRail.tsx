import { FileSearch, ListChecks, Terminal, X } from "lucide-react";

import type { AssistantAction } from "@/api";
import { Button } from "@/components/ui/button";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { ActionDetailsPanel } from "./ActionDetailsPanel";
import { OperatorSessionDock } from "./OperatorSessionDock";
import { PlanTasksPanel, type PlanData } from "./PlanTasksPanel";
import type { OperatorSessionState } from "./operatorSessionTypes";

export type ContextRailTab = "tasks" | "terminal" | "details";

type Props = {
  tab: ContextRailTab;
  onTabChange: (tab: ContextRailTab) => void;
  onClose: () => void;
  plan: PlanData | null;
  session: OperatorSessionState;
  actionDetails: AssistantAction | null;
  onModeChange: (mode: "agent" | "live") => void;
  onHumanCommand: (cmd: string) => void;
  onOpenTerminalFromDetails?: () => void;
  /** When true, omit outer border (used inside Sheet). */
  embedded?: boolean;
  className?: string;
};

/**
 * Single right context rail: Tasks | Terminal | Details tabs (mutually exclusive content).
 */
export function ChatContextRail({
  tab,
  onTabChange,
  onClose,
  plan,
  session,
  actionDetails,
  onModeChange,
  onHumanCommand,
  onOpenTerminalFromDetails,
  embedded = false,
  className,
}: Props) {
  const { lang } = useI18n();
  const hasPlan = Boolean(plan?.steps?.length);
  const hasSession = session.open && Boolean(session.serverId);
  const hasDetails = Boolean(actionDetails);

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 w-full flex-col overflow-hidden bg-card",
        !embedded && "border-l border-border",
        className,
      )}
      aria-label={localize(lang, "Контекст", "Context")}
    >
      <header className="flex h-11 shrink-0 items-center gap-1 border-b border-border px-2">
        <div className="flex min-w-0 flex-1 items-center gap-0.5 rounded-sm bg-secondary/60 p-0.5">
          <button
            type="button"
            onClick={() => onTabChange("tasks")}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-sm px-2 py-1.5 text-[11px] font-medium transition-colors",
              tab === "tasks"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <ListChecks className="h-3.5 w-3.5" />
            {localize(lang, "Задачи", "Tasks")}
            {hasPlan ? (
              <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
            ) : null}
          </button>
          <button
            type="button"
            onClick={() => onTabChange("terminal")}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-sm px-2 py-1.5 text-[11px] font-medium transition-colors",
              tab === "terminal"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Terminal className="h-3.5 w-3.5" />
            {localize(lang, "Терминал", "Terminal")}
            {hasSession ? (
              <span className="h-1.5 w-1.5 rounded-full bg-ai" aria-hidden />
            ) : null}
          </button>
          <button
            type="button"
            onClick={() => onTabChange("details")}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-sm px-2 py-1.5 text-[11px] font-medium transition-colors",
              tab === "details"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <FileSearch className="h-3.5 w-3.5" />
            {localize(lang, "Детали", "Details")}
            {hasDetails ? (
              <span className="h-1.5 w-1.5 rounded-full bg-info" aria-hidden />
            ) : null}
          </button>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 shrink-0 p-0"
          onClick={onClose}
          aria-label={localize(lang, "Закрыть", "Close")}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "tasks" ? (
          <PlanTasksPanel plan={plan} />
        ) : tab === "terminal" ? (
          <OperatorSessionDock
            session={session}
            onModeChange={onModeChange}
            onHumanCommand={onHumanCommand}
          />
        ) : (
          <ActionDetailsPanel
            action={actionDetails}
            hasSession={hasSession}
            onOpenTerminal={onOpenTerminalFromDetails}
          />
        )}
      </div>
    </aside>
  );
}
