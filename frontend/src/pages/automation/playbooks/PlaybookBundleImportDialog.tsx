import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  FileCode2,
  Files,
  GitBranch,
  Loader2,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  PLAYBOOK_BUNDLE_ACCEPT,
  type CommitPlaybookBundleMetadata,
  type CommitPlaybookBundleResponse,
  type PlaybookBundlePreview,
} from "@/api/playbook-bundles";
import type { RawPlaybookImportPreview } from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { CATEGORIES, CATEGORY_META } from "../constants";
import { usePlaybookBundleImport } from "./usePlaybookBundleImport";
import { usePlaybookGitLabImport } from "./usePlaybookGitLabImport";
import { usePlaybookYamlImport } from "./usePlaybookYamlImport";

interface PlaybookBundleImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lang: string;
  initialFile?: File | null;
  initialMode?: SourceMode;
  onCommitted?: (result: CommitPlaybookBundleResponse) => void;
  onOpenPlaybook?: (playbookId: number) => void;
}

type SourceMode = "yaml" | "archive" | "gitlab";

export function PlaybookBundleImportDialog({
  open,
  onOpenChange,
  lang,
  initialFile,
  initialMode = "yaml",
  onCommitted,
  onOpenPlaybook,
}: PlaybookBundleImportDialogProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const yamlInputRef = useRef<HTMLInputElement>(null);
  const initialFileRef = useRef<File | null>(null);
  const wasOpenRef = useRef(false);
  const [mode, setMode] = useState<SourceMode>(initialMode);
  const [dragging, setDragging] = useState(false);
  const handleCommitted = async (result: CommitPlaybookBundleResponse) => {
    await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    onCommitted?.(result);
  };
  const archive = usePlaybookBundleImport({ onCommitted: handleCommitted });
  const gitlab = usePlaybookGitLabImport({ onCommitted: handleCommitted });
  const yaml = usePlaybookYamlImport({
    onCommitted: async () => {
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    },
  });
  const selectArchiveFile = archive.selectFile;
  const active = mode === "gitlab" ? gitlab : archive;
  const preview = mode === "yaml" ? null : active.preview;
  const metadata = active.metadata;
  const result = mode === "yaml" ? yaml.result : active.result;
  const error = mode === "yaml" ? yaml.error : active.error;
  const busy = mode === "yaml" ? yaml.busy : active.busy;
  const progress = mode === "yaml" ? yaml.progress : active.progress;

  useEffect(() => {
    if (!open || !initialFile || initialFileRef.current === initialFile) return;
    initialFileRef.current = initialFile;
    setMode("archive");
    void selectArchiveFile(initialFile);
  }, [initialFile, open, selectArchiveFile]);

  useEffect(() => {
    const justOpened = open && !wasOpenRef.current;
    wasOpenRef.current = open;
    if (justOpened && !initialFile) setMode(initialMode);
  }, [initialFile, initialMode, open]);

  const close = (nextOpen: boolean) => {
    if (!nextOpen) {
      archive.reset();
      gitlab.reset();
      yaml.reset();
      initialFileRef.current = null;
      setDragging(false);
      setMode(initialMode);
    }
    onOpenChange(nextOpen);
  };

  const selectFile = (file: File) => {
    initialFileRef.current = file;
    void archive.selectFile(file);
  };
  const dropFile = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) selectFile(file);
  };
  const openImportedPlaybook = () => {
    const playbookId = result?.playbook.id;
    close(false);
    if (playbookId) onOpenPlaybook?.(playbookId);
  };
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent
        className="max-h-[92vh] max-w-2xl"
        closeLabel={tr("Закрыть", "Close")}
        onInteractOutside={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            <DialogTitle>{tr("Подключить Ansible-проект", "Connect Ansible project")}</DialogTitle>
          </div>
          <DialogDescription>
            {tr(
              "Импортируем проект, проверим его безопасность и совместимость.",
              "Import the project, then check its safety and compatibility.",
            )}
          </DialogDescription>
          {progress > 0 ? (
            <Progress
              value={progress}
              className="mt-3 h-1"
              aria-label={tr("Прогресс импорта", "Import progress")}
            />
          ) : null}
        </DialogHeader>

        <DialogBody className="max-h-[68vh] space-y-4 overflow-y-auto">
          {!result ? (
            <div className="grid grid-cols-3 gap-1 rounded-sm border border-border bg-surface-0 p-1" role="tablist" aria-label={tr("Источник проекта", "Project source")}>
              <SourceTab
                active={mode === "yaml"}
                label="YAML"
                icon={<FileCode2 className="h-4 w-4" />}
                onClick={() => setMode("yaml")}
              />
              <SourceTab
                active={mode === "archive"}
                label={tr("Архив", "Archive")}
                icon={<Archive className="h-4 w-4" />}
                onClick={() => setMode("archive")}
              />
              <SourceTab
                active={mode === "gitlab"}
                label="GitLab"
                icon={<GitBranch className="h-4 w-4" />}
                onClick={() => setMode("gitlab")}
              />
            </div>
          ) : null}

          {!yaml.preview && !result && mode === "yaml" ? (
            <section className="rounded-sm border border-border bg-card p-4">
              <input
                ref={yamlInputRef}
                type="file"
                accept=".yml,.yaml,application/x-yaml,text/yaml,text/plain"
                className="hidden"
                aria-label={tr("Выбрать Ansible YAML", "Choose Ansible YAML")}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void yaml.selectFile(file);
                  event.target.value = "";
                }}
              />
              <div className="flex min-h-40 flex-col items-center justify-center rounded-sm border border-dashed border-border bg-surface-0 px-5 py-6 text-center">
                {yaml.busy ? <Loader2 className="h-7 w-7 animate-spin text-primary" /> : <FileCode2 className="h-7 w-7 text-muted-foreground" />}
                <p className="mt-3 text-sm font-medium text-foreground">{tr("Загрузите готовый playbook YAML", "Load an existing playbook YAML")}</p>
                <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
                  {tr("Перед добавлением WebTerm проверит структуру, секреты и совместимость, затем попросит подтверждение.", "WebTerm checks structure, secrets, and compatibility before asking you to confirm the import.")}
                </p>
                <Button type="button" size="sm" variant="outline" className="mt-3" disabled={busy} onClick={() => yamlInputRef.current?.click()}>
                  {tr("Выбрать YAML", "Choose YAML")}
                </Button>
              </div>
            </section>
          ) : null}

          {!preview && !result && mode === "gitlab" ? (
            <section className="space-y-4 rounded-sm border border-border bg-card p-4">
              <div className="space-y-1.5">
                <Label htmlFor="gitlab-project-url">{tr("Ссылка на проект GitLab", "GitLab project URL")}</Label>
                <Input
                  id="gitlab-project-url"
                  autoFocus
                  value={gitlab.source.project_url}
                  placeholder="https://gitlab.com/group/ansible-project"
                  onChange={(event) => gitlab.updateSource({ project_url: event.target.value })}
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="gitlab-ref">{tr("Ветка или тег", "Branch or tag")}</Label>
                  <Input
                    id="gitlab-ref"
                    value={gitlab.source.ref}
                    placeholder={tr("По умолчанию", "Default branch")}
                    onChange={(event) => gitlab.updateSource({ ref: event.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="gitlab-path">{tr("Папка с Ansible", "Ansible directory")}</Label>
                  <Input
                    id="gitlab-path"
                    value={gitlab.source.path}
                    placeholder="ansible"
                    onChange={(event) => gitlab.updateSource({ path: event.target.value })}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="gitlab-token">{tr("Токен доступа — только для приватного проекта", "Access token — private projects only")}</Label>
                <Input
                  id="gitlab-token"
                  type="password"
                  autoComplete="off"
                  value={gitlab.source.token}
                  placeholder="glpat-…"
                  onChange={(event) => gitlab.updateSource({ token: event.target.value })}
                />
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <LockKeyhole className="h-3.5 w-3.5" />
                  {tr("Токен используется один раз и не сохраняется.", "The token is used once and never stored.")}
                </p>
                <p className="text-xs leading-5 text-muted-foreground">
                  {tr(
                    "Подключение работает через GitLab API. Обычный Git, GitHub и SSH-репозитории пока не поддерживаются.",
                    "Connection uses the GitLab API. Generic Git, GitHub, and SSH repositories are not supported yet.",
                  )}
                </p>
              </div>
            </section>
          ) : null}

          {!preview && !result && mode === "archive" ? (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept={PLAYBOOK_BUNDLE_ACCEPT}
                className="hidden"
                aria-label={tr("Выбрать архив проекта", "Choose project archive")}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) selectFile(file);
                  event.target.value = "";
                }}
              />
              <div
                className={cn(
                  "flex min-h-40 flex-col items-center justify-center rounded-sm border border-dashed px-5 py-6 text-center transition-colors",
                  dragging ? "border-primary bg-primary/5" : "border-border bg-surface-0",
                )}
                onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setDragging(false)}
                onDrop={dropFile}
              >
                {archive.status === "previewing" ? (
                  <Loader2 className="h-7 w-7 animate-spin text-primary" />
                ) : (
                  <UploadCloud className="h-7 w-7 text-muted-foreground" />
                )}
                <p className="mt-3 text-sm font-medium text-foreground">
                  {archive.file?.name || tr("Перетащите ZIP/TAR сюда", "Drop a ZIP/TAR here")}
                </p>
                <Button type="button" size="sm" variant="outline" className="mt-3" disabled={busy} onClick={() => fileInputRef.current?.click()}>
                  {tr("Выбрать файл", "Choose file")}
                </Button>
              </div>
            </>
          ) : null}

          {error ? (
            <div role="alert" className="flex items-start gap-2 rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2.5">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <div>
                <p className="text-sm font-medium text-destructive">{tr("Не удалось проверить проект", "Project validation failed")}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{error}</p>
              </div>
            </div>
          ) : null}

          {preview && !result ? (
            <ProjectReview
              lang={lang}
              preview={preview}
              metadata={metadata}
              sourceLabel={mode === "gitlab" && gitlab.resolvedSource
                ? `${gitlab.resolvedSource.host}/${gitlab.resolvedSource.project}`
                : archive.file?.name || tr("Архив проекта", "Project archive")}
              busy={active.busy}
              allowProjectPath={mode === "archive"}
              onMetadataChange={(patch) => {
                if (mode === "archive" && Object.prototype.hasOwnProperty.call(patch, "project_path") && patch.project_path !== active.metadata.project_path) {
                  void archive.selectProjectPath(patch.project_path || "");
                } else if (patch.entrypoint && patch.entrypoint !== active.metadata.entrypoint) {
                  void active.selectEntrypoint(patch.entrypoint);
                } else {
                  active.updateMetadata(patch);
                }
              }}
            />
          ) : null}

          {yaml.preview && !result && mode === "yaml" ? (
            <YamlProjectReview lang={lang} preview={yaml.preview} filename={yaml.file?.name || "playbook.yml"} />
          ) : null}

          {result ? (
            <div role="status" className="flex items-start gap-3 rounded-sm border border-success/30 bg-success/8 px-4 py-4">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
              <div>
                <p className="text-sm font-semibold text-foreground">{tr("Проект добавлен", "Project added")}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {tr("Откройте проект: WebTerm проверит совместимость и предложит минимальную адаптацию перед запуском.", "Open the project to check compatibility and prepare a minimal adaptation before running.")}
                </p>
              </div>
            </div>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)} disabled={busy}>
            {result ? tr("Закрыть", "Close") : tr("Отмена", "Cancel")}
          </Button>
          {result ? (
            <Button className="gap-1.5" onClick={openImportedPlaybook}><Sparkles className="h-4 w-4" />{tr("Открыть проект", "Open project")}</Button>
          ) : !preview && mode === "gitlab" ? (
            <Button className="gap-1.5" disabled={!gitlab.canPreview} onClick={() => void gitlab.previewProject()}>
              {gitlab.status === "previewing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              {gitlab.status === "previewing" ? tr("Проверяем…", "Checking…") : tr("Проверить проект", "Check project")}
            </Button>
          ) : mode === "yaml" && yaml.preview ? (
            <Button className="gap-1.5" disabled={!yaml.canCommit} onClick={() => void yaml.commit()}>
              {yaml.status === "committing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              {yaml.status === "committing" ? tr("Добавляем…", "Adding…") : tr("Добавить приватный проект", "Add private project")}
            </Button>
          ) : preview ? (
            <Button className="gap-1.5" disabled={!active.canCommit} onClick={() => void active.commit()}>
              {active.status === "committing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              {active.status === "committing" ? tr("Добавляем…", "Adding…") : tr("Добавить приватный проект", "Add private project")}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SourceTab({ active, label, icon, onClick }: { active: boolean; label: string; icon: React.ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "flex h-9 items-center justify-center gap-2 rounded-sm text-sm font-medium transition-colors",
        active ? "bg-card text-foreground shadow-elev-1" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {icon}{label}
    </button>
  );
}

function ProjectReview({
  lang,
  preview,
  metadata,
  sourceLabel,
  onMetadataChange,
  busy,
  allowProjectPath,
}: {
  lang: string;
  preview: PlaybookBundlePreview;
  metadata: CommitPlaybookBundleMetadata;
  sourceLabel: string;
  onMetadataChange: (patch: Partial<CommitPlaybookBundleMetadata>) => void;
  busy: boolean;
  allowProjectPath: boolean;
}) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  return (
    <section className="space-y-4 rounded-sm border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{sourceLabel}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {preview.file_count} {tr("файлов", "files")} · {formatBytes(preview.total_size_bytes)}
          </p>
        </div>
        <span className={cn(
          "inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 text-xs font-medium",
          preview.safe_to_commit ? "border-success/30 bg-success/10 text-success" : "border-destructive/30 bg-destructive/10 text-destructive",
        )}>
          {preview.safe_to_commit ? <ShieldCheck className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          {preview.safe_to_commit ? tr("Проверка пройдена", "Checks passed") : tr("Нужно исправить", "Needs attention")}
        </span>
      </div>

      {preview.secret_warnings.length ? (
        <div className="rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {tr("Найдены потенциальные секреты. Удалите их из проекта и проверьте снова.", "Potential secrets were found. Remove them and check again.")}
        </div>
      ) : null}
      {preview.controller_warnings?.length ? (
        <div className="rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {tr("Найдены опасные операции на контроллере. Импорт заблокирован до исправления.", "Unsafe controller-side operations were found. Import is blocked until they are fixed.")}
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-2">
        <details open className="rounded-sm border border-border bg-surface-0/50">
          <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-xs font-medium text-foreground">
            <Files className="h-3.5 w-3.5 text-primary" />
            {tr("Структура проекта", "Project structure")} · {preview.files.length}
          </summary>
           <div className="max-h-44 overflow-auto border-t border-border py-1">
            {preview.files.slice(0, 80).map((file) => (
              <div key={file.path} className="flex items-center justify-between gap-3 px-3 py-1.5 text-xs">
                <span className="min-w-0 truncate font-mono text-foreground">{file.path}</span>
                <span className="shrink-0 text-muted-foreground">{formatBytes(file.size_bytes)}</span>
              </div>
            ))}
            {preview.ignored_files?.length ? (
              <details className="mx-2 mt-1 border-t border-border/70 pt-1">
                <summary className="cursor-pointer px-1.5 py-1 text-2xs text-muted-foreground">{tr("Игнорируемые служебные файлы", "Ignored service files")} · {preview.ignored_files.length}</summary>
                {preview.ignored_files.slice(0, 40).map((path) => <p key={path} className="truncate px-1.5 py-0.5 font-mono text-2xs text-muted-foreground">{path}</p>)}
              </details>
            ) : null}
          </div>
        </details>
        <div className="rounded-sm border border-border bg-surface-0/50 p-3">
          <p className="text-xs font-medium text-foreground">{tr("Зависимости", "Dependencies")}</p>
          <div className="mt-2 space-y-2">
            <DependencyRow label={tr("Коллекции", "Collections")} values={preview.dependencies?.collections || preview.manifest.required_collections || []} emptyLabel={tr("Не найдены", "None detected")} />
            <DependencyRow label={tr("Роли", "Roles")} values={preview.dependencies?.roles || preview.manifest.required_roles || []} emptyLabel={tr("Не найдены", "None detected")} />
            <p className="border-t border-border/70 pt-2 text-2xs text-muted-foreground">
              {tr("Совместимость", "Compatibility")}: {preview.compatibility?.ready === false
                ? tr(`${preview.compatibility.issues?.length || 0} замечаний`, `${preview.compatibility.issues?.length || 0} issues`)
                : tr("готово к проверке", "ready for validation")}
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="project-name">{tr("Название в WebTerm", "Name in WebTerm")}</Label>
          <Input id="project-name" value={metadata.name} onChange={(event) => onMetadataChange({ name: event.target.value })} />
        </div>
        {allowProjectPath ? (
          <div className="space-y-1.5">
            <Label>{tr("Корень Ansible-проекта", "Ansible project root")}</Label>
            <Select
              value={metadata.project_path || "__archive_root__"}
              onValueChange={(value) => onMetadataChange({ project_path: value === "__archive_root__" ? "" : value })}
              disabled={busy}
            >
              <SelectTrigger aria-label={tr("Корень Ansible-проекта", "Ansible project root")}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__archive_root__">.</SelectItem>
                {projectRootCandidates(preview).map((path) => <SelectItem key={path} value={path}>{path}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-2xs text-muted-foreground">{tr("Смена корня повторно проверяет тот же архив.", "Changing the root rechecks the same archive.")}</p>
          </div>
        ) : null}
        <div className="space-y-1.5">
          <Label>{tr("Основной YAML", "Main YAML file")}</Label>
          <Select value={metadata.entrypoint} onValueChange={(entrypoint) => onMetadataChange({ entrypoint })} disabled={busy}>
            <SelectTrigger aria-label={tr("Основной YAML", "Main YAML file")}><SelectValue placeholder={tr("Выберите YAML", "Choose YAML")} /></SelectTrigger>
            <SelectContent>
              {preview.entrypoints.map((entrypoint) => (
                <SelectItem key={entrypoint.path} value={entrypoint.path}>{entrypoint.path}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="rounded-sm border border-border bg-surface-0 px-3 py-2">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Доступ", "Access")}</p>
          <p className="mt-1 flex items-center gap-1.5 text-xs font-medium text-foreground">
            <LockKeyhole className="h-3.5 w-3.5 text-primary" />{tr("Приватный проект", "Private project")}
          </p>
          <p className="mt-1 text-2xs text-muted-foreground">
            {tr("Поделиться можно после импорта на вкладке «Доступ».", "Share it after import from the Access tab.")}
          </p>
        </div>
      </div>

      <details className="group rounded-sm border border-border bg-surface-0/50">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">
          {tr("Дополнительные настройки", "More settings")}
        </summary>
        <div className="grid gap-3 border-t border-border p-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="project-description">{tr("Описание", "Description")}</Label>
            <Textarea id="project-description" rows={2} value={metadata.description} onChange={(event) => onMetadataChange({ description: event.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label>{tr("Категория", "Category")}</Label>
            <Select value={metadata.category} onValueChange={(category) => onMetadataChange({ category: category as CommitPlaybookBundleMetadata["category"] })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((category) => <SelectItem key={category} value={category}>{lang === "ru" ? CATEGORY_META[category].labelRu : CATEGORY_META[category].labelEn}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-tags">{tr("Теги", "Tags")}</Label>
            <Input id="project-tags" value={metadata.tags.join(", ")} onChange={(event) => onMetadataChange({ tags: parseTags(event.target.value) })} placeholder="nginx, production" />
          </div>
        </div>
      </details>
    </section>
  );
}

function projectRootCandidates(preview: PlaybookBundlePreview): string[] {
  const paths = new Set<string>();
  for (const entrypoint of preview.entrypoints) {
    const parts = entrypoint.path.split("/").filter(Boolean);
    for (let index = 1; index < parts.length; index += 1) {
      paths.add(parts.slice(0, index).join("/"));
    }
  }
  if (preview.project_path) paths.add(preview.project_path);
  return Array.from(paths).sort();
}

function YamlProjectReview({
  lang,
  preview,
  filename,
}: {
  lang: string;
  preview: RawPlaybookImportPreview;
  filename: string;
}) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const name = typeof preview.parsed.name === "string" ? preview.parsed.name : filename.replace(/\.ya?ml$/i, "");
  return (
    <section className="space-y-4 rounded-sm border border-border bg-card p-4" aria-label={tr("Предпросмотр YAML", "YAML import preview")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{name}</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{preview.entrypoint}</p>
        </div>
        <span className={cn(
          "inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 text-xs font-medium",
          preview.safe_to_commit
            ? "border-success/30 bg-success/10 text-success"
            : "border-destructive/30 bg-destructive/10 text-destructive",
        )}>
          {preview.safe_to_commit ? <ShieldCheck className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          {preview.safe_to_commit ? tr("Проверка пройдена", "Checks passed") : tr("Импорт заблокирован", "Import blocked")}
        </span>
      </div>

      {preview.secret_findings.length ? (
        <div className="rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {tr("В YAML найдены буквальные секреты. Значения скрыты; удалите их и загрузите файл повторно.", "Literal secrets were found in the YAML. Values are hidden; remove them and upload the file again.")}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-sm border border-border bg-surface-0/50 p-3">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Структура", "Structure")}</p>
          {preview.tree.files.map((file) => (
            <div key={file.path} className="mt-2 flex items-center justify-between gap-3 text-xs">
              <span className="min-w-0 truncate font-mono text-foreground">{file.path}</span>
              <span className="shrink-0 text-muted-foreground">{formatBytes(file.size_bytes)}</span>
            </div>
          ))}
        </div>
        <div className="rounded-sm border border-border bg-surface-0/50 p-3">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Зависимости", "Dependencies")}</p>
          <div className="mt-2 space-y-2">
            <DependencyRow label={tr("Коллекции", "Collections")} values={preview.dependencies.collections || []} emptyLabel={tr("Не найдены", "None detected")} />
            <DependencyRow label={tr("Роли", "Roles")} values={preview.dependencies.roles || []} emptyLabel={tr("Не найдены", "None detected")} />
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-sm border border-border bg-surface-0 px-3 py-2">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Синтаксис", "Syntax")}</p>
          <p className="mt-1 text-xs font-medium text-success">{tr("Корректный YAML", "Valid YAML")}</p>
        </div>
        <div className="rounded-sm border border-border bg-surface-0 px-3 py-2">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Секреты", "Secrets")}</p>
          <p className={cn("mt-1 text-xs font-medium", preview.secret_findings.length ? "text-destructive" : "text-success")}>
            {preview.secret_findings.length ? tr("Импорт заблокирован", "Import blocked") : tr("Не найдены", "None found")}
          </p>
        </div>
        <div className="rounded-sm border border-border bg-surface-0 px-3 py-2">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Совместимость", "Compatibility")}</p>
          <p className="mt-1 text-xs font-medium text-foreground">
            {preview.compatibility.ready ? tr("Готов к запуску", "Ready to run") : tr("Потребуется проверка или адаптация", "Validation or adaptation required")}
          </p>
        </div>
        <div className="rounded-sm border border-border bg-surface-0 px-3 py-2">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Доступ", "Access")}</p>
          <p className="mt-1 flex items-center gap-1.5 text-xs font-medium text-foreground"><LockKeyhole className="h-3.5 w-3.5 text-primary" />{tr("Приватный проект", "Private project")}</p>
        </div>
      </div>

      <p className="text-2xs text-muted-foreground">
        {tr("Подтверждение привязано к проверенному SHA-256 снимку. Если содержимое изменится, импорт будет отклонён.", "Confirmation is locked to the reviewed SHA-256 snapshot. Changed content is rejected.")}
      </p>
    </section>
  );
}

function DependencyRow({ label, values, emptyLabel }: { label: string; values: string[]; emptyLabel: string }) {
  return (
    <div>
      <p className="text-2xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {values.length ? values.map((value) => (
          <span key={value} className="rounded-sm border border-border bg-card px-2 py-1 font-mono text-2xs text-foreground">{value}</span>
        )) : <span className="text-xs text-muted-foreground">{emptyLabel}</span>}
      </div>
    </div>
  );
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const amount = value / 1024 ** index;
  return `${amount >= 10 || index === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`;
}

function parseTags(value: string): string[] {
  return Array.from(new Set(value.split(",").map((tag) => tag.trim()).filter(Boolean))).slice(0, 20);
}
