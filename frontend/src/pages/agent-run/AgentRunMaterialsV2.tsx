import { Download, File, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  backendPath,
  type AgentRunActivityFilters,
  type AgentRunArtifactsV2Response,
  type AgentRunReportEventFilters,
  type AgentRunReportEventsV2Response,
} from "@/lib/api";

import { reportTone, type MaterialsView, type ReportViewModel } from "./reportViewModel";

const materialTabs: Array<{ value: MaterialsView; label: string }> = [
  { value: "files", label: "Файлы" },
  { value: "tech", label: "Техжурнал" },
];

function refMatches(selected: string, id: string | number) {
  if (!selected) return false;
  const normalized = selected.includes(":") ? selected.slice(selected.indexOf(":") + 1) : selected;
  return normalized === String(id);
}

/**
 * Материалы: файлы и техжурнал. Полный текст отчёта живёт на вкладке «Отчёт».
 */
export function AgentRunMaterialsV2({
  viewModel,
  view,
  onViewChange,
  selected,
  onSelect,
  eventsResponse,
  eventsLoading,
  eventsError,
  eventFilters,
  setEventFilters,
  artifactsResponse,
  artifactsLoading,
  artifactsError,
}: {
  viewModel: ReportViewModel;
  view: MaterialsView;
  onViewChange: (view: MaterialsView) => void;
  selected: string;
  onSelect: (id: string | null) => void;
  eventsResponse?: AgentRunReportEventsV2Response;
  eventsLoading: boolean;
  eventsError: unknown;
  eventFilters: AgentRunReportEventFilters;
  setEventFilters: (patch: Partial<AgentRunReportEventFilters>) => void;
  activityFilters?: AgentRunActivityFilters;
  setActivityFilters?: (patch: Partial<AgentRunActivityFilters>) => void;
  artifactsResponse?: AgentRunArtifactsV2Response;
  artifactsLoading: boolean;
  artifactsError: unknown;
}) {
  const safeView: MaterialsView = view === "document" ? "files" : view;

  return (
    <Tabs value={safeView} onValueChange={(value) => onViewChange(value as MaterialsView)} className="space-y-4">
      <TabsList aria-label="Разделы материалов" className="grid h-auto w-full grid-cols-2 gap-1 rounded-sm border border-border bg-surface-0 p-1 sm:flex sm:w-fit">
        {materialTabs.map((item) => (
          <TabsTrigger key={item.value} value={item.value} className="min-h-10 px-3 sm:px-4">
            {item.label}
            {item.value === "files" && viewModel.counts.artifacts ? (
              <span className="ml-1.5 font-mono text-xs text-muted-foreground">{viewModel.counts.artifacts}</span>
            ) : null}
            {item.value === "tech" && viewModel.counts.events ? (
              <span className="ml-1.5 font-mono text-xs text-muted-foreground">{viewModel.counts.events}</span>
            ) : null}
          </TabsTrigger>
        ))}
      </TabsList>

      <TabsContent value="files" className="mt-0">
        <FilesPanel viewModel={viewModel} response={artifactsResponse} loading={artifactsLoading} error={artifactsError} selected={selected} />
      </TabsContent>
      <TabsContent value="tech" className="mt-0">
        <TechJournal
          response={eventsResponse}
          loading={eventsLoading}
          error={eventsError}
          filters={eventFilters}
          setFilters={setEventFilters}
          selected={selected}
          onSelect={onSelect}
          fallback={viewModel.embedded.events}
        />
      </TabsContent>
    </Tabs>
  );
}

function FilesPanel({
  viewModel,
  response,
  loading,
  error,
  selected,
}: {
  viewModel: ReportViewModel;
  response?: AgentRunArtifactsV2Response;
  loading: boolean;
  error: unknown;
  selected: string;
}) {
  const legacy = viewModel.embedded.artifacts;
  const items =
    response?.items ||
    legacy.map((item) => ({
      id: Number(item.artifact_id || 0),
      key: item.id,
      name: item.name,
      description: item.description,
      content_type: item.content_type,
      size_bytes: item.size_bytes,
      size_label: item.size_label,
      truncated: item.truncated,
      download_url: item.download_url,
    }));

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">Файлы</h2>
        {response?.download_all_url ? (
          <Button size="sm" variant="outline" className="h-8 gap-1.5" asChild>
            <a href={backendPath(response.download_all_url)} download>
              <Download className="h-3.5 w-3.5" aria-hidden />
              Скачать все
            </a>
          </Button>
        ) : null}
      </div>
      {loading ? (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Загружаем…
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mb-3 rounded-sm border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : "Файлы недоступны."}
        </p>
      ) : null}
      <ul className="divide-y divide-border overflow-hidden rounded-sm border border-border bg-card">
        {items.map((item) => (
          <li
            key={item.id || item.key}
            className={`flex items-center gap-3 px-4 py-3 ${refMatches(selected, item.id || item.key) ? "bg-primary/5" : ""}`}
          >
            <File className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-foreground">{item.name}</p>
              <p className="text-xs text-muted-foreground">{item.size_label || `${item.size_bytes} байт`}</p>
            </div>
            {item.download_url ? (
              <Button size="sm" variant="ghost" className="h-8 gap-1.5" asChild>
                <a href={backendPath(item.download_url)} download>
                  <Download className="h-3.5 w-3.5" aria-hidden />
                  Скачать
                </a>
              </Button>
            ) : null}
          </li>
        ))}
        {!items.length && !loading ? (
          <li className="px-4 py-8 text-center text-sm text-muted-foreground">Файлов нет</li>
        ) : null}
      </ul>
    </section>
  );
}

function TechJournal({
  response,
  loading,
  error,
  filters,
  setFilters,
  selected,
  onSelect,
  fallback,
}: {
  response?: AgentRunReportEventsV2Response;
  loading: boolean;
  error: unknown;
  filters: AgentRunReportEventFilters;
  setFilters: (patch: Partial<AgentRunReportEventFilters>) => void;
  selected: string;
  onSelect: (id: string | null) => void;
  fallback: ReportViewModel["embedded"]["events"];
}) {
  const items = response?.items || fallback;
  const selectedItem = selected ? items.find((item) => refMatches(selected, item.id)) : items[0];

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Сырые события модели (thinking, format error). Не для операторского вывода.</p>

      <details className="rounded-sm border border-border bg-card">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">Фильтры</summary>
        <div className="grid gap-2 border-t border-border p-3 sm:grid-cols-3">
          <input
            className="h-9 rounded-sm border border-input bg-background px-3 text-sm"
            placeholder="Поиск…"
            value={filters.q || ""}
            onChange={(event) => setFilters({ q: event.target.value || undefined })}
          />
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" className="h-4 w-4 accent-primary" checked={filters.important === true} onChange={(event) => setFilters({ important: event.target.checked ? true : undefined })} />
            Только важные
          </label>
        </div>
      </details>

      {loading ? (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Загружаем…
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="rounded-sm border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : "Техжурнал недоступен."}
        </p>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[minmax(14rem,0.9fr)_minmax(0,1.1fr)]">
        <ol data-testid="evidence-list" className="max-h-[36rem] divide-y divide-border overflow-y-auto rounded-sm border border-border bg-card">
          {items.length ? (
            items.map((item) => {
              const id = String(item.id);
              const active = selectedItem && String(selectedItem.id) === id;
              return (
                <li key={id}>
                  <button
                    type="button"
                    aria-current={active ? "true" : undefined}
                    className="w-full px-3 py-2.5 text-left hover:bg-surface-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring aria-[current=true]:bg-primary/5"
                    onClick={() => onSelect(id)}
                  >
                    <span className="line-clamp-1 text-sm font-medium text-foreground">{item.title || item.event_type}</span>
                    <span className="mt-0.5 line-clamp-1 block text-xs text-muted-foreground">{item.summary || item.message}</span>
                  </button>
                </li>
              );
            })
          ) : (
            <li className="p-4 text-sm text-muted-foreground">Событий нет</li>
          )}
        </ol>

        <article data-testid="evidence-detail" className="min-w-0 rounded-sm border border-border bg-card p-4">
          {selectedItem ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">{selectedItem.title || selectedItem.event_type}</h3>
                <span className={`rounded-sm border px-1.5 py-0.5 text-2xs ${reportTone(selectedItem.severity) === "danger" ? "border-destructive/30 text-destructive" : "border-border text-muted-foreground"}`}>
                  {selectedItem.severity}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{selectedItem.summary || selectedItem.message}</p>
              {selectedItem.payload && Object.keys(selectedItem.payload).length ? (
                <details className="mt-3 rounded-sm border border-border bg-surface-0">
                  <summary className="cursor-pointer px-3 py-2 text-xs text-muted-foreground">Payload</summary>
                  <pre className="max-h-64 overflow-auto border-t border-border p-3 font-mono text-xs whitespace-pre-wrap">{JSON.stringify(selectedItem.payload, null, 2)}</pre>
                </details>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Выберите событие</p>
          )}
        </article>
      </div>
    </div>
  );
}

/** @deprecated Use AgentRunMaterialsV2 */
export const AgentRunEvidenceV2 = AgentRunMaterialsV2;
