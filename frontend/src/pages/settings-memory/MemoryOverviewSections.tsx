import { Activity, Bot, Clock, Database, FolderOpen, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { QueryStateBlock } from "@/components/ui/page-shell";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import type { ServerMemoryOverviewResponse, ServerMemorySnapshotRecord } from "@/api";
import { MemorySnapshotActions, MemorySnapshotCard } from "./MemorySnapshotCard";
import { MemoryWorkerStateCard } from "./MemoryWorkerStateCard";

type MemoryOverviewSectionsProps = {
  memoryOverview?: ServerMemoryOverviewResponse;
  selectedMemoryServerId: number | null;
  memoryLoading: boolean;
  memoryActionKey: string | null;
  onArchiveMemorySnapshot: (snapshotId: number) => void | Promise<void>;
  onPromoteMemorySnapshotToNote: (snapshotId: number) => void | Promise<void>;
  onPromoteMemorySnapshotToSkill: (snapshotId: number) => void | Promise<void>;
};

function MemoryStats({ stats }: { stats: ServerMemoryOverviewResponse["stats"] }) {
  const items = [
    { label: "Канонические", value: stats.canonical },
    { label: "Паттерны", value: stats.patterns },
    { label: "Автоматизация", value: stats.automation_candidates },
    { label: "Навыки", value: stats.skill_drafts },
    { label: "Верификация", value: stats.revalidation_open },
    { label: "Эпизоды", value: stats.episodes },
    { label: "Архив", value: stats.archive },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7">
      {items.map((stat) => (
        <div key={stat.label} className="group/stat relative overflow-hidden rounded-xl border border-primary/5 bg-background/50 px-4 py-4 shadow-sm transition-all hover:border-primary/20 hover:bg-background/80 hover:shadow-md">
          <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 transition-opacity group-hover/stat:opacity-100" />
          <p className="relative z-10 text-xs font-bold uppercase tracking-widest text-muted-foreground/70 transition-colors group-hover/stat:text-primary">{stat.label}</p>
          <p className="relative z-10 mt-2 text-2xl font-black text-foreground/90">{stat.value}</p>
        </div>
      ))}
    </div>
  );
}

function CandidateSnapshotCard({
  item,
  memoryActionKey,
  onArchiveMemorySnapshot,
  onPromoteMemorySnapshotToNote,
  onPromoteMemorySnapshotToSkill,
}: {
  item: ServerMemorySnapshotRecord;
  memoryActionKey: string | null;
  onArchiveMemorySnapshot: (snapshotId: number) => void | Promise<void>;
  onPromoteMemorySnapshotToNote: (snapshotId: number) => void | Promise<void>;
  onPromoteMemorySnapshotToSkill: (snapshotId: number) => void | Promise<void>;
}) {
  return (
    <MemorySnapshotCard
      item={item}
      actions={
        <MemorySnapshotActions
          item={item}
          memoryActionKey={memoryActionKey}
          onArchive={onArchiveMemorySnapshot}
          onPromoteToNote={onPromoteMemorySnapshotToNote}
          onPromoteToSkill={onPromoteMemorySnapshotToSkill}
        />
      }
    />
  );
}

export function MemoryOverviewSections({
  memoryOverview,
  selectedMemoryServerId,
  memoryLoading,
  memoryActionKey,
  onArchiveMemorySnapshot,
  onPromoteMemorySnapshotToNote,
  onPromoteMemorySnapshotToSkill,
}: MemoryOverviewSectionsProps) {
  if (!memoryOverview) {
    return (
      <QueryStateBlock loading={!!(selectedMemoryServerId && memoryLoading)}>
        <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
          Выберите сервер в списке слева для просмотра сведений долгосрочной памяти.
        </div>
      </QueryStateBlock>
    );
  }

  const candidateSnapshots = [
    ...memoryOverview.patterns,
    ...memoryOverview.automation_candidates,
    ...memoryOverview.skill_drafts,
  ];

  return (
    <>
      <MemoryStats stats={memoryOverview.stats} />

      <SectionCard title="Состояние фоновых служб" icon={Activity} description="Мониторинг фоновых процессов анализа и выполнения">
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          <MemoryWorkerStateCard label="Консолидация памяти" state={memoryOverview.worker_states?.memory_dreams || memoryOverview.daemon_state} />
          <MemoryWorkerStateCard label="Выполнение агентов" state={memoryOverview.worker_states?.agent_execution} />
          <MemoryWorkerStateCard label="Службы наблюдения" state={memoryOverview.worker_states?.watchers} />
        </div>
      </SectionCard>

      {memoryOverview.canonical.length > 0 ? (
        <SectionCard title="Канонические записи" icon={Database} description="Подтвержденные и структурированные факты о сервере">
          <div className="space-y-2">
            {memoryOverview.canonical.map((item) => (
              <MemorySnapshotCard key={item.id} item={item} />
            ))}
          </div>
        </SectionCard>
      ) : null}

      {candidateSnapshots.length > 0 ? (
        <SectionCard title="Выявленные паттерны и предложения" icon={Bot} description="Кандидаты для пополнения базы знаний">
          <div className="space-y-3">
            {candidateSnapshots.map((item) => (
              <CandidateSnapshotCard
                key={item.id}
                item={item}
                memoryActionKey={memoryActionKey}
                onArchiveMemorySnapshot={onArchiveMemorySnapshot}
                onPromoteMemorySnapshotToNote={onPromoteMemorySnapshotToNote}
                onPromoteMemorySnapshotToSkill={onPromoteMemorySnapshotToSkill}
              />
            ))}
          </div>
        </SectionCard>
      ) : null}

      {memoryOverview.revalidation.length > 0 ? (
        <SectionCard title="Очередь верификации" icon={RefreshCw} description="Записи и утверждения, требующие повторного подтверждения">
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
        <SectionCard title="Недавние сессии активности" icon={Clock} description="Сводная хроника сессий и выполненных операций">
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
        <SectionCard title="Архив памяти" icon={FolderOpen} description="Устаревшие версии канонических записей и деактивированные артефакты">
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
