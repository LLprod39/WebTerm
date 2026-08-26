import { useDeferredValue, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookOpen,
  Clock3,
  FilePlus2,
  GitBranch,
  History,
  LayoutGrid,
  Loader2,
  Pin,
  RefreshCcw,
  Search,
  Upload,
} from "lucide-react";

import {
  listPlaybookRunHistory,
  type AnsibleStatus,
  type PlaybookCategory,
  type PlaybookRun,
  type PlaybookRunHistoryItem,
  type PlaybookSummary,
} from "@/api/playbooks";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, QueryStateBlock } from "@/components/ui/page-shell";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
                  "Проекты, проверки и запуски инфраструктуры.",
                  "Infrastructure projects, checks, and runs.",
                )}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" className="h-9 gap-1.5" onClick={onOpenImport}>
              <Upload className="h-4 w-4" />
              {tr("Импортировать", "Import")}
            </Button>
            <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={onOpenNew}>
              <FilePlus2 className="h-4 w-4" />
              {tr("Создать с нуля", "Create from scratch")}
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
              errorText={playbooksError ? `${tr("Не удалось загрузить проекты", "Failed to load projects")}: ${playbooksError}` : undefined}
              retryText={tr("Повторить", "Retry")}
              onRetry={onRetryPlaybooks}
            >
              {playbooks.length === 0 ? (
                <EmptyState
                  icon={<GitBranch className="h-5 w-5" />}
                  title={search.trim() || categoryFilter !== "all" ? tr("Ничего не найдено", "Nothing found") : tr("Проектов пока нет", "No projects yet")}
                  description={search.trim() || categoryFilter !== "all"
                    ? tr("Измените поиск или категорию.", "Change the search or category.")
                    : tr("Создайте проект или импортируйте готовый Ansible YAML.", "Create a project or import an existing Ansible YAML file.")}
                  actions={search.trim() || categoryFilter !== "all" ? (
                    <Button size="sm" variant="outline" onClick={() => { setSearch(""); setCategoryFilter("all"); }}>{tr("Сбросить", "Reset")}</Button>
                  ) : (
                    <div className="flex flex-wrap justify-center gap-2">
                      <Button size="sm" onClick={onOpenImport}><Upload className="h-4 w-4" />{tr("Импортировать", "Import")}</Button>
                      <Button size="sm" variant="outline" onClick={onOpenNew}><FilePlus2 className="h-4 w-4" />{tr("Создать с нуля", "Create from scratch")}</Button>
                    </div>
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
          <RecentRuns lang={lang} tr={tr} runs={recentRuns} playbooks={playbooks} onRefresh={onRefreshRuns} onOpen={onOpenRun} />
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
          {validatorReady ? tr("Сервис запуска недоступен", "Execution service is unavailable") : tr("Ansible требует настройки", "Ansible needs setup")}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {validatorReady
            ? tr("Проекты и проверка YAML доступны. Запуск станет доступен после восстановления сервиса.", "Projects and YAML validation remain available. Runs will resume when the service is restored.")
            : tr("Проверьте настройки Ansible в разделе системы.", "Check the Ansible settings in the system section.")}
        </p>
        <StatusBadge label={validatorReady ? tr("Только проверка", "Validation only") : tr("Нужна настройка", "Setup required")} tone="warning" className="mt-2 normal-case tracking-normal sm:hidden" />
      </div>
      <StatusBadge label={validatorReady ? tr("Только проверка", "Validation only") : tr("Нужна настройка", "Setup required")} tone="warning" className="hidden normal-case tracking-normal sm:inline-flex" />
      <Button asChild size="sm" variant="outline" className="h-8 shrink-0"><a href="/settings/readiness">{tr("Проверить готовность", "Check readiness")}</a></Button>
    </div>
  );
}

function RecentRuns({
  lang,
  tr,
  runs,
  playbooks,
  onRefresh,
  onOpen,
}: {
  lang: string;
  tr: (ru: string, en: string) => string;
  runs: PlaybookRun[];
  playbooks: PlaybookSummary[];
  onRefresh: () => void;
  onOpen: (run: PlaybookRun) => void;
}) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [status, setStatus] = useState("all");
  const [playbookId, setPlaybookId] = useState("all");
  const historyQuery = useInfiniteQuery({
    queryKey: ["playbook-run-history", status, playbookId, deferredQuery],
    queryFn: ({ pageParam }) => listPlaybookRunHistory({
      cursor: pageParam || undefined,
      limit: 25,
      status: status === "all" ? undefined : [status],
      playbookId: playbookId === "all" ? undefined : Number(playbookId),
      q: deferredQuery,
    }),
    initialPageParam: 0,
    getNextPageParam: (page) => page.page.has_more ? page.page.next_cursor || undefined : undefined,
    retry: 2,
  });
  const history = historyQuery.data?.pages.flatMap((page) => page.items) || [];
  const queryText = deferredQuery.trim().toLowerCase();
  const activeRuns = runs
    .filter((run) => run.status === "pending" || run.status === "running")
    .filter((run) => status === "all" || run.status === status)
    .filter((run) => playbookId === "all" || run.playbook_id === Number(playbookId))
    .filter((run) => !queryText || `${run.playbook_name} ${run.id}`.toLowerCase().includes(queryText))
    .sort((left, right) => right.id - left.id);
  const activeIds = new Set(activeRuns.map((run) => run.id));
  const rows: Array<{ run: PlaybookRun | PlaybookRunHistoryItem; active: boolean }> = [
    ...activeRuns.map((run) => ({ run, active: true })),
    ...history.filter((run) => !activeIds.has(run.id)).map((run) => ({ run, active: false })),
  ];

  return (
    <section className="overflow-hidden rounded-lg border border-border/80 bg-card/55" aria-labelledby="recent-runs-title">
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-3">
        <div>
          <h2 id="recent-runs-title" className="text-sm font-semibold text-foreground">{tr("История запусков", "Run history")}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">{tr("Последние операции Ansible", "Recent Ansible operations")}</p>
        </div>
        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => { onRefresh(); void historyQuery.refetch(); }} aria-label={tr("Обновить запуски", "Refresh runs")}>
          <RefreshCcw className={cn("h-3.5 w-3.5", historyQuery.isRefetching && "animate-spin")} />
        </Button>
      </div>
      <div className="grid gap-2 border-b border-border/70 bg-surface-0/35 p-3 md:grid-cols-[minmax(0,1fr)_180px_220px]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={tr("Найти запуск", "Find a run")} className="h-9 bg-card pl-9" />
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger aria-label={tr("Статус запуска", "Run status")} className="h-9 bg-card"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{tr("Все статусы", "All statuses")}</SelectItem>
            {(["pending", "running", "completed", "failed", "partial", "cancelled"] as const).map((value) => (
              <SelectItem key={value} value={value}>{lang === "ru" ? RUN_STATUS_META[value].labelRu : RUN_STATUS_META[value].labelEn}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={playbookId} onValueChange={setPlaybookId}>
          <SelectTrigger aria-label={tr("Проект запуска", "Run project")} className="h-9 bg-card"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{tr("Все проекты", "All projects")}</SelectItem>
            {playbooks.map((playbook) => <SelectItem key={playbook.id} value={String(playbook.id)}>{playbook.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {historyQuery.isError ? (
        <div className="border-b border-warning/25 bg-warning/5 px-4 py-2 text-xs text-muted-foreground" role="alert">
          {tr("Полная история временно недоступна; активные запуски всё ещё показаны.", "Full history is temporarily unavailable; active runs are still shown.")}
        </div>
      ) : null}
      {rows.length ? rows.map(({ run, active }) => {
        const meta = RUN_STATUS_META[run.status];
        const fullRun = "target_server_ids" in run ? run : historyItemToRun(run);
        return (
          <button key={run.id} type="button" onClick={() => onOpen(fullRun)} className={cn("grid w-full gap-2 border-b border-border/60 px-4 py-3 text-left last:border-0 hover:bg-secondary/25 sm:grid-cols-[minmax(0,1fr)_150px_150px_100px] sm:items-center", active && "border-l-2 border-l-primary bg-primary/[0.035]")}>
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 truncate text-sm font-medium text-foreground">{active ? <Pin className="h-3 w-3 shrink-0 text-primary" /> : null}{run.playbook_name}</span>
              <span className="mt-0.5 block text-2xs text-muted-foreground">#{run.id}{active ? ` · ${tr("активный", "active")}` : ""}{fullRun.options?.dry_run ? ` · ${tr("проверочный прогон", "dry run")}` : ""}</span>
            </span>
            <span className={cn("text-xs", meta?.className)}>{meta ? (lang === "ru" ? meta.labelRu : meta.labelEn) : run.status}</span>
            <span className="text-xs text-muted-foreground">
              {tr("Хосты", "Hosts")}: {run.summary?.hosts_ok ?? 0}/{run.summary?.hosts_total ?? fullRun.target_server_ids.length}
              {(run.summary?.tasks_failed || 0) > 0 ? ` · ${tr("ошибок", "failed")} ${run.summary.tasks_failed}` : ""}
            </span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground"><Clock3 className="h-3 w-3" />{run.started_at ? relativeTime(run.started_at) : "—"}</span>
          </button>
        );
      }) : historyQuery.isPending ? (
        <p className="flex items-center justify-center gap-2 px-4 py-12 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{tr("Загружаем историю…", "Loading history…")}</p>
      ) : <p className="px-4 py-12 text-center text-sm text-muted-foreground">{tr("Запусков не найдено", "No runs found")}</p>}
      {historyQuery.hasNextPage ? (
        <div className="flex justify-center border-t border-border/60 p-3">
          <Button size="sm" variant="outline" disabled={historyQuery.isFetchingNextPage} onClick={() => void historyQuery.fetchNextPage()}>
            {historyQuery.isFetchingNextPage ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}{tr("Загрузить ещё", "Load more")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function historyItemToRun(item: PlaybookRunHistoryItem): PlaybookRun {
  return {
    id: item.id,
    playbook_id: item.playbook_id,
    status: item.status,
    playbook_name: item.playbook_name,
    target_server_ids: [],
    target_group_ids: [],
    options: {},
    summary: item.summary,
    progress: { phase: item.phase, finished: !["pending", "running"].includes(item.status) },
    inventory_preview: "",
    error_message: item.failure?.message || "",
    cancel_requested: false,
    started_at: item.started_at,
    finished_at: item.finished_at,
    created_at: item.created_at,
    live_log: "",
    host_results: [],
  };
}
