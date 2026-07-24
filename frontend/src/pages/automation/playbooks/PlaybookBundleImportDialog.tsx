import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  FileArchive,
  FileText,
  Loader2,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  PLAYBOOK_BUNDLE_ACCEPT,
  type CommitPlaybookBundleResponse,
  type PlaybookBundleSecurityWarning,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { CATEGORIES, CATEGORY_META } from "../constants";
import { usePlaybookBundleImport } from "./usePlaybookBundleImport";

interface PlaybookBundleImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lang: string;
  initialFile?: File | null;
  onCommitted?: (result: CommitPlaybookBundleResponse) => void;
  onOpenPlaybook?: (playbookId: number) => void;
}

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
  const [dragging, setDragging] = useState(false);
  const [tagsText, setTagsText] = useState("");
  const importer = usePlaybookBundleImport({
    onCommitted: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
      onCommitted?.(result);
    },
  });
  const startPreview = importer.selectFile;

  useEffect(() => {
    if (!open || !initialFile || initialFileRef.current === initialFile) return;
    initialFileRef.current = initialFile;
    void startPreview(initialFile);
  }, [initialFile, open, startPreview]);

  useEffect(() => {
    if (importer.preview) setTagsText((importer.preview.manifest.tags || []).join(", "));
  }, [importer.preview]);

  const setOpen = (nextOpen: boolean) => {
    if (!nextOpen) {
      importer.reset();
      initialFileRef.current = null;
      setDragging(false);
      setTagsText("");
    }
    onOpenChange(nextOpen);
  };

  const selectFile = (file: File) => {
    initialFileRef.current = file;
    void startPreview(file);
  };

  const dropFile = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) selectFile(file);
  };

  const preview = importer.preview;
  const selectedEntrypoint = preview?.entrypoints.find(
    (entrypoint) => entrypoint.path === importer.metadata.entrypoint,
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[92vh] max-w-4xl" closeLabel={tr("Закрыть", "Close")}>
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Archive className="h-4 w-4 text-primary" />
            <DialogTitle>{tr("Импорт проекта Ansible", "Import Ansible project")}</DialogTitle>
          </div>
          <DialogDescription>
            {tr(
              "Сначала проверим структуру и безопасность архива. Содержимое файлов в preview не отображается.",
              "The archive is checked for structure and security first. File contents are never shown in preview.",
            )}
          </DialogDescription>
          <Progress value={importer.progress} className="mt-3 h-1" />
        </DialogHeader>

        <DialogBody className="max-h-[68vh] space-y-4 overflow-y-auto">
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
              "flex min-h-28 items-center justify-center rounded-sm border border-dashed px-5 py-5 transition-colors",
              dragging ? "border-primary bg-primary/5" : "border-border bg-surface-0",
            )}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={dropFile}
          >
            <div className="flex flex-col items-center gap-2 text-center sm:flex-row sm:text-left">
              {importer.status === "previewing" ? (
                <Loader2 className="h-7 w-7 shrink-0 animate-spin text-primary" />
              ) : (
                <FileArchive className="h-7 w-7 shrink-0 text-muted-foreground" />
              )}
              <div>
                <p className="max-w-lg truncate text-sm font-medium text-foreground">
                  {importer.file?.name || tr("Перетащите архив проекта", "Drop a project archive")}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {importer.file
                    ? `${formatBytes(importer.file.size)} · .zip / .tar / .tar.gz`
                    : tr("Поддерживаются .zip, .tar и .tar.gz", ".zip, .tar, and .tar.gz are supported")}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="sm:ml-3"
                disabled={importer.busy}
                onClick={() => fileInputRef.current?.click()}
              >
                {importer.file ? tr("Заменить", "Replace") : tr("Выбрать архив", "Choose archive")}
              </Button>
            </div>
          </div>

          {importer.error ? (
            <div role="alert" className="rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                <div>
                  <p className="text-sm font-medium text-destructive">
                    {importer.errorStage === "commit"
                      ? tr("Проект не импортирован", "Project was not imported")
                      : tr("Архив не прошёл проверку", "Archive validation failed")}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{importer.error}</p>
                </div>
              </div>
            </div>
          ) : null}

          {preview ? (
            <>
              <section aria-labelledby="bundle-preview-title" className="overflow-hidden rounded-sm border border-border">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface-2/50 px-3 py-2.5">
                  <div>
                    <h3 id="bundle-preview-title" className="text-sm font-semibold text-foreground">
                      {tr("Безопасный preview", "Safe preview")}
                    </h3>
                    <p className="mt-0.5 text-2xs text-muted-foreground">
                      {preview.archive_format.toUpperCase()} · {preview.file_count} {tr("файлов", "files")} · {formatBytes(preview.total_size_bytes)}
                    </p>
                  </div>
                  <div
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 text-xs",
                      preview.safe_to_commit
                        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                        : "border-destructive/30 bg-destructive/10 text-destructive",
                    )}
                  >
                    {preview.safe_to_commit ? <ShieldCheck className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                    {preview.safe_to_commit
                      ? tr("Можно импортировать", "Safe to import")
                      : tr("Импорт заблокирован", "Import blocked")}
                  </div>
                </div>

                <div className="grid gap-4 p-3 lg:grid-cols-[minmax(0,1fr)_minmax(17rem,0.7fr)]">
                  <div className="min-w-0 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium text-foreground">{tr("Файлы проекта", "Project files")}</p>
                      <span className="font-mono text-2xs text-muted-foreground" title={preview.content_hash}>
                        sha256:{preview.content_hash.slice(0, 10)}…
                      </span>
                    </div>
                    <div className="max-h-52 divide-y divide-border overflow-y-auto rounded-sm border border-border bg-surface-0">
                      {preview.files.map((file) => (
                        <div key={file.path} className="flex items-center gap-2 px-2.5 py-2 text-xs">
                          <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                          <span className="min-w-0 flex-1 truncate font-mono text-foreground" title={file.path}>{file.path}</span>
                          <span className="shrink-0 text-muted-foreground">{formatBytes(file.size_bytes)}</span>
                          <span className="w-10 shrink-0 text-right text-2xs text-muted-foreground">
                            {file.is_text ? tr("текст", "text") : tr("binary", "binary")}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="bundle-entrypoint">Entrypoint</Label>
                      <Select
                        value={importer.metadata.entrypoint}
                        onValueChange={(entrypoint) => importer.updateMetadata({ entrypoint })}
                      >
                        <SelectTrigger id="bundle-entrypoint">
                          <SelectValue placeholder={tr("Выберите playbook", "Choose a playbook")} />
                        </SelectTrigger>
                        <SelectContent>
                          {preview.entrypoints.map((entrypoint) => (
                            <SelectItem key={entrypoint.path} value={entrypoint.path}>
                              {entrypoint.path} · {entrypoint.task_count} {tr("задач", "tasks")}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    {selectedEntrypoint ? (
                      <div className="rounded-sm border border-border bg-surface-0 px-3 py-2 text-xs text-muted-foreground">
                        <p>{selectedEntrypoint.play_count} {tr("plays", "plays")} · {selectedEntrypoint.task_count} {tr("задач", "tasks")}</p>
                        {selectedEntrypoint.plays.slice(0, 4).map((play, index) => (
                          <p key={`${play.name}-${index}`} className="mt-1 truncate">
                            <span className="text-foreground">{play.name || `Play ${index + 1}`}</span> · hosts: {play.hosts || "—"}
                          </p>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-amber-400">
                        {tr("Выберите один entrypoint для импорта.", "Choose one entrypoint to import.")}
                      </p>
                    )}
                    {dependencySummary(preview.manifest).length ? (
                      <div className="rounded-sm border border-border bg-surface-0 px-3 py-2">
                        <p className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                          {tr("Зависимости", "Dependencies")}
                        </p>
                        {dependencySummary(preview.manifest).map((item) => (
                          <p key={item} className="mt-1 truncate font-mono text-xs text-foreground" title={item}>{item}</p>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              </section>

              {preview.secret_warnings.length ? (
                <section aria-labelledby="bundle-warnings-title" className="rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                    <div className="min-w-0">
                      <h3 id="bundle-warnings-title" className="text-sm font-semibold text-foreground">
                        {tr("Найдены потенциальные секреты или адреса", "Potential secrets or target identities found")}
                      </h3>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {tr(
                          "Значения не показываются и не отправятся в библиотеку. Удалите их из архива и повторите проверку.",
                          "Values are hidden and will not be imported. Remove them from the archive and validate again.",
                        )}
                      </p>
                      <ul className="mt-2 space-y-1">
                        {preview.secret_warnings.map((warning, index) => (
                          <li key={`${warning.path}-${warning.kind}-${index}`} className="font-mono text-xs text-destructive">
                            {warning.path} · {securityWarningLabel(warning, tr)}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </section>
              ) : null}

              <section aria-labelledby="bundle-metadata-title" className="rounded-sm border border-border p-3">
                <h3 id="bundle-metadata-title" className="text-sm font-semibold text-foreground">
                  {tr("Метаданные проекта", "Project metadata")}
                </h3>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5 sm:col-span-2">
                    <Label htmlFor="bundle-name">{tr("Название", "Name")}</Label>
                    <Input
                      id="bundle-name"
                      value={importer.metadata.name}
                      maxLength={200}
                      onChange={(event) => importer.updateMetadata({ name: event.target.value })}
                    />
                  </div>
                  <div className="space-y-1.5 sm:col-span-2">
                    <Label htmlFor="bundle-description">{tr("Описание", "Description")}</Label>
                    <Textarea
                      id="bundle-description"
                      value={importer.metadata.description}
                      rows={2}
                      maxLength={4000}
                      onChange={(event) => importer.updateMetadata({ description: event.target.value })}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>{tr("Категория", "Category")}</Label>
                    <Select
                      value={importer.metadata.category}
                      onValueChange={(category) => importer.updateMetadata({ category: category as typeof importer.metadata.category })}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {CATEGORIES.map((category) => (
                          <SelectItem key={category} value={category}>
                            {lang === "ru" ? CATEGORY_META[category].labelRu : CATEGORY_META[category].labelEn}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>{tr("Доступ", "Visibility")}</Label>
                    <Select
                      value={importer.metadata.visibility}
                      onValueChange={(visibility) => importer.updateMetadata({ visibility: visibility as typeof importer.metadata.visibility })}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="private">{tr("Только я", "Private")}</SelectItem>
                        <SelectItem value="shared">{tr("Общий workspace", "Shared workspace")}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5 sm:col-span-2">
                    <Label htmlFor="bundle-tags">{tr("Теги через запятую", "Comma-separated tags")}</Label>
                    <Input
                      id="bundle-tags"
                      value={tagsText}
                      placeholder="nginx, deploy, linux"
                      onChange={(event) => {
                        setTagsText(event.target.value);
                        importer.updateMetadata({ tags: parseTags(event.target.value) });
                      }}
                    />
                  </div>
                </div>
              </section>
            </>
          ) : null}

          {importer.result ? (
            <div role="status" className="rounded-sm border border-emerald-500/30 bg-emerald-500/10 px-3 py-3">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-400" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {tr("Проект импортирован и опубликован", "Project imported and published")}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {importer.result.playbook.name} · revision #{importer.result.revision.number} · {importer.result.bundle.file_count} {tr("файлов", "files")}
                  </p>
                </div>
              </div>
            </div>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={importer.busy}>
            {importer.result ? tr("Закрыть", "Close") : tr("Отмена", "Cancel")}
          </Button>
          {importer.errorStage === "preview" && importer.file ? (
            <Button variant="outline" onClick={() => void importer.retryPreview()} disabled={importer.busy}>
              {tr("Проверить снова", "Retry validation")}
            </Button>
          ) : null}
          {importer.result ? (
            <Button
              onClick={() => {
                const playbookId = importer.result?.playbook.id;
                setOpen(false);
                if (playbookId) onOpenPlaybook?.(playbookId);
              }}
            >
              {tr("Открыть playbook", "Open playbook")}
            </Button>
          ) : preview ? (
            <Button
              className="gap-1.5"
              disabled={!importer.canCommit}
              onClick={() => void importer.commit()}
            >
              {importer.status === "committing" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <UploadCloud className="h-4 w-4" />
              )}
              {importer.status === "committing"
                ? tr("Импорт…", "Importing…")
                : tr("Импортировать проект", "Import project")}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
  return Array.from(
    new Set(value.split(",").map((tag) => tag.trim()).filter(Boolean)),
  ).slice(0, 20);
}

function dependencySummary(manifest: {
  required_collections?: string[];
  required_roles?: string[];
}): string[] {
  return [
    ...(manifest.required_collections || []).map((item) => `collection: ${item}`),
    ...(manifest.required_roles || []).map((item) => `role: ${item}`),
  ];
}

function securityWarningLabel(
  warning: PlaybookBundleSecurityWarning,
  tr: (ru: string, en: string) => string,
): string {
  const labels: Record<string, string> = {
    credential_pattern: tr("похоже на credential", "credential-like value"),
    inventory_identity: tr("конкретный адрес inventory", "literal inventory identity"),
    private_key: tr("приватный ключ", "private key"),
    sensitive_assignment: tr("секретное присваивание", "sensitive assignment"),
    sensitive_path: tr("чувствительный файл", "sensitive file"),
    sensitive_value: tr("чувствительное значение", "sensitive value"),
  };
  return `${labels[warning.kind] || warning.kind}${warning.key ? ` (${warning.key})` : ""}`;
}
