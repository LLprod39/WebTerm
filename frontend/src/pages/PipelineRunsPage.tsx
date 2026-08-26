import { StudioNav } from "@/components/StudioNav";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  RotateCcw,
  Search,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { studioRuns } from "@/lib/api";
import { StudioHero, HeroStatChip, HeroActionButton } from "@/components/studio/StudioHero";
import { PipelineRunDetail, StatusBadge } from "@/components/studio/PipelineRunDetail";
import { formatRunDate, formatRunDuration } from "@/components/studio/pipelineRunFormatters";
import { EmptyState } from "@/components/ui/page-shell";
import { SkeletonList } from "@/components/ui/list-state";
import { localize, useI18n } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Runs list
// ---------------------------------------------------------------------------
const STATUS_FILTERS = ["all", "running", "completed", "failed", "pending", "stopped"] as const;
type StatusFilter = typeof STATUS_FILTERS[number];
const TIME_FILTERS = ["all", "24h", "7d"] as const;
type TimeFilter = typeof TIME_FILTERS[number];

function statusFilterLabel(status: StatusFilter, lang: string, count: number) {
  const labels: Record<StatusFilter, string> = {
    all: localize(lang, "Все", "All"),
    running: localize(lang, "В работе", "Running"),
    completed: localize(lang, "Выполнены", "Completed"),
    failed: localize(lang, "Ошибки", "Failed"),
    pending: localize(lang, "Ожидают", "Pending"),
    stopped: localize(lang, "Остановлены", "Stopped"),
  };
  return status === "all" ? `${labels.all} (${count})` : labels[status];
}

function timeFilterLabel(filter: TimeFilter, lang: string) {
  if (filter === "24h") return localize(lang, "24 часа", "24h");
  if (filter === "7d") return localize(lang, "7 дней", "7d");
  return localize(lang, "Всё время", "All time");
}

function runTimestamp(run: { started_at: string | null; created_at: string }) {
  return new Date(run.started_at || run.created_at).getTime();
}

export default function PipelineRunsPage() {
  const navigate = useNavigate();
  const { lang } = useI18n();
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const autoSelectedRunRef = useRef(false);

  const { data: runs = [], isLoading, refetch } = useQuery({
    queryKey: ["studio", "runs"],
    queryFn: studioRuns.list,
    refetchInterval: 5000,
  });

  const filtered = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const now = Date.now();

    return runs.filter((run) => {
      if (statusFilter !== "all" && run.status !== statusFilter) return false;

      if (timeFilter !== "all") {
        const ageMs = now - runTimestamp(run);
        const limitMs = timeFilter === "24h" ? 24 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
        if (Number.isFinite(ageMs) && ageMs > limitMs) return false;
      }

      if (!query) return true;
      const haystack = [
        run.id,
        run.pipeline_name,
        run.status,
        run.error,
        run.triggered_by,
        run.trigger_type,
        run.trigger_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [runs, searchQuery, statusFilter, timeFilter]);

  const statusCount = (s: string) => runs.filter((r) => r.status === s).length;

  useEffect(() => {
    if (!filtered.length) {
      setSelectedRunId(null);
      autoSelectedRunRef.current = false;
      return;
    }

    if (selectedRunId && !filtered.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(filtered[0].id);
      autoSelectedRunRef.current = true;
      return;
    }

    const canShowSplitPane = typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches;
    if (!selectedRunId && !autoSelectedRunRef.current && canShowSplitPane) {
      setSelectedRunId(filtered[0].id);
      autoSelectedRunRef.current = true;
    }
  }, [filtered, selectedRunId]);

  return (
    <div className="flex flex-col h-full">
      <StudioNav />
      <StudioHero
        kicker={localize(lang, "Пайплайны", "Pipelines")}
        title={localize(lang, "История запусков", "Run history")}
        titleIcon={<Workflow className="h-7 w-7 text-primary" />}
        description={localize(lang, "Статусы, ошибки и вывод каждого шага.", "Statuses, errors, and output for every step.")}
        stats={
          <>
            <HeroStatChip icon={<CheckCircle2 className="h-3.5 w-3.5" />} label={`${statusCount("completed")} ${localize(lang, "выполнено", "completed")}`} />
            {statusCount("failed") > 0 && <HeroStatChip icon={<XCircle className="h-3.5 w-3.5" />} label={`${statusCount("failed")} ${localize(lang, "с ошибкой", "failed")}`} />}
            {statusCount("running") > 0 && <HeroStatChip icon={<Loader2 className="h-3.5 w-3.5" />} label={`${statusCount("running")} ${localize(lang, "в работе", "running")}`} />}
          </>
        }
        actions={
          <HeroActionButton onClick={() => refetch()} icon={<RotateCcw className="h-4 w-4" />} label={localize(lang, "Обновить", "Refresh")} />
        }
      />
      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
      {/* Left: runs list */}
      <div className={`min-w-0 flex-col border-r border-border ${selectedRunId ? "hidden lg:flex lg:w-80 lg:shrink-0" : "flex w-full flex-1"}`}>
        {/* Filters */}
        <div className="space-y-3 border-b border-border/60 bg-secondary/10 px-4 py-3 shrink-0">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={localize(lang, "Пайплайн, ID, ошибка или инициатор", "Pipeline, ID, error, or actor")}
              aria-label={localize(lang, "Поиск запусков", "Search runs")}
              className="h-10 bg-background/70 pl-9"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {STATUS_FILTERS.map((s) => (
              <button
                type="button"
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`min-h-9 rounded-lg border px-3 py-1 text-xs font-medium transition-all duration-150 ${
                  statusFilter === s
                    ? "bg-primary/15 text-primary border-primary/30 shadow-sm"
                    : "border-border/50 text-muted-foreground hover:text-foreground hover:bg-secondary/40"
                }`}
              >
                {statusFilterLabel(s, lang, runs.length)}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {TIME_FILTERS.map((filter) => (
              <button
                type="button"
                key={filter}
                onClick={() => setTimeFilter(filter)}
                className={`min-h-9 rounded-lg border px-3 py-1 text-xs font-medium transition-all duration-150 ${
                  timeFilter === filter
                    ? "bg-info/15 text-info border-info/30 shadow-sm"
                    : "border-border/50 text-muted-foreground hover:text-foreground hover:bg-secondary/40"
                }`}
              >
                {timeFilterLabel(filter, lang)}
              </button>
            ))}
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto">
          {isLoading && <div className="p-4"><SkeletonList rows={6} /></div>}

          {!isLoading && filtered.length === 0 && (
            <div className="p-4">
              <EmptyState
                icon={<Workflow className="h-5 w-5" />}
                title={runs.length ? localize(lang, "Под фильтры ничего не подходит", "No runs match the filters") : localize(lang, "Нет запусков", "No runs")}
                description={
                  runs.length
                    ? localize(lang, "Измените или сбросьте фильтры, чтобы увидеть запуски.", "Change or reset the filters to see runs.")
                    : localize(lang, "Запустите пайплайн из Студии, чтобы увидеть историю здесь.", "Run a pipeline from Studio to see history here.")
                }
                actions={
                  runs.length ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setSearchQuery("");
                        setStatusFilter("all");
                        setTimeFilter("all");
                      }}
                    >
                      {localize(lang, "Сбросить фильтры", "Reset filters")}
                    </Button>
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => navigate("/studio")}>
                      {localize(lang, "Перейти к пайплайнам", "Open pipelines")}
                    </Button>
                  )
                }
              />
            </div>
          )}

          {filtered.map((run) => (
            <button
              type="button"
              key={run.id}
              onClick={() => setSelectedRunId(run.id)}
              className={`group relative min-h-20 w-full border-b border-border/50 px-4 py-3 text-left transition-all duration-150 ${
                selectedRunId === run.id
                  ? "bg-primary/6 border-l-2 border-l-primary"
                  : "hover:bg-secondary/25 border-l-2 border-l-transparent"
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-sm font-medium truncate text-foreground">{run.pipeline_name}</span>
                <StatusBadge status={run.status} lang={lang} />
              </div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground/70">
                <span className="font-mono">#{run.id}</span>
                <span className="text-border">·</span>
                <span>{formatRunDate(run.started_at || run.created_at, lang)}</span>
                {run.duration_seconds && (
                  <>
                    <span className="text-border">·</span>
                    <span>{formatRunDuration(run.duration_seconds, lang)}</span>
                  </>
                )}
              </div>
              <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground/70">
                <span>{run.trigger_type || localize(lang, "ручной запуск", "manual")}</span>
                {run.triggered_by ? (
                  <>
                    <span className="text-border">·</span>
                    <span className="truncate">{run.triggered_by}</span>
                  </>
                ) : null}
              </div>
              {run.error && (
                <div className="mt-1.5 flex items-center gap-1 text-xs text-red-400">
                  <span className="h-1 w-1 rounded-full bg-red-400 shrink-0" />
                  <span className="truncate">{run.error}</span>
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Right: run detail */}
      {selectedRunId && (
        <div className="min-w-0 flex-1 overflow-hidden">
          <PipelineRunDetail runId={selectedRunId} onClose={() => setSelectedRunId(null)} lang={lang} />
        </div>
      )}
      </div>
    </div>
  );
}
