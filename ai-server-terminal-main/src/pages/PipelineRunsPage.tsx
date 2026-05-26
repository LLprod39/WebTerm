import { StudioNav } from "@/components/StudioNav";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  RotateCcw,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { studioRuns } from "@/lib/api";
import { StudioHero, HeroStatChip, HeroActionButton } from "@/components/studio/StudioHero";
import { PipelineRunDetail, StatusBadge, formatRunDate, formatRunDuration } from "@/components/studio/PipelineRunDetail";
import { localize, useI18n } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Runs list
// ---------------------------------------------------------------------------
const STATUS_FILTERS = ["all", "running", "completed", "failed", "pending", "stopped"] as const;
type StatusFilter = typeof STATUS_FILTERS[number];

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

export default function PipelineRunsPage() {
  const navigate = useNavigate();
  const { lang } = useI18n();
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const autoSelectedRunRef = useRef(false);

  const { data: runs = [], isLoading, refetch } = useQuery({
    queryKey: ["studio", "runs"],
    queryFn: studioRuns.list,
    refetchInterval: 5000,
  });

  const filtered = runs.filter((r) => {
    if (statusFilter !== "all" && r.status !== statusFilter) return false;
    return true;
  });

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
        kicker="Studio / Runs"
        title={localize(lang, "История запусков", "Execution History")}
        titleIcon={<Workflow className="h-7 w-7 text-primary" />}
        description={localize(lang, "Следите за pipeline run, проверяйте ошибки и открывайте подробный вывод по каждому шагу.", "Monitor pipeline runs, inspect failures, and open detailed output for each step.")}
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
      <div className="flex min-h-0 flex-1">
      {/* Left: runs list */}
      <div className={`flex-col border-r border-border ${selectedRunId ? "hidden lg:flex lg:w-80 lg:shrink-0" : "flex flex-1"}`}>
        {/* Filters */}
        <div className="px-4 py-2.5 border-b border-border/60 bg-secondary/10 shrink-0">
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
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto">
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
              <Loader2 className="h-4 w-4 animate-spin mr-2" /> Загрузка…
            </div>
          )}

          {!isLoading && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground text-sm gap-2">
              <Workflow className="h-8 w-8 text-muted-foreground/30" />
              <p>{localize(lang, "Нет запусков", "No runs")}</p>
              <Button size="sm" variant="outline" className="mt-2 h-10" onClick={() => navigate("/studio")}>
                {localize(lang, "Перейти к пайплайнам", "Open pipelines")}
              </Button>
            </div>
          )}

          {filtered.map((run) => (
            <button
              type="button"
              key={run.id}
              onClick={() => setSelectedRunId(run.id === selectedRunId ? null : run.id)}
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
              <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
                <span className="font-mono">#{run.id}</span>
                <span className="text-border">·</span>
                <span>{formatRunDate(run.started_at || run.created_at)}</span>
                {run.duration_seconds && (
                  <>
                    <span className="text-border">·</span>
                    <span>{formatRunDuration(run.duration_seconds)}</span>
                  </>
                )}
              </div>
              {run.error && (
                <div className="mt-1.5 flex items-center gap-1 text-[11px] text-red-400">
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
        <div className="flex-1 overflow-hidden">
          <PipelineRunDetail runId={selectedRunId} onClose={() => setSelectedRunId(null)} lang={lang} />
        </div>
      )}
      </div>
    </div>
  );
}
