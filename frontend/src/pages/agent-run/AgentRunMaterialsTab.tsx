import { useState } from "react";
import { FolderArchive, List, Terminal } from "lucide-react";

import type { AgentRunReportResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

import { EventsTab } from "./AgentRunEventsTab";
import { ArtifactsTab, LogsTab } from "./AgentRunLogsArtifactsTabs";
import type { MaterialsSection } from "./reportShared";

const sections: Array<{ id: MaterialsSection; label: string; icon: typeof List; hint: string }> = [
  { id: "events", label: "События", icon: List, hint: "Таймлайн" },
  { id: "logs", label: "Логи", icon: Terminal, hint: "Команды" },
  { id: "artifacts", label: "Файлы", icon: FolderArchive, hint: "Артефакты" },
];

/**
 * «Материалы» — everything technical, out of the way of the outcome.
 */
export function MaterialsTab({
  report,
  initialSection = "events",
}: {
  report: AgentRunReportResponse;
  initialSection?: MaterialsSection;
}) {
  const [section, setSection] = useState<MaterialsSection>(initialSection);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 rounded-sm border border-border bg-surface-0 p-1">
        {sections.map((item) => {
          const Icon = item.icon;
          const active = section === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setSection(item.id)}
              className={cn(
                "inline-flex min-h-9 flex-1 items-center justify-center gap-2 rounded-sm px-3 text-xs font-medium transition-colors sm:flex-none",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {item.label}
              <span className={cn("hidden font-mono text-2xs sm:inline", active ? "opacity-80" : "opacity-50")}>
                {item.id === "events"
                  ? report.events.length
                  : item.id === "logs"
                    ? report.logs.length
                    : report.artifacts.length}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-2xs text-muted-foreground">
        Здесь технические детали. Для вывода «что случилось» вернитесь на вкладку{" "}
        <strong className="text-foreground/80">Итог</strong>.
      </p>

      {section === "events" ? <EventsTab report={report} /> : null}
      {section === "logs" ? <LogsTab report={report} logs={report.logs} /> : null}
      {section === "artifacts" ? <ArtifactsTab report={report} /> : null}
    </div>
  );
}
