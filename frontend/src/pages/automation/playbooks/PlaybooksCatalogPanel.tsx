import { useState } from "react";
import {
  AlertTriangle,
  Archive,
  BookOpen,
  History,
  Plus,
  Search,
  Upload,
  Wand2,
} from "lucide-react";

import { isSupportedPlaybookBundleFile } from "@/api/playbook-bundles";
import type { PlaybookCategory, PlaybookRun, PlaybookSummary, PlaybookTemplate } from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, relativeTime } from "@/lib/utils";
import { PlaybookCard } from "../PlaybookCard";
import { CATEGORIES, CATEGORY_META, RUN_STATUS_META } from "../constants";
import { PlaybookBundleImportDialog } from "./PlaybookBundleImportDialog";

export interface PlaybooksCatalogPanelProps {
  lang: string;
  tr: (ru: string, en: string) => string;
  playbooks: PlaybookSummary[];
  templates: PlaybookTemplate[];
  recentRuns: PlaybookRun[];
  playbooksLoading: boolean;
  playbooksError: string;
  search: string;
  setSearch: (v: string) => void;
  categoryFilter: PlaybookCategory | "all";
  setCategoryFilter: (v: PlaybookCategory | "all") => void;
  showHistory: boolean;
  setShowHistory: (updater: (v: boolean) => boolean) => void;
  ansible: { available?: boolean; method?: string; version?: string; message?: string } | undefined;
  ansibleAvailable: boolean;
  onRefreshRuns: () => void;
  onRetryPlaybooks: () => void;
  onImportClick: () => void;
  onImportFile: (file: File) => void;
  onOpenNew: () => void;
  onOpenGuided: () => void;
  onInstallTemplate: (tmpl: PlaybookTemplate) => void;
  onOpenEdit: (id: number) => void;
  onStartRun: (id: number) => void;
  onDuplicate: (id: number) => void;
  onDelete: (pb: PlaybookSummary) => void;
  onOpenRun: (run: PlaybookRun) => void;
}

export function PlaybooksCatalogPanel({
  lang,
  tr,
  playbooks,
  templates,
  recentRuns,
  playbooksLoading,
  playbooksError,
  search,
  setSearch,
  categoryFilter,
  setCategoryFilter,
  showHistory,
  setShowHistory,
  ansible,
  ansibleAvailable,
  onRefreshRuns,
  onRetryPlaybooks,
  onImportClick,
  onImportFile,
  onOpenNew,
  onOpenGuided,
  onInstallTemplate,
  onOpenEdit,
  onStartRun,
  onDuplicate,
  onDelete,
  onOpenRun,
}: PlaybooksCatalogPanelProps) {
  const [bundleImportOpen, setBundleImportOpen] = useState(false);
  const [bundleImportFile, setBundleImportFile] = useState<File | null>(null);
  const importDroppedFile = (file: File) => {
    if (isSupportedPlaybookBundleFile(file)) {
      setBundleImportFile(file);
      setBundleImportOpen(true);
      return;
    }
    onImportFile(file);
  };

  return (
    <>
      <PlaybookBundleImportDialog
        open={bundleImportOpen}
        onOpenChange={(open) => {
          setBundleImportOpen(open);
          if (!open) setBundleImportFile(null);
        }}
        lang={lang}
        initialFile={bundleImportFile}
        onOpenPlaybook={onOpenEdit}
      />

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2.5">
          <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
            Playbooks
          </h2>
          {!playbooksLoading ? (
            <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5 font-mono text-2xs text-muted-foreground">
              {playbooks.length}
            </span>
          ) : null}
          {ansible ? (
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-2xs",
                ansibleAvailable
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                  : "border-amber-500/30 bg-amber-500/10 text-amber-300",
              )}
              title={ansibleAvailable ? [ansible.method, ansible.version].filter(Boolean).join(" · ") : undefined}
            >
              <span
                aria-hidden
                className={cn("h-1.5 w-1.5 rounded-full", ansibleAvailable ? "bg-emerald-400" : "bg-amber-400")}
              />
              Ansible
              {ansibleAvailable && ansible.version ? (
                <span className="font-mono opacity-70">{ansible.version}</span>
              ) : null}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            size="sm"
            variant={showHistory ? "secondary" : "ghost"}
            className="h-8 gap-1.5 text-muted-foreground hover:text-foreground"
            onClick={() => {
              setShowHistory((v) => !v);
              onRefreshRuns();
            }}
          >
            <History className="h-3.5 w-3.5" />
            {tr("Запуски", "Runs")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-8 gap-1.5 text-muted-foreground hover:text-foreground"
            onClick={onImportClick}
          >
            <Upload className="h-3.5 w-3.5" />
            {tr("YAML", "YAML")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-8 gap-1.5 text-muted-foreground hover:text-foreground"
            onClick={() => {
              setBundleImportFile(null);
              setBundleImportOpen(true);
            }}
          >
            <Archive className="h-3.5 w-3.5" />
            {tr("Импорт проекта", "Import project")}
          </Button>
          <div aria-hidden className="mx-1 hidden h-5 w-px bg-border sm:block" />
          <Button size="sm" variant="outline" className="h-8 gap-1.5" onClick={onOpenGuided}>
            <Wand2 className="h-3.5 w-3.5" />
            {tr("Мастер", "Wizard")}
          </Button>
          <Button size="sm" className="h-8 gap-1.5 shadow-elev-1" onClick={onOpenNew}>
            <Plus className="h-3.5 w-3.5" />
            {tr("Новый playbook", "New playbook")}
          </Button>
        </div>
      </div>

      {/* Warning only when ansible is missing on the backend */}
      {!ansibleAvailable && ansible ? (
        <div className="rounded-sm border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground">
          <span className="font-medium">{tr("Ansible не найден на backend", "Ansible not found on backend")}</span>
          {ansible.message ? (
            <p className="mt-0.5 text-2xs text-muted-foreground">{ansible.message}</p>
          ) : null}
        </div>
      ) : null}

      {showHistory ? (
        <div className="overflow-hidden rounded-md border border-border bg-card">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <History className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
              {tr("Недавние запуски", "Recent runs")}
            </span>
          </div>
          <div className="max-h-56 divide-y divide-border/70 overflow-y-auto">
            {recentRuns.length === 0 ? (
              <p className="px-3 py-5 text-center text-xs text-muted-foreground">
                {tr("Запусков пока не было", "No runs yet")}
              </p>
            ) : (
              recentRuns.slice(0, 15).map((run) => {
                const meta = RUN_STATUS_META[run.status];
                return (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => onOpenRun(run)}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left text-xs transition-colors hover:bg-secondary/40"
                  >
                    <span
                      aria-hidden
                      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", meta?.dot || "bg-muted-foreground/60")}
                    />
                    <span className="min-w-0 flex-1 truncate font-medium text-foreground">
                      {run.playbook_name}
                    </span>
                    <span className={cn("shrink-0", meta?.className || "text-muted-foreground")}>
                      {meta ? (lang === "ru" ? meta.labelRu : meta.labelEn) : run.status}
                    </span>
                    <span className="shrink-0 font-mono text-muted-foreground/60">
                      {run.started_at ? relativeTime(run.started_at) : `#${run.id}`}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      ) : null}

      {/* Search + category filters */}
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
        <div className="relative w-full min-w-0 lg:max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={tr("Поиск playbook…", "Search playbooks…")}
            className="h-8 bg-card pl-8 text-sm"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <button
            type="button"
            onClick={() => setCategoryFilter("all")}
            className={cn(
              "h-7 rounded-full border px-2.5 text-xs font-medium transition-colors",
              categoryFilter === "all"
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-border bg-card text-muted-foreground hover:border-border hover:text-foreground",
            )}
          >
            {tr("Все", "All")}
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategoryFilter(c)}
              className={cn(
                "h-7 rounded-full border px-2.5 text-xs font-medium transition-colors",
                categoryFilter === c
                  ? CATEGORY_META[c].kicker
                  : "border-border bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              {lang === "ru" ? CATEGORY_META[c].labelRu : CATEGORY_META[c].labelEn}
            </button>
          ))}
        </div>
      </div>

      {/* Templates — quick start */}
      {templates.length > 0 ? (
        <div className="rounded-md border border-border/70 bg-surface-0/40 px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-2xs font-medium uppercase tracking-wider text-muted-foreground">
              {tr("Быстрый старт", "Quick start")}
            </span>
            {templates.map((tmpl) => (
              <button
                key={tmpl.slug}
                type="button"
                onClick={() => void onInstallTemplate(tmpl)}
                className="inline-flex h-7 items-center gap-1 rounded-full border border-border bg-card px-2.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                title={tmpl.description}
              >
                <Plus className="h-3 w-3 opacity-60" />
                {tmpl.name}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* Drop zone + list */}
      {playbooksError ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-6 py-8 text-center" role="alert">
          <AlertTriangle className="mx-auto h-7 w-7 text-destructive" />
          <p className="mt-3 text-sm font-semibold text-foreground">
            {tr("Не удалось загрузить playbooks", "Failed to load playbooks")}
          </p>
          <p className="mx-auto mt-1 max-w-xl text-xs text-muted-foreground">{playbooksError}</p>
          <Button size="sm" variant="outline" className="mt-4" onClick={onRetryPlaybooks}>
            {tr("Повторить", "Retry")}
          </Button>
        </div>
      ) : playbooksLoading ? (
        <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-md border border-border/60 bg-card/60" />
          ))}
        </div>
      ) : playbooks.length === 0 ? (
        <div
          className="rounded-md border border-dashed border-border bg-card/40 px-6 py-14 text-center"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) importDroppedFile(file);
          }}
        >
          {search.trim() || categoryFilter !== "all" ? (
            <>
              <Search className="mx-auto mb-3 h-8 w-8 text-muted-foreground/35" />
              <p className="font-display text-sm font-semibold text-foreground">
                {tr("Ничего не найдено", "Nothing found")}
              </p>
              <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
                {tr("Попробуйте изменить запрос или сбросить фильтры", "Try a different query or reset the filters")}
              </p>
              <Button
                size="sm"
                variant="outline"
                className="mt-4 h-8"
                onClick={() => {
                  setSearch("");
                  setCategoryFilter("all");
                }}
              >
                {tr("Сбросить фильтры", "Reset filters")}
              </Button>
            </>
          ) : (
            <>
              <BookOpen className="mx-auto mb-3 h-8 w-8 text-muted-foreground/35" />
              <p className="font-display text-sm font-semibold text-foreground">
                {tr("Пока нет ни одного playbook", "No playbooks yet")}
              </p>
              <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
                {tr(
                  "Соберите первый через мастер, начните с шаблона или перетащите сюда готовый .yml",
                  "Build your first one with the wizard, start from a template, or drop a .yml file here",
                )}
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <Button size="sm" className="h-8 gap-1" onClick={onOpenGuided}>
                  <Wand2 className="h-3.5 w-3.5" />
                  {tr("Мастер", "Wizard")}
                </Button>
                <Button size="sm" variant="outline" className="h-8 gap-1" onClick={onOpenNew}>
                  <Plus className="h-3.5 w-3.5" />
                  {tr("Создать", "Create")}
                </Button>
                <Button size="sm" variant="outline" className="h-8 gap-1" onClick={onImportClick}>
                  <Upload className="h-3.5 w-3.5" />
                  {tr("Импорт YAML", "Import YAML")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 gap-1"
                  onClick={() => {
                    setBundleImportFile(null);
                    setBundleImportOpen(true);
                  }}
                >
                  <Archive className="h-3.5 w-3.5" />
                  {tr("Импорт проекта", "Import project")}
                </Button>
              </div>
            </>
          )}
        </div>
      ) : (
        <div
          className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) importDroppedFile(file);
          }}
        >
          {playbooks.map((pb) => (
            <PlaybookCard
              key={pb.id}
              playbook={pb}
              lang={lang}
              onOpen={() => void onOpenEdit(pb.id)}
              onRun={() => void onStartRun(pb.id)}
              onDuplicate={() => void onDuplicate(pb.id)}
              onDelete={() => onDelete(pb)}
            />
          ))}
        </div>
      )}
    </>
  );
}
