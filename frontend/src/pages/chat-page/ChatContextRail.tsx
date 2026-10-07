import { FileSearch, ListChecks, Maximize2, PanelRightClose, Terminal, X } from "lucide-react";

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
  /** When false, stuck running steps render as waiting in the task list. */
  turnActive?: boolean;
  continueAvailable?: boolean;
  onContinuePlan?: () => void;
  session: OperatorSessionState;
  actionDetails: AssistantAction | null;
  onModeChange: (mode: "agent" | "live") => void;
  onHumanCommand: (cmd: string) => void;
  onOpenTerminalFromDetails?: () => void;
  /** When true, omit outer chrome (used inside Sheet). */
  embedded?: boolean;
  className?: string;
};

/**
 * Right context rail mapped to BoardUI Changes/Browser panel pattern:
 * pill tabs + terminal affordance, fixed secondary inspector.
 */
export function ChatContextRail({
  tab,
  onTabChange,
  onClose,
  plan,
  turnActive = true,
  continueAvailable = false,
  onContinuePlan,
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

  const tabs: Array<{ id: ContextRailTab; labelRu: string; labelEn: string; icon: typeof ListChecks; live: boolean }> = [
    { id: "tasks", labelRu: "Задачи", labelEn: "Tasks", icon: ListChecks, live: hasPlan },
    { id: "terminal", labelRu: "Терминал", labelEn: "Terminal", icon: Terminal, live: hasSession },
    { id: "details", labelRu: "Детали", labelEn: "Details", icon: FileSearch, live: hasDetails },
  ];

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 w-full flex-col gap-2.5 overflow-hidden bg-card/30",
        embedded && "rounded-none border-0 shadow-none",
        className,
      )}
      aria-label={localize(lang, "Контекст", "Context")}
    >
      <header className="flex h-[30px] shrink-0 items-center justify-between px-2.5 pt-2">
        <div role="group" className="relative inline-flex items-center gap-0.5" aria-label={localize(lang, "Вид панели", "Panel view")}>
          {tabs.map((item) => {
            const Icon = item.icon;
            const selected = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                aria-pressed={selected}
                onClick={() => onTabChange(item.id)}
                className={cn(
                  "relative z-10 flex shrink-0 items-center gap-1 rounded-md px-2 py-[5px] text-[12px] transition-colors",
                  selected ? "text-primary" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {selected ? (
                  <span className="pointer-events-none absolute inset-0 rounded-md bg-primary/10" aria-hidden />
                ) : null}
                <Icon className="relative z-10 h-4 w-4 shrink-0" />
                <span className="relative z-10 whitespace-nowrap">
                  {lang === "ru" ? item.labelRu : item.labelEn}
                </span>
                {item.live ? (
                  <span className="relative z-10 h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                ) : null}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-1 pe-0.5">
          {hasSession ? (
            <button
              type="button"
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => onTabChange("terminal")}
              aria-label={localize(lang, "Открыть терминал", "Open terminal")}
              title={localize(lang, "Терминал", "Terminal")}
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          ) : null}
          <button
            type="button"
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:text-foreground"
            onClick={onClose}
            aria-label={localize(lang, "Свернуть панель", "Toggle panel")}
            title={localize(lang, "Свернуть", "Collapse")}
          >
            <PanelRightClose className="h-3.5 w-3.5" />
          </button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 shrink-0 rounded-md p-0"
            onClick={onClose}
            aria-label={localize(lang, "Закрыть", "Close")}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-hidden px-1 pb-1">
        {tab === "tasks" ? (
          <PlanTasksPanel
            plan={plan}
            turnActive={turnActive}
            continueAvailable={continueAvailable}
            onContinue={onContinuePlan}
          />
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
