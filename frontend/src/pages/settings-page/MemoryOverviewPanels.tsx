import { Activity, Bot, Clock, Database, FolderOpen, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { ServerMemoryOverviewResponse, ServerMemorySnapshotRecord } from "@/lib/api";
import { MemoryCandidateActions, MemorySnapshotAudit, WorkerStateCard } from "./MemoryCards";
import { SectionCard } from "./SectionCard";

type MemoryOverviewPanelsProps = {
  memoryOverview: ServerMemoryOverviewResponse;
  memoryActionKey: string | null;
  onPromoteNote: (snapshotId: number) => void | Promise<void>;
  onPromoteSkill: (snapshotId: number) => void | Promise<void>;
  onArchive: (snapshotId: number) => void | Promise<void>;
};

function MemoryStatsGrid({ stats }: { stats: ServerMemoryOverviewResponse["stats"] }) {
  const items = [
    { label: "Проверенные", value: stats.canonical },
    { label: "Закономерности", value: stats.patterns },
    { label: "Автоматизация", value: stats.automation_candidates },
    { label: "Навыки", value: stats.skill_drafts },
    { label: "На проверке", value: stats.revalidation_open },
    { label: "Сессии", value: stats.episodes },
    { label: "Архив", value: stats.archive },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      {items.map((item) => (
        <div key={item.label} className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">{item.label}</p>
          <p className="mt-1 text-lg font-semibold text-foreground">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function SnapshotCard({
  item,
  children,
}: {
  item: ServerMemorySnapshotRecord;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium text-foreground">{item.title}</p>
        <Badge variant="secondary">{item.memory_key}</Badge>
        <Badge variant="outline">v{item.version}</Badge>
      </div>
      <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.content}</p>
      <MemorySnapshotAudit item={item} />
      {children}
    </div>
  );
}

export function MemoryOverviewPanels({
  memoryOverview,
  memoryActionKey,
  onPromoteNote,
  onPromoteSkill,
  onArchive,
}: MemoryOverviewPanelsProps) {
  const learnedCandidates = [
    ...memoryOverview.patterns,
    ...memoryOverview.automation_candidates,
    ...memoryOverview.skill_drafts,
  ];

  return (
    <>
      <MemoryStatsGrid stats={memoryOverview.stats} />

      <SectionCard
        title="Фоновые службы"
        icon={Activity}
        description="Анализ, расписание и выполнение"
      >
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-4">
          <WorkerStateCard
            label="Объединение памяти"
            state={memoryOverview.worker_states?.memory_dreams || memoryOverview.daemon_state}
          />
          <WorkerStateCard label="Выполнение агентов" state={memoryOverview.worker_states?.agent_execution} />
          <WorkerStateCard label="Расписание агентов" state={memoryOverview.worker_states?.scheduled_agents} />
          <WorkerStateCard label="Наблюдение" state={memoryOverview.worker_states?.watchers} />
        </div>
      </SectionCard>

      {memoryOverview.canonical.length > 0 ? (
        <SectionCard
          title="Проверенные записи"
          icon={Database}
          description="Факты, доступные моделям"
        >
          <div className="space-y-2">
            {memoryOverview.canonical.map((item) => (
              <SnapshotCard key={item.id} item={item} />
            ))}
          </div>
        </SectionCard>
      ) : null}

      {learnedCandidates.length > 0 ? (
        <SectionCard
          title="Найденные закономерности"
          icon={Bot}
          description="Предложения для базы знаний"
        >
          <div className="space-y-3">
            {learnedCandidates.map((item) => (
              <SnapshotCard key={item.id} item={item}>
                <MemoryCandidateActions
                  item={item}
                  actionKey={memoryActionKey}
                  onPromoteNote={onPromoteNote}
                  onPromoteSkill={onPromoteSkill}
                  onArchive={onArchive}
                />
              </SnapshotCard>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {memoryOverview.revalidation.length > 0 ? (
        <SectionCard
          title="Нужно проверить"
          icon={RefreshCw}
          description="Факты, требующие подтверждения"
        >
          <div className="space-y-2">
            {memoryOverview.revalidation.map((item) => (
              <div key={item.id} className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-foreground">{item.title}</p>
                  <Badge variant="outline">{item.memory_key}</Badge>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{item.reason}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {memoryOverview.episodes.length > 0 ? (
        <SectionCard title="Недавняя активность" icon={Clock} description="Последние сессии и операции">
          <div className="space-y-2">
            {memoryOverview.episodes.slice(0, 6).map((item) => (
              <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-foreground">{item.title}</p>
                  <Badge variant="secondary">{item.episode_kind}</Badge>
                  <Badge variant="outline">{item.event_count} событий</Badge>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.summary}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {memoryOverview.archive.length > 0 ? (
        <SectionCard
          title="Архив"
          icon={FolderOpen}
          description="Старые и отключённые записи"
        >
          <div className="space-y-2">
            {memoryOverview.archive.slice(0, 6).map((item) => (
              <div key={`${item.kind}-${item.id}`} className="rounded-lg border border-border/60 bg-secondary/5 px-3 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-foreground">{item.title}</p>
                  <Badge variant="outline">{item.kind}</Badge>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                  {"content" in item ? item.content : item.summary}
                </p>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}
    </>
  );
}
