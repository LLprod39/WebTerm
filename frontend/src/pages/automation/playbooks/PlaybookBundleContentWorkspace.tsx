import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { File, FileCode2, FolderTree, Loader2, Save } from "lucide-react";

import {
  getPlaybookDraftFile,
  getPlaybookDraftFiles,
  updatePlaybookDraftFile,
} from "@/api/playbooks";
import { CodeEditor } from "@/components/editor/CodeEditor";
import { Button } from "@/components/ui/button";
import { notify } from "@/lib/notify";
import { cn } from "@/lib/utils";

interface PlaybookBundleContentWorkspaceProps {
  lang: string;
  playbookId: number;
  readOnly?: boolean;
  entrypointEditor: ReactNode;
  onCompatibilityTargetChange?: (target: {
    path: string;
    content: string;
    isEntrypoint: boolean;
    editable: boolean;
  } | null) => void;
}

const treeKey = (playbookId: number) => ["playbook-workspace", "files", playbookId] as const;

export function PlaybookBundleContentWorkspace({
  lang,
  playbookId,
  readOnly = false,
  entrypointEditor,
  onCompatibilityTargetChange,
}: PlaybookBundleContentWorkspaceProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const queryClient = useQueryClient();
  const treeQuery = useQuery({
    queryKey: treeKey(playbookId),
    queryFn: () => getPlaybookDraftFiles(playbookId),
    retry: false,
  });
  const tree = treeQuery.data?.tree;
  const [selectedPath, setSelectedPath] = useState("");
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [viewMode, setViewMode] = useState<"working" | "original" | "changes">("working");

  useEffect(() => {
    if (!tree) return;
    setSelectedPath((current) => current && tree.files.some((file) => file.path === current)
      ? current
      : tree.entrypoint || tree.files[0]?.path || "");
  }, [tree]);

  const selected = useMemo(
    () => tree?.files.find((file) => file.path === selectedPath) || null,
    [selectedPath, tree],
  );
  const entrypointSelected = Boolean(tree && selectedPath === tree.entrypoint);
  const currentView = readOnly ? "published" : "current";
  const fileQuery = useQuery({
    queryKey: ["playbook-workspace", "file", playbookId, selectedPath, currentView],
    queryFn: () => getPlaybookDraftFile(playbookId, selectedPath, currentView),
    enabled: Boolean(selectedPath && !entrypointSelected && selected?.is_text),
    retry: false,
  });
  const originalQuery = useQuery({
    queryKey: ["playbook-workspace", "file", playbookId, selectedPath, "base"],
    queryFn: () => getPlaybookDraftFile(playbookId, selectedPath, "base"),
    enabled: Boolean(!readOnly && selectedPath && !entrypointSelected && selected?.is_text),
    retry: false,
  });

  useEffect(() => {
    const next = fileQuery.data?.file.content;
    if (typeof next !== "string") return;
    setContent(next);
    setSavedContent(next);
  }, [fileQuery.data?.file.content, selectedPath]);

  useEffect(() => {
    setViewMode("working");
  }, [selectedPath]);

  useEffect(() => {
    if (!selected) {
      onCompatibilityTargetChange?.(null);
      return;
    }
    onCompatibilityTargetChange?.({
      path: selected.path,
      content: entrypointSelected ? "" : content,
      isEntrypoint: entrypointSelected,
      editable: Boolean(selected.editable && selected.is_text && /\.ya?ml$/i.test(selected.path)),
    });
  }, [content, entrypointSelected, onCompatibilityTargetChange, selected]);

  if (treeQuery.isPending) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 rounded-sm border border-border bg-card px-3 py-2 text-xs text-muted-foreground" role="status">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />{tr("Загрузка структуры проекта…", "Loading project structure…")}
        </div>
        {entrypointEditor}
      </div>
    );
  }

  // Old single-file playbooks and temporarily unavailable bundle APIs keep the
  // proven YAML editor instead of turning a recoverable API miss into a blocker.
  if (!tree || treeQuery.isError) return <>{entrypointEditor}</>;

  const saveFile = async () => {
    if (!selected || !selected.editable || tree.draft_version == null || content === savedContent) return;
    setSaving(true);
    try {
      const response = await updatePlaybookDraftFile(playbookId, {
        path: selected.path,
        content,
        expected_draft_version: tree.draft_version,
        expected_bundle_hash: tree.bundle_hash,
      });
      setSavedContent(response.file.content);
      queryClient.setQueryData(treeKey(playbookId), { success: true, tree: response.tree });
      await queryClient.invalidateQueries({ queryKey: ["playbook-workspace", "draft", playbookId] });
      notify.success({ title: tr("Файл сохранён", "File saved") });
    } catch (caught) {
      notify.error({ title: tr("Не удалось сохранить файл", "Failed to save file"), description: String(caught) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-elev-1" aria-label={tr("Файлы проекта", "Project files")}>
      <div className="grid min-h-[34rem] lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside className="border-b border-border bg-surface-0/45 lg:border-b-0 lg:border-r">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2.5 text-xs font-medium text-foreground">
            <FolderTree className="h-3.5 w-3.5 text-primary" />
            {tr("Файлы", "Files")}
            <span className="ml-auto text-muted-foreground">{tree.files.length}</span>
          </div>
          <div className="max-h-[40rem] overflow-auto p-1.5">
            {tree.files.map((file) => {
              const active = file.path === selectedPath;
              return (
                <button
                  key={file.path}
                  type="button"
                  title={file.path}
                  onClick={() => setSelectedPath(file.path)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-xs",
                    active ? "bg-primary/10 text-foreground" : "text-muted-foreground hover:bg-secondary/45 hover:text-foreground",
                  )}
                >
                  {/\.ya?ml$/i.test(file.path) ? <FileCode2 className="h-3.5 w-3.5 shrink-0" /> : <File className="h-3.5 w-3.5 shrink-0" />}
                  <span className="min-w-0 flex-1 truncate font-mono">{file.path}</span>
                  {file.path === tree.entrypoint ? <span className="text-2xs text-primary">main</span> : null}
                </button>
              );
            })}
          </div>
        </aside>
        <div className="min-w-0">
          {entrypointSelected ? entrypointEditor : (
            <div className="flex h-full min-h-0 flex-col">
              <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate font-mono text-xs font-medium text-foreground">{selectedPath}</p>
                  <p className="mt-0.5 text-2xs text-muted-foreground">
                    {selected?.editable ? tr("Текстовый файл", "Text file") : tr("Только чтение", "Read only")}
                  </p>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {selected?.is_text && !readOnly ? (
                    <div className="flex rounded-sm border border-border bg-surface-0 p-0.5" role="tablist" aria-label={tr("Режим файла", "File view") }>
                      <FileModeTab active={viewMode === "working"} onClick={() => setViewMode("working")}>{tr("Рабочая копия", "Working copy")}</FileModeTab>
                      <FileModeTab active={viewMode === "original"} onClick={() => setViewMode("original")}>{tr("Оригинал", "Original")}</FileModeTab>
                      <FileModeTab active={viewMode === "changes"} onClick={() => setViewMode("changes")}>{tr("Изменения", "Changes")}</FileModeTab>
                    </div>
                  ) : null}
                  {viewMode === "working" ? (
                    <Button size="sm" variant="outline" className="h-8 gap-1.5" disabled={readOnly || tree.draft_version == null || !selected?.editable || content === savedContent || saving} onClick={() => void saveFile()}>
                      {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                      {saving ? tr("Сохранение…", "Saving…") : tr("Сохранить файл", "Save file")}
                    </Button>
                  ) : null}
                </div>
              </div>
              {selected?.is_text && fileQuery.isPending ? (
                <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 className="h-4 w-4 animate-spin" />{tr("Загрузка файла…", "Loading file…")}</div>
              ) : selected?.is_text && fileQuery.isError ? (
                <div className="m-4 rounded-sm border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">{tr("Не удалось открыть файл.", "Could not open the file.")}</div>
              ) : selected?.is_text && viewMode !== "working" && originalQuery.isPending ? (
                <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 className="h-4 w-4 animate-spin" />{tr("Загрузка оригинала…", "Loading original…")}</div>
              ) : selected?.is_text && viewMode !== "working" && originalQuery.isError ? (
                <div className="m-4 rounded-sm border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">{tr("Не удалось открыть неизменяемый оригинал.", "Could not open the immutable original.")}</div>
              ) : selected?.is_text && viewMode === "working" ? (
                <CodeEditor
                  content={content}
                  filename={selected.path}
                  readOnly={readOnly || !selected.editable}
                  onChange={setContent}
                  onSave={() => void saveFile()}
                  ariaLabel={tr(`Редактор ${selected.path}`, `${selected.path} editor`)}
                  className="min-h-[32rem]"
                />
              ) : selected?.is_text && viewMode === "changes" ? (
                <SessionDiff before={originalQuery.data?.file.content || ""} after={content} lang={lang} />
              ) : selected?.is_text && viewMode === "original" ? (
                <CodeEditor
                  content={originalQuery.data?.file.content || ""}
                  filename={selected.path}
                  readOnly
                  onChange={() => undefined}
                  ariaLabel={tr(`Оригинал ${selected.path}`, `${selected.path} original`)}
                  className="min-h-[32rem]"
                />
              ) : (
                <div className="m-4 rounded-sm border border-border bg-surface-0 p-3 text-xs text-muted-foreground">{tr("Бинарный файл доступен только в экспортируемом архиве.", "Binary files are available only in the exported bundle.")}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function FileModeTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn("rounded-sm px-2 py-1 text-2xs font-medium", active ? "bg-card text-foreground shadow-elev-1" : "text-muted-foreground hover:text-foreground")}
    >
      {children}
    </button>
  );
}

function SessionDiff({ before, after, lang }: { before: string; after: string; lang: string }) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  if (before === after) {
    return <div className="m-4 rounded-sm border border-border bg-surface-0 p-4 text-xs text-muted-foreground">{tr("Рабочая копия совпадает с неизменяемым оригиналом.", "The working copy matches the immutable original.")}</div>;
  }
  return (
    <div className="min-h-[32rem] overflow-auto bg-terminal-bg p-4 font-mono text-xs leading-5" role="region" aria-label={tr("Изменения текущего файла", "Current file changes")}>
      <p className="mb-3 font-sans text-xs text-muted-foreground">{tr("Рабочая копия сравнена с неизменяемой базовой ревизией.", "Working copy compared with the immutable base revision.")}</p>
      <pre className="whitespace-pre-wrap text-destructive">{before.split("\n").map((line) => `- ${line}`).join("\n")}</pre>
      <pre className="mt-3 whitespace-pre-wrap text-success">{after.split("\n").map((line) => `+ ${line}`).join("\n")}</pre>
    </div>
  );
}
