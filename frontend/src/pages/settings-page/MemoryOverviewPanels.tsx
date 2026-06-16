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
    { label: "Canonical", value: stats.canonical },
    { label: "Patterns", value: stats.patterns },
    { label: "Automation", value: stats.automation_candidates },
    { label: "Skill Drafts", value: stats.skill_drafts },
    { label: "Revalidation", value: stats.revalidation_open },
    { label: "Episodes", value: stats.episodes },
    { label: "Archive", value: stats.archive },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      {items.map((item) => (
        <div key={item.label} className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{item.label}</p>
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
        title="Worker status"
        icon={Activity}
        description="Состояние фоновых workers, которые крутят dreams, execution plane и watcher scans."
      >
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          <WorkerStateCard
            label="Memory dreams"
            state={memoryOverview.worker_states?.memory_dreams || memoryOverview.daemon_state}
          />
          <WorkerStateCard label="Agent execution" state={memoryOverview.worker_states?.agent_execution} />
          <WorkerStateCard label="Watchers" state={memoryOverview.worker_states?.watchers} />
        </div>
      </SectionCard>

      {memoryOverview.canonical.length > 0 ? (
        <SectionCard
          title="Canonical snapshots"
          icon={Database}
          description="Активная память сервера, которая реально уходит в prompt."
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
          title="Learned candidates"
          icon={Bot}
          description="То, что dreams и pattern learning предлагают поднять в operational knowledge."
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
          title="Revalidation queue"
          icon={RefreshCw}
          description="Факты, которые снам нужно перепроверить или уточнить."
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
        <SectionCard title="Recent episodes" icon={Clock} description="Последние схлопнутые эпизоды из raw event inbox.">
          <div className="space-y-2">
            {memoryOverview.episodes.slice(0, 6).map((item) => (
              <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-foreground">{item.title}</p>
                  <Badge variant="secondary">{item.episode_kind}</Badge>
                  <Badge variant="outline">{item.event_count} events</Badge>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.summary}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {memoryOverview.archive.length > 0 ? (
        <SectionCard
          title="Archive"
          icon={FolderOpen}
          description="Старые и superseded memory artefacts, исключенные из prompt."
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
