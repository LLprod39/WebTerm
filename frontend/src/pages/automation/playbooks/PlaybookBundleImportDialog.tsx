import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  GitBranch,
  Loader2,
  LockKeyhole,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  PLAYBOOK_BUNDLE_ACCEPT,
  type CommitPlaybookBundleMetadata,
  type CommitPlaybookBundleResponse,
  type PlaybookBundlePreview,
} from "@/api/playbook-bundles";
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

interface PlaybookBundleImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lang: string;
  initialFile?: File | null;
  onCommitted?: (result: CommitPlaybookBundleResponse) => void;
  onOpenPlaybook?: (playbookId: number) => void;
}

type SourceMode = "gitlab" | "archive";

export function PlaybookBundleImportDialog({
  open,
  onOpenChange,
  lang,
  initialFile,
  onCommitted,
  onOpenPlaybook,
}: PlaybookBundleImportDialogProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const initialFileRef = useRef<File | null>(null);
  const [mode, setMode] = useState<SourceMode>("gitlab");
  const [dragging, setDragging] = useState(false);
  const handleCommitted = async (result: CommitPlaybookBundleResponse) => {
    await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    onCommitted?.(result);
  };
  const archive = usePlaybookBundleImport({ onCommitted: handleCommitted });
  const gitlab = usePlaybookGitLabImport({ onCommitted: handleCommitted });
  const selectArchiveFile = archive.selectFile;

  useEffect(() => {
    if (!open || !initialFile || initialFileRef.current === initialFile) return;
    initialFileRef.current = initialFile;
    setMode("archive");
    void selectArchiveFile(initialFile);
  }, [initialFile, open, selectArchiveFile]);

  const close = (nextOpen: boolean) => {
    if (!nextOpen) {
      archive.reset();
      gitlab.reset();
      initialFileRef.current = null;
      setDragging(false);
      setMode("gitlab");
    }
    onOpenChange(nextOpen);
  };
  const active = mode === "gitlab" ? gitlab : archive;
  const preview = active.preview;
  const metadata = active.metadata;
  const result = active.result;
  const error = active.error;
  const busy = active.busy;
  const progress = active.progress;

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
      <DialogContent className="max-h-[92vh] max-w-2xl" closeLabel={tr("Закрыть", "Close")}>
        <DialogHeader>
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            <DialogTitle>{tr("Подключить Ansible-проект", "Connect Ansible project")}</DialogTitle>
          </div>
          <DialogDescription>
            {tr(
              "Возьмём snapshot из GitLab или архива, проверим его и добавим в библиотеку.",
              "Take a snapshot from GitLab or an archive, validate it, and add it to the library.",
            )}
          </DialogDescription>
          {progress > 0 ? <Progress value={progress} className="mt-3 h-1" /> : null}
        </DialogHeader>

        <DialogBody className="max-h-[68vh] space-y-4 overflow-y-auto">
          {!result ? (
            <div className="grid grid-cols-2 gap-1 rounded-sm border border-border bg-surface-0 p-1" role="tablist" aria-label={tr("Источник проекта", "Project source")}>
              <SourceTab
                active={mode === "gitlab"}
                label="GitLab"
                icon={<GitBranch className="h-4 w-4" />}
                onClick={() => setMode("gitlab")}
              />
              <SourceTab
                active={mode === "archive"}
                label={tr("Архив", "Archive")}
                icon={<Archive className="h-4 w-4" />}
                onClick={() => setMode("archive")}
              />
            </div>
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
                <Label htmlFor="gitlab-token">{tr("Access token — только для приватного проекта", "Access token — private projects only")}</Label>
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
              onMetadataChange={active.updateMetadata}
            />
          ) : null}

          {result ? (
            <div role="status" className="flex items-start gap-3 rounded-sm border border-success/30 bg-success/8 px-4 py-4">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
              <div>
                <p className="text-sm font-semibold text-foreground">{tr("Проект добавлен", "Project added")}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {result.playbook.name} · revision #{result.revision.number} · {result.bundle.file_count} {tr("файлов", "files")}
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
            <Button onClick={openImportedPlaybook}>{tr("Открыть", "Open")}</Button>
          ) : !preview && mode === "gitlab" ? (
            <Button className="gap-1.5" disabled={!gitlab.canPreview} onClick={() => void gitlab.previewProject()}>
              {gitlab.status === "previewing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              {gitlab.status === "previewing" ? tr("Проверяем…", "Checking…") : tr("Проверить проект", "Check project")}
            </Button>
          ) : preview ? (
            <Button className="gap-1.5" disabled={!active.canCommit} onClick={() => void active.commit()}>
              {active.status === "committing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              {active.status === "committing" ? tr("Добавляем…", "Adding…") : tr("Добавить в WebTerm", "Add to WebTerm")}
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
}: {
  lang: string;
  preview: PlaybookBundlePreview;
  metadata: CommitPlaybookBundleMetadata;
  sourceLabel: string;
  onMetadataChange: (patch: Partial<CommitPlaybookBundleMetadata>) => void;
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

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="project-name">{tr("Название в WebTerm", "Name in WebTerm")}</Label>
          <Input id="project-name" value={metadata.name} onChange={(event) => onMetadataChange({ name: event.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>{tr("Главный playbook", "Main playbook")}</Label>
          <Select value={metadata.entrypoint} onValueChange={(entrypoint) => onMetadataChange({ entrypoint })}>
            <SelectTrigger aria-label={tr("Главный playbook", "Main playbook")}><SelectValue placeholder={tr("Выберите YAML", "Choose YAML")} /></SelectTrigger>
            <SelectContent>
              {preview.entrypoints.map((entrypoint) => (
                <SelectItem key={entrypoint.path} value={entrypoint.path}>{entrypoint.path}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>{tr("Доступ", "Access")}</Label>
          <Select value={metadata.visibility} onValueChange={(visibility) => onMetadataChange({ visibility: visibility as CommitPlaybookBundleMetadata["visibility"] })}>
            <SelectTrigger aria-label={tr("Доступ", "Access")}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="private">{tr("Только я", "Only me")}</SelectItem>
              <SelectItem value="shared">{tr("Команда", "Team")}</SelectItem>
            </SelectContent>
          </Select>
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
