import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Download, File, Loader2, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { backendPath, type AgentRunActivityFilters, type AgentRunActivityV2Item, type AgentRunActivityV2Response, type AgentRunArtifactsV2Response, type AgentRunReportEventFilters, type AgentRunReportEventsV2Response } from "@/lib/api";

import { AgentRunFullDocument } from "./AgentRunFullDocument";
import { reportTone, type EvidenceView, type ReportViewModel } from "./reportViewModel";

const evidenceTabs: Array<{ value: EvidenceView; label: string }> = [
  { value: "events", label: "События" },
  { value: "activity", label: "Активность" },
  { value: "outputs", label: "Выводы" },
  { value: "artifacts", label: "Файлы" },
  { value: "document", label: "Полный отчёт" },
];
const severityLabels: Record<string, string> = { success: "Норма", info: "Информация", warning: "Предупреждение", high: "Высокая", critical: "Критично", fatal: "Критично" };
const activityStatusLabels: Record<string, string> = { succeeded: "Выполнено", success: "Выполнено", completed: "Завершено", failed: "Ошибка", error: "Ошибка", running: "Выполняется", pending: "Ожидает", unknown: "Неизвестно" };

function refMatches(selected: string, id: string | number) {
  if (!selected) return false;
  const normalized = selected.includes(":") ? selected.slice(selected.indexOf(":") + 1) : selected;
  return normalized === String(id);
}

function activityTitle(item: AgentRunActivityV2Item) {
  if (item.title && !/^[a-z0-9_.:/-]+$/.test(item.title.trim())) return item.title;
  if (item.kind === "tool") return `Работа инструмента ${item.ordinal}`;
  if (item.kind === "command") return `Команда ${item.ordinal}`;
  if (item.kind === "iteration") return `Итерация ${item.ordinal}`;
  return `Шаг ${item.ordinal}`;
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value));
}

function EventEvidence({
  viewModel,
  response,
  loading,
  error,
  filters,
  setFilters,
  selected,
  onSelect,
}: {
  viewModel: ReportViewModel;
  response?: AgentRunReportEventsV2Response;
  loading: boolean;
  error: unknown;
  filters: AgentRunReportEventFilters;
  setFilters: (patch: Partial<AgentRunReportEventFilters>) => void;
  selected: string;
  onSelect: (id: string | null) => void;
}) {
  const items = response?.items || viewModel.embedded.events;
  const selectedItem = selected ? items.find((item) => refMatches(selected, item.id)) : items[0];
  const categories = Array.from(new Set(items.map((item) => item.category).filter(Boolean)));
  const phases = Array.from(new Set(items.map((item) => item.phase).filter(Boolean)));
  return (
    <div className="space-y-3">
      <div aria-label="Фильтры событий" className="grid gap-2 rounded-sm border border-border bg-card p-3 sm:grid-cols-2 lg:grid-cols-[minmax(14rem,1fr)_9rem_9rem_9rem_auto]">
        <label className="relative block">
          <span className="sr-only">Поиск по событиям</span>
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
          <Input className="pl-9" value={filters.q || ""} placeholder="Событие, фаза или сообщение" onChange={(event) => setFilters({ q: event.target.value || undefined })} />
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">
          Важность
          <select className="h-9 rounded-sm border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={filters.severity?.[0] || ""} onChange={(event) => setFilters({ severity: event.target.value ? [event.target.value] : undefined })}>
            <option value="">Все</option><option value="critical">Критично</option><option value="high">Высокая</option><option value="warning">Предупреждение</option><option value="info">Информация</option><option value="success">Норма</option>
          </select>
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">
          Фаза
          <select className="h-9 rounded-sm border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={filters.phase?.[0] || ""} onChange={(event) => setFilters({ phase: event.target.value ? [event.target.value] : undefined })}>
            <option value="">Все</option>{(phases.length ? phases : ["planning", "executing", "synthesizing", "delivery"]).map((phase) => <option key={phase} value={phase}>{phase === "planning" ? "Планирование" : phase === "executing" ? "Выполнение" : phase === "synthesizing" ? "Отчёт" : phase === "delivery" ? "Доставка" : phase.replace(/[_-]+/g, " ")}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">
          Категория
          <select className="h-9 rounded-sm border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={filters.category?.[0] || ""} onChange={(event) => setFilters({ category: event.target.value ? [event.target.value] : undefined })}>
            <option value="">Все</option>{categories.map((category) => <option key={category} value={category}>{category.replace(/[_-]+/g, " ")}</option>)}
          </select>
        </label>
        <label className="flex min-h-9 items-center gap-2 self-end rounded-sm border border-border px-3 text-sm text-foreground">
          <input type="checkbox" className="h-4 w-4 accent-primary" checked={filters.important === true} onChange={(event) => setFilters({ important: event.target.checked ? true : undefined })} />
          Только важные
        </label>
      </div>

      {loading ? <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />Загружаем события…</p> : null}
      {error ? <p role="alert" className="rounded-sm border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error instanceof Error ? error.message : "События недоступны."}</p> : null}

      <div className="grid gap-3 lg:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.2fr)]">
        <ol data-testid="evidence-list" className="max-h-[38rem] space-y-2 overflow-y-auto rounded-sm border border-border bg-surface-0 p-2" aria-label="Список событий">
          {items.length ? items.map((item) => {
            const id = String(item.id);
            return (
              <li key={id}>
                <button type="button" aria-current={selectedItem && String(selectedItem.id) === id ? "true" : undefined} className="w-full rounded-sm border border-transparent p-3 text-left hover:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-[current=true]:border-primary/40 aria-[current=true]:bg-primary/5" onClick={() => onSelect(id)}>
                  <span className="flex items-start justify-between gap-2"><span className="font-medium text-foreground">{item.title || item.event_type}</span><span className="font-mono text-xs text-muted-foreground">#{item.sequence_no}</span></span>
                  <span className="mt-1 line-clamp-2 block text-xs leading-5 text-muted-foreground">{item.summary || item.message}</span>
                </button>
              </li>
            );
          }) : <li className="p-4 text-sm text-muted-foreground">События не найдены.</li>}
        </ol>
        <article data-testid="evidence-detail" className="min-w-0 rounded-sm border border-border bg-card p-4 shadow-elev-1" aria-live="polite">
          {selectedItem ? (
            <>
              <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold text-foreground">{selectedItem.title || selectedItem.event_type}</h3><span className={`rounded-sm border px-2 py-1 text-xs ${reportTone(selectedItem.severity) === "danger" ? "border-destructive/30 text-destructive" : "border-border text-muted-foreground"}`}>{severityLabels[selectedItem.severity] || "Информация"}</span></div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{selectedItem.summary || selectedItem.message}</p>
              <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2"><div><dt className="text-muted-foreground">Фаза</dt><dd className="mt-1 font-medium text-foreground">{selectedItem.phase || "—"}</dd></div><div><dt className="text-muted-foreground">Источник</dt><dd className="mt-1 font-medium text-foreground">{selectedItem.source || "—"}</dd></div><div><dt className="text-muted-foreground">Категория</dt><dd className="mt-1 font-medium text-foreground">{selectedItem.category || "—"}</dd></div><div><dt className="text-muted-foreground">Время</dt><dd className="mt-1 font-medium text-foreground">{formatDate(selectedItem.created_at)}</dd></div></dl>
              {selectedItem.payload && Object.keys(selectedItem.payload).length ? <details className="mt-4 rounded-sm border border-border bg-surface-0"><summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">Безопасный payload</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words border-t border-border p-3 font-mono text-xs">{JSON.stringify(selectedItem.payload, null, 2)}</pre></details> : null}
            </>
          ) : selected ? <div className="space-y-3"><p className="text-sm text-muted-foreground">Запись по ссылке не загружена на текущей странице.</p>{response?.page.has_more && response.page.next_cursor ? <Button type="button" size="sm" variant="outline" onClick={() => setFilters({ cursor: response.page.next_cursor, direction: "older" })}>Загрузить более ранние записи</Button> : <p className="text-xs text-muted-foreground">В доступных страницах запись не найдена.</p>}</div> : <p className="text-sm text-muted-foreground">Выберите событие.</p>}
        </article>
      </div>

      {response?.page ? <nav aria-label="Страницы событий" className="flex items-center justify-between rounded-sm border border-border bg-surface-0 p-2"><Button size="sm" variant="ghost" disabled={!response.page.prev_cursor} onClick={() => setFilters({ cursor: response.page.prev_cursor, direction: "newer" })}><ChevronLeft className="mr-1 h-4 w-4" aria-hidden />Новее</Button><span className="text-xs text-muted-foreground">{items.length} из {response.total}</span><Button size="sm" variant="ghost" disabled={!response.page.has_more || !response.page.next_cursor} onClick={() => setFilters({ cursor: response.page.next_cursor, direction: "older" })}>Старше<ChevronRight className="ml-1 h-4 w-4" aria-hidden /></Button></nav> : null}
    </div>
  );
}

function ActivityEvidence({ viewModel, response, selected, onSelect, outputsOnly, loading, error, setFilters }: { viewModel: ReportViewModel; response?: AgentRunActivityV2Response; selected: string; onSelect: (id: string | null) => void; outputsOnly: boolean; loading: boolean; error: unknown; setFilters: (patch: Partial<AgentRunActivityFilters>) => void }) {
  const allItems = response?.items || viewModel.embedded.activity;
  const items = outputsOnly ? allItems.filter((item) => item.command || item.error || item.summary) : allItems;
  const selectedItem = selected ? items.find((item) => refMatches(selected, item.id)) : items[0];
  return (
    <div className="space-y-3">
      {loading ? <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />Загружаем активность…</p> : null}
      {error ? <p role="alert" className="rounded-sm border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error instanceof Error ? error.message : "Активность недоступна."}</p> : null}
      <div className="grid gap-3 lg:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.2fr)]">
        <ol data-testid="evidence-list" className="max-h-[38rem] space-y-2 overflow-y-auto rounded-sm border border-border bg-surface-0 p-2" aria-label={outputsOnly ? "Список выводов" : "Список активности"}>
          {items.length ? items.map((item) => <li key={item.id}><button type="button" aria-current={selectedItem && String(selectedItem.id) === String(item.id) ? "true" : undefined} className="w-full rounded-sm border border-transparent p-3 text-left hover:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-[current=true]:border-primary/40 aria-[current=true]:bg-primary/5" onClick={() => onSelect(String(item.id))}><span className="font-medium text-foreground">{activityTitle(item)}</span><span className="mt-1 line-clamp-2 block text-xs leading-5 text-muted-foreground">{item.summary && !/^[a-z0-9_.:/-]+$/.test(item.summary.trim()) ? item.summary : activityStatusLabels[item.status] || "Техническая операция"}</span></button></li>) : <li className="p-4 text-sm text-muted-foreground">Записей нет.</li>}
        </ol>
        <article data-testid="evidence-detail" className="min-w-0 rounded-sm border border-border bg-card p-4 shadow-elev-1" aria-live="polite">
          {selectedItem ? <ActivityDetail item={selectedItem} /> : selected ? <div className="space-y-3"><p className="text-sm text-muted-foreground">Запись по ссылке не загружена на текущей странице.</p>{response?.page.has_more && response.page.next_cursor ? <Button type="button" size="sm" variant="outline" onClick={() => setFilters({ cursor: response.page.next_cursor, direction: "older" })}>Загрузить более ранние записи</Button> : <Button type="button" size="sm" variant="outline" onClick={() => onSelect(null)}>Показать текущую страницу</Button>}</div> : <p className="text-sm text-muted-foreground">Выберите запись.</p>}
        </article>
      </div>
    </div>
  );
}

function ActivityDetail({ item }: { item: AgentRunActivityV2Item }) {
  return <><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold text-foreground">{activityTitle(item)}</h3><span className="rounded-sm border border-border px-2 py-1 text-xs text-muted-foreground">{activityStatusLabels[item.status] || "Неизвестно"}</span></div>{item.summary && !/^[a-z0-9_.:/-]+$/.test(item.summary.trim()) ? <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.summary}</p> : null}<details className="mt-4 rounded-sm border border-border bg-surface-0"><summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">Технические детали</summary><div className="border-t border-border p-3"><dl className="grid gap-3 text-xs sm:grid-cols-2"><div><dt className="text-muted-foreground">Инструмент</dt><dd className="mt-1 font-medium text-foreground">{item.tool || "—"}</dd></div><div><dt className="text-muted-foreground">Сервер</dt><dd className="mt-1 font-medium text-foreground">{item.server || "—"}</dd></div><div><dt className="text-muted-foreground">Код выхода</dt><dd className="mt-1 font-medium text-foreground">{item.exit_code ?? "—"}</dd></div><div><dt className="text-muted-foreground">Длительность</dt><dd className="mt-1 font-medium text-foreground">{item.duration_ms ? `${item.duration_ms} мс` : "—"}</dd></div></dl>{item.command ? <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-sm border border-border bg-background p-3 font-mono text-xs">{item.command}</pre> : null}{item.error ? <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-sm border border-destructive/30 bg-destructive/5 p-3 font-mono text-xs">{item.error}</pre> : null}</div></details></>;
}

function ArtifactEvidence({ viewModel, response, loading, error, selected }: { viewModel: ReportViewModel; response?: AgentRunArtifactsV2Response; loading: boolean; error: unknown; selected: string }) {
  const legacy = viewModel.embedded.artifacts;
  const refs = viewModel.evidenceLinks.filter((item) => item.view === "artifacts");
  const items = response?.items || legacy.map((item) => ({ id: Number(item.artifact_id || 0), key: item.id, name: item.name, type: item.type, description: item.description, content_type: item.content_type, size_bytes: item.size_bytes, size_label: item.size_label, checksum_sha256: item.checksum_sha256 || "", truncated: item.truncated, created_at: item.created_at, updated_at: item.created_at, download_url: item.download_url }));
  return <section aria-labelledby="artifacts-heading"><div className="mb-3 flex flex-wrap items-center justify-between gap-3"><h2 id="artifacts-heading" className="font-display text-base font-semibold text-foreground">Файлы и артефакты</h2>{response?.download_all_url ? <Button size="sm" variant="outline" className="gap-1.5" asChild><a href={backendPath(response.download_all_url)} download><Download className="h-4 w-4" aria-hidden />Скачать все</a></Button> : null}</div>{loading ? <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />Загружаем метаданные файлов…</p> : null}{error ? <p role="alert" className="mb-3 rounded-sm border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error instanceof Error ? error.message : "Метаданные файлов недоступны."}</p> : null}<div data-testid="evidence-list" className="grid gap-3 sm:grid-cols-2">{items.map((item) => <article key={item.id || item.key} data-testid={refMatches(selected, item.id || item.key) ? "evidence-detail" : undefined} className={`rounded-sm border bg-card p-4 shadow-elev-1 ${refMatches(selected, item.id || item.key) ? "border-primary/50 ring-1 ring-primary/20" : "border-border"}`}><div className="flex items-start gap-3"><File className="h-5 w-5 text-muted-foreground" aria-hidden /><div className="min-w-0"><h3 className="break-words font-medium text-foreground">{item.name}</h3><p className="mt-1 text-xs text-muted-foreground">{item.size_label || `${item.size_bytes} байт`} · {item.content_type || "тип не указан"}</p></div></div>{item.description ? <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.description}</p> : null}{item.truncated ? <p role="status" className="mt-2 rounded-sm border border-warning/35 bg-warning/10 p-2 text-xs text-foreground">Файл сохранён в усечённом виде; скачивание не восстановит отброшенную часть.</p> : null}{item.download_url ? <Button size="sm" variant="outline" className="mt-3 gap-1.5" asChild><a href={backendPath(item.download_url)} download><Download className="h-4 w-4" aria-hidden />Скачать{item.truncated ? " усечённый файл" : ""}</a></Button> : null}</article>)}{!items.length && !loading ? refs.map((item) => <article key={item.id} className="rounded-sm border border-border bg-card p-4 shadow-elev-1"><h3 className="font-medium text-foreground">{item.label}</h3><Button size="sm" variant="outline" className="mt-3" asChild><Link to={item.href}>Открыть доказательство</Link></Button></article>) : null}{!items.length && !refs.length && !loading ? <div className="col-span-full rounded-sm border border-dashed border-border p-6 text-sm text-muted-foreground">Файлы не приложены.</div> : null}</div></section>;
}

export function AgentRunEvidenceV2({
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
  activityResponse,
  activityLoading,
  activityError,
  activityFilters: _activityFilters,
  setActivityFilters,
  artifactsResponse,
  artifactsLoading,
  artifactsError,
  documentText,
  documentLoading,
  documentError,
}: {
  viewModel: ReportViewModel;
  view: EvidenceView;
  onViewChange: (view: EvidenceView) => void;
  selected: string;
  onSelect: (id: string | null) => void;
  eventsResponse?: AgentRunReportEventsV2Response;
  eventsLoading: boolean;
  eventsError: unknown;
  eventFilters: AgentRunReportEventFilters;
  setEventFilters: (patch: Partial<AgentRunReportEventFilters>) => void;
  activityResponse?: AgentRunActivityV2Response;
  activityLoading: boolean;
  activityError: unknown;
  activityFilters: AgentRunActivityFilters;
  setActivityFilters: (patch: Partial<AgentRunActivityFilters>) => void;
  artifactsResponse?: AgentRunArtifactsV2Response;
  artifactsLoading: boolean;
  artifactsError: unknown;
  documentText?: string;
  documentLoading: boolean;
  documentError: unknown;
}) {
  return (
    <Tabs value={view} onValueChange={(value) => onViewChange(value as EvidenceView)} className="space-y-4">
      <TabsList aria-label="Виды доказательств" className="grid h-auto w-full grid-cols-2 gap-1 rounded-sm border border-border bg-surface-0 p-1 sm:flex sm:flex-wrap sm:justify-start">
        {evidenceTabs.map((item) => (
          <TabsTrigger key={item.value} value={item.value} className="min-h-10 min-w-0 px-2 sm:px-3">
            {item.label}
            {item.value === "events" ? ` ${viewModel.counts.events}` : item.value === "activity" ? ` ${viewModel.counts.activities}` : item.value === "artifacts" ? ` ${viewModel.counts.artifacts}` : ""}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="events" className="mt-0">
        <EventEvidence viewModel={viewModel} response={eventsResponse} loading={eventsLoading} error={eventsError} filters={eventFilters} setFilters={setEventFilters} selected={selected} onSelect={onSelect} />
      </TabsContent>
      <TabsContent value="activity" className="mt-0">
        <ActivityEvidence viewModel={viewModel} response={activityResponse} selected={selected} onSelect={onSelect} outputsOnly={false} loading={activityLoading} error={activityError} setFilters={setActivityFilters} />
      </TabsContent>
      <TabsContent value="outputs" className="mt-0">
        <ActivityEvidence viewModel={viewModel} response={activityResponse} selected={selected} onSelect={onSelect} outputsOnly loading={activityLoading} error={activityError} setFilters={setActivityFilters} />
      </TabsContent>
      <TabsContent value="artifacts" className="mt-0">
        <ArtifactEvidence viewModel={viewModel} response={artifactsResponse} loading={artifactsLoading} error={artifactsError} selected={selected} />
      </TabsContent>
      <TabsContent value="document" className="mt-0">
        <div data-testid="full-report-document">
          <AgentRunFullDocument document={viewModel.document} fullText={documentText} loading={documentLoading} error={documentError} runId={viewModel.run.id} />
        </div>
      </TabsContent>
    </Tabs>
  );
}
