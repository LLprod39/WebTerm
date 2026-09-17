import { ScrollText } from "lucide-react";

import type { KubernetesPodLogsResponse, KubernetesPodRef } from "@/api";
import { Button } from "@/components/ui/button";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import { LOG_TAIL } from "./types";

export function PodLogsPanel({
  lang,
  pod,
  logs,
  loading,
  error,
  explaining,
  onRefresh,
  onExplain,
}: {
  lang: string;
  pod: KubernetesPodRef | null;
  logs?: KubernetesPodLogsResponse;
  loading: boolean;
  error: unknown;
  explaining: boolean;
  onRefresh: () => void;
  onExplain: () => void;
}) {
  const lines = logs?.lines ?? [];
  const canExplain = Boolean(pod && lines.length > 0 && !loading && !explaining);

  return (
    <section data-ui-slot="cockpit-logs" className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/70 px-4 py-3.5 sm:px-5">
        <div className="min-w-0 max-w-xl">
          <h3 className="text-sm font-semibold text-foreground">
            {localize(lang, "Логи", "Logs")}
          </h3>
          <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
            {localize(
              lang,
              "stdout/stderr контейнера. Читайте напрямую или нажмите «Разобрать».",
              "Container stdout/stderr. Read directly or hit Explain.",
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" className="h-9" disabled={!pod || loading} onClick={onRefresh}>
            {localize(lang, "Обновить", "Refresh")}
          </Button>
          <Button type="button" size="sm" className="h-9 px-3.5" disabled={!canExplain} onClick={onExplain}>
            {localize(lang, "Разобрать логи", "Explain logs")}
          </Button>
        </div>
      </div>

      <div className="min-h-[16rem] flex-1 overflow-auto bg-secondary/20">
        {!pod ? (
          <EmptyState
            className="m-0 border-0 bg-transparent py-14"
            icon={<ScrollText className="h-6 w-6" />}
            title={localize(lang, "Логи не открыты", "No logs open")}
            description={localize(lang, "Откройте под из списка.", "Open a pod from the list.")}
          />
        ) : loading ? (
          <pre className="m-0 px-5 py-5 font-mono text-sm leading-6 text-muted-foreground">
            {localize(lang, "Загрузка логов…", "Loading logs…")}
          </pre>
        ) : error ? (
          <div className="m-4 rounded-sm border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {localize(lang, "Не удалось загрузить логи. Попробуйте обновить.", "Couldn’t load logs. Try refresh.")}
          </div>
        ) : logs && !logs.available ? (
          <div className="space-y-3 px-5 py-5 text-sm text-muted-foreground">
            <StatusBadge label={logs.source || "unavailable"} tone="warning" />
            <p>{logs.message || localize(lang, "Снимок логов недоступен.", "Log snapshot unavailable.")}</p>
          </div>
        ) : (
          <pre
            className="m-0 whitespace-pre-wrap break-all px-4 py-4 font-mono text-[13px] leading-6 text-foreground/90 sm:px-5"
            aria-live="polite"
          >
            {lines.length ? lines.join("\n") : localize(lang, "(пусто)", "(empty)")}
          </pre>
        )}
      </div>

      <div className="border-t border-border/70 px-4 py-2.5 font-mono text-xs text-muted-foreground sm:px-5">
        {localize(lang, "хвост", "tail")} · {logs?.policy?.requested_tail_lines || LOG_TAIL}{" "}
        {localize(lang, "строк", "lines")}
        {logs?.truncated ? ` · ${localize(lang, "обрезано", "truncated")}` : ""}
        {logs ? ` · ${logs.line_count}` : ""}
      </div>
    </section>
  );
}
