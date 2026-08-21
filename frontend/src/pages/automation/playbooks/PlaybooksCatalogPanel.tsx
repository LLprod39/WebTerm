import {
  AlertTriangle,
  BookOpen,
  Clock3,
  FilePlus2,
  GitBranch,
  History,
  LayoutGrid,
  RefreshCcw,
  Search,
  Upload,
} from "lucide-react";

import type { AnsibleStatus, PlaybookCategory, PlaybookRun, PlaybookSummary } from "@/api/playbooks";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, QueryStateBlock } from "@/components/ui/page-shell";
import { cn, relativeTime } from "@/lib/utils";
import { PlaybookCard } from "../PlaybookCard";
import { CATEGORIES, CATEGORY_META, RUN_STATUS_META } from "../constants";

export interface PlaybooksCatalogPanelProps {
  lang: string;
  tr: (ru: string, en: string) => string;
  playbooks: PlaybookSummary[];
  recentRuns: PlaybookRun[];
  playbooksLoading: boolean;
  playbooksError: string;
  search: string;
  setSearch: (value: string) => void;
  categoryFilter: PlaybookCategory | "all";
  setCategoryFilter: (value: PlaybookCategory | "all") => void;
  showHistory: boolean;
  setShowHistory: (updater: (value: boolean) => boolean) => void;
  ansible: AnsibleStatus | undefined;
  ansibleAvailable: boolean;
  onRefreshRuns: () => void;
  onRetryPlaybooks: () => void;
  onOpenNew: () => void;
  onOpenImport: () => void;
  onOpenEdit: (id: number) => void;
  onStartRun: (id: number) => void;
  onDuplicate: (id: number) => void;
  onDelete: (playbook: PlaybookSummary) => void;
  onOpenRun: (run: PlaybookRun) => void;
}

export function PlaybooksCatalogPanel(props: PlaybooksCatalogPanelProps) {
  const {
    lang, tr, playbooks, recentRuns, playbooksLoading, playbooksError,
    search, setSearch, categoryFilter, setCategoryFilter, showHistory, setShowHistory,
    ansible, ansibleAvailable, onRefreshRuns, onRetryPlaybooks,
    onOpenNew, onOpenImport, onOpenEdit, onStartRun, onDuplicate, onDelete, onOpenRun,
  } = props;

  return (
      <section className="mx-auto w-full max-w-[1320px] space-y-5">
        <header className="flex flex-col gap-5 border-b border-border/70 pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-start gap-3.5">
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-foreground text-background">
              <BookOpen className="h-5 w-5" />
            </span>
            <div>
              <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground">Ansible</h1>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                {tr(
                  "Проекты, проверки и запуски инфраструктуры — в одном рабочем месте.",
                  "Infrastructure projects, checks, and runs in one workspace.",
                )}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" className="h-9 gap-1.5" onClick={onOpenNew}>
              <FilePlus2 className="h-4 w-4" />
              {tr("Создать Ansible", "Create Ansible")}
            </Button>
            <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={onOpenImport}>
              <Upload className="h-4 w-4" />
              {tr("Импортировать", "Import")}
            </Button>
          </div>
        </header>

        <RuntimeNotice tr={tr} ansible={ansible} ready={ansibleAvailable} />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="inline-flex w-fit rounded-lg bg-secondary/60 p-1" role="tablist" aria-label={tr("Раздел Ansible", "Ansible section")}>
            <button
              type="button"
              role="tab"
              aria-selected={!showHistory}
              onClick={() => setShowHistory(() => false)}
              className={cn(
                "flex h-8 items-center gap-2 rounded-md px-3 text-xs font-medium transition-colors",
                !showHistory ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              {tr("Проекты", "Projects")}
              <span className="text-muted-foreground">{playbooks.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={showHistory}
              onClick={() => setShowHistory(() => true)}
              className={cn(
                "flex h-8 items-center gap-2 rounded-md px-3 text-xs font-medium transition-colors",
                showHistory ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <History className="h-3.5 w-3.5" />
              {tr("Запуски", "Runs")}
            </button>
          </div>

          {!showHistory ? (
            <div className="flex min-w-0 flex-1 sm:max-w-md sm:justify-end">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={tr("Найти проект", "Find a project")}
                  className="h-9 bg-card pl-9"
                />
              </div>
            </div>
          ) : null}
        </div>

        {!showHistory ? (
          <div className="flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="group" aria-label={tr("Фильтр по категории", "Category filter")}>
            {(["all", ...CATEGORIES] as const).map((category) => {
              const active = categoryFilter === category;
              const label = category === "all"
                ? tr("Все", "All")
                : lang === "ru" ? CATEGORY_META[category].labelRu : CATEGORY_META[category].labelEn;
              return (
                <button
                  key={category}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setCategoryFilter(category)}
                  className={cn(
                    "h-7 shrink-0 rounded-full px-3 text-xs font-medium transition-colors",
                    active ? "bg-foreground text-background" : "bg-secondary/55 text-muted-foreground hover:bg-secondary hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        ) : null}

        {!showHistory ? (
          <div>
            <QueryStateBlock
              loading={playbooksLoading}
              error={playbooksError || undefined}
              loadingText={tr("Загружаем проекты…", "Loading projects…")}
              errorText={playbooksError ? `${tr("Не удалось загрузить playbooks", "Failed to load playbooks")}: ${playbooksError}` : undefined}
              retryText={tr("Повторить", "Retry")}
              onRetry={onRetryPlaybooks}
            >
              {playbooks.length === 0 ? (
                <EmptyState
                  icon={<GitBranch className="h-5 w-5" />}
                  title={search.trim() || categoryFilter !== "all" ? tr("Ничего не найдено", "Nothing found") : tr("Подключите первый Ansible-проект", "Connect your first Ansible project")}
                  description={search.trim() || categoryFilter !== "all"
                    ? tr("Измените поиск или категорию.", "Change the search or category.")
                    : tr("Создайте Ansible и напишите или вставьте YAML. Импорт будет доступен внутри редактора.", "Create Ansible and write or paste YAML. Import is available inside the editor.")}
                  actions={search.trim() || categoryFilter !== "all" ? (
                    <Button size="sm" variant="outline" onClick={() => { setSearch(""); setCategoryFilter("all"); }}>{tr("Сбросить", "Reset")}</Button>
                  ) : (
                    <Button size="sm" onClick={onOpenNew}><FilePlus2 className="h-4 w-4" />{tr("Создать Ansible", "Create Ansible")}</Button>
                  )}
                />
              ) : (
                <div className="grid gap-3 lg:grid-cols-2" role="list" aria-label={tr("Проекты Ansible", "Ansible projects")}>
                  {playbooks.map((playbook) => (
                    <PlaybookCard
                      key={playbook.id}
                      playbook={playbook}
                      lang={lang}
                      executionReady={ansibleAvailable}
                      onOpen={() => onOpenEdit(playbook.id)}
                      onRun={() => onStartRun(playbook.id)}
                      onDuplicate={() => onDuplicate(playbook.id)}
                      onDelete={() => onDelete(playbook)}
                    />
                  ))}
                </div>
              )}
            </QueryStateBlock>
          </div>
        ) : (
          <RecentRuns lang={lang} tr={tr} runs={recentRuns} onRefresh={onRefreshRuns} onOpen={onOpenRun} />
        )}
      </section>
  );
}

function RuntimeNotice({ tr, ansible, ready }: { tr: (ru: string, en: string) => string; ansible?: AnsibleStatus; ready: boolean }) {
  if (ready) return null;
  const validatorReady = Boolean(ansible?.validation_available ?? ansible?.method);
  return (
    <div role="status" className="flex items-start gap-3 border-l-2 border-warning bg-warning/[0.045] px-4 py-3 sm:items-center">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning sm:mt-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">
          {validatorReady ? tr("Worker запуска не подключён", "Execution worker is offline") : tr("Ansible требует настройки", "Ansible needs setup")}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {validatorReady
            ? tr("Проекты и проверка YAML доступны. Настроить запуск можно сейчас, выполнить — после подключения worker.", "Projects and YAML validation remain available. Configure now; execution resumes when the worker connects.")
            : tr("Проверьте Ansible runtime в настройках системы.", "Check the Ansible runtime in system settings.")}
        </p>
        <StatusBadge label={validatorReady ? tr("Только проверка", "Validation only") : tr("Нужна настройка", "Setup required")} tone="warning" className="mt-2 normal-case tracking-normal sm:hidden" />
      </div>
      <StatusBadge label={validatorReady ? tr("Только проверка", "Validation only") : tr("Нужна настройка", "Setup required")} tone="warning" className="hidden normal-case tracking-normal sm:inline-flex" />
    </div>
  );
}

function RecentRuns({
  lang,
  tr,
  runs,
  onRefresh,
  onOpen,
}: {
  lang: string;
  tr: (ru: string, en: string) => string;
  runs: PlaybookRun[];
  onRefresh: () => void;
  onOpen: (run: PlaybookRun) => void;
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-border/80 bg-card/55" aria-labelledby="recent-runs-title">
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-3">
        <div>
          <h2 id="recent-runs-title" className="text-sm font-semibold text-foreground">{tr("История запусков", "Run history")}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">{tr("Последние операции Ansible", "Recent Ansible operations")}</p>
        </div>
        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={onRefresh} aria-label={tr("Обновить запуски", "Refresh runs")}>
          <RefreshCcw className="h-3.5 w-3.5" />
        </Button>
      </div>
      {runs.length ? runs.slice(0, 12).map((run) => {
        const meta = RUN_STATUS_META[run.status];
        return (
          <button key={run.id} type="button" onClick={() => onOpen(run)} className="grid w-full gap-2 border-b border-border/60 px-4 py-3 text-left last:border-0 hover:bg-secondary/25 sm:grid-cols-[minmax(0,1fr)_140px_100px] sm:items-center">
            <span className="truncate text-sm font-medium text-foreground">{run.playbook_name}</span>
            <span className={cn("text-xs", meta?.className)}>{meta ? (lang === "ru" ? meta.labelRu : meta.labelEn) : run.status}</span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground"><Clock3 className="h-3 w-3" />{run.started_at ? relativeTime(run.started_at) : "—"}</span>
          </button>
        );
      }) : <p className="px-4 py-12 text-center text-sm text-muted-foreground">{tr("Запусков пока нет", "No runs yet")}</p>}
    </section>
  );
}
