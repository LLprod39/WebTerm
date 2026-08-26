import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, FileCode2, GitBranch, Loader2, RefreshCw } from "lucide-react";

import {
  commitGitLabPlaybookRefresh,
  previewGitLabPlaybookRefresh,
  type GitLabPlaybookRefreshPreviewResponse,
  type GitLabProjectSource,
} from "@/api/playbooks";
import { Badge } from "@/components/ui/badge";
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
import { notify } from "@/lib/notify";

interface PlaybookGitLabRefreshButtonProps {
  lang: string;
  playbookId: number;
  source?: GitLabProjectSource | null;
}

export function PlaybookGitLabRefreshButton({
  lang,
  playbookId,
  source,
}: PlaybookGitLabRefreshButtonProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [entrypoint, setEntrypoint] = useState("");
  const [review, setReview] = useState<GitLabPlaybookRefreshPreviewResponse | null>(null);
  const [busy, setBusy] = useState<"preview" | "commit" | null>(null);
  const [error, setError] = useState("");

  const updateReviewedInput = (next: { token?: string; entrypoint?: string }) => {
    if (typeof next.token === "string") setToken(next.token);
    if (typeof next.entrypoint === "string") setEntrypoint(next.entrypoint);
    setReview(null);
    setError("");
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      setToken("");
      setEntrypoint("");
      setReview(null);
      setBusy(null);
      setError("");
    }
  };

  const previewRefresh = async () => {
    setBusy("preview");
    setError("");
    try {
      const response = await previewGitLabPlaybookRefresh(playbookId, {
        ...(token ? { token } : {}),
        ...(entrypoint.trim() ? { entrypoint: entrypoint.trim() } : {}),
      });
      setReview(response);
      setEntrypoint(response.preview.selected_entrypoint || entrypoint);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };

  const commitRefresh = async () => {
    if (!review) return;
    setBusy("commit");
    setError("");
    try {
      const response = await commitGitLabPlaybookRefresh(playbookId, {
        ...(token ? { token } : {}),
        ...(review.preview.selected_entrypoint
          ? { entrypoint: review.preview.selected_entrypoint }
          : {}),
        expected_content_hash: review.preview.content_hash,
        expected_base_revision_id: review.refresh.base_revision_id,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["playbook-workspace", "revisions", playbookId] }),
        queryClient.invalidateQueries({ queryKey: ["playbooks"] }),
      ]);
      notify.success({
        title: tr("Версия из GitLab создана", "GitLab version created"),
        description: tr(
          `Создана версия #${response.revision.number}. Черновик и опубликованная версия не изменены.`,
          `Revision #${response.revision.number} was created. Draft and published revision were not changed.`,
        ),
      });
      handleOpenChange(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };

  const diff = review?.refresh.diff;
  const changedCount = (diff?.added.length || 0) + (diff?.changed.length || 0) + (diff?.removed.length || 0);
  const dependencies = review
    ? [
        ...(review.preview.manifest.required_collections || []).map((name) => `collection: ${name}`),
        ...(review.preview.manifest.required_roles || []).map((name) => `role: ${name}`),
      ]
    : [];

  return (
    <>
      <Button size="sm" variant="outline" className="h-8 gap-1.5" onClick={() => setOpen(true)}>
        <RefreshCw className="h-3.5 w-3.5" />
        {tr("Обновить из GitLab", "Refresh from GitLab")}
      </Button>

      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="max-w-4xl" closeLabel={tr("Закрыть", "Close")}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-primary" />
              {tr("Обновить проект из GitLab", "Refresh project from GitLab")}
            </DialogTitle>
            <DialogDescription>
              {tr(
                "Сначала проверьте снимок и изменения. Подтверждение создаст отдельную неизменяемую версию — без перезаписи черновика и публикации.",
                "Review the snapshot and changes first. Confirmation creates a separate immutable revision without overwriting the draft or publishing it.",
              )}
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="max-h-[68vh] space-y-4 overflow-y-auto">
            {source ? (
              <div className="rounded-sm border border-border bg-surface-0 px-3 py-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{source.host}/{source.project}</span>
                {source.ref ? ` · ${source.ref}` : ""}{source.path ? ` · ${source.path}` : ""}
              </div>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor={`gitlab-refresh-token-${playbookId}`}>
                  {tr("Токен — только для приватного проекта", "Token — private projects only")}
                </Label>
                <Input
                  id={`gitlab-refresh-token-${playbookId}`}
                  type="password"
                  autoComplete="off"
                  value={token}
                  placeholder="glpat-…"
                  onChange={(event) => updateReviewedInput({ token: event.target.value })}
                />
                <p className="text-2xs text-muted-foreground">
                  {tr("Токен отправляется только в этом запросе и не сохраняется.", "The token is sent only with this request and is not stored.")}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`gitlab-refresh-entrypoint-${playbookId}`}>
                  {tr("Точка входа — при необходимости", "Entrypoint — if needed")}
                </Label>
                <Input
                  id={`gitlab-refresh-entrypoint-${playbookId}`}
                  value={entrypoint}
                  placeholder="site.yml"
                  onChange={(event) => updateReviewedInput({ entrypoint: event.target.value })}
                />
                <p className="text-2xs text-muted-foreground">
                  {tr("Оставьте пустым для автоопределения структуры.", "Leave empty to detect the project structure automatically.")}
                </p>
              </div>
            </div>

            {error ? (
              <div className="rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive" role="alert">
                {error}
              </div>
            ) : null}

            {review && diff ? (
              <div className="space-y-4" aria-label={tr("Предпросмотр обновления GitLab", "GitLab refresh preview")}>
                <div className="grid gap-2 sm:grid-cols-4">
                  <DiffMetric label={tr("Добавлено", "Added")} value={diff.added.length} tone="success" />
                  <DiffMetric label={tr("Изменено", "Changed")} value={diff.changed.length} tone="warning" />
                  <DiffMetric label={tr("Удалено", "Removed")} value={diff.removed.length} tone="danger" />
                  <DiffMetric label={tr("Без изменений", "Unchanged")} value={diff.unchanged_count} />
                </div>

                {changedCount === 0 ? (
                  <div className="flex items-center gap-2 rounded-sm border border-success/30 bg-success/5 px-3 py-2 text-xs text-success">
                    <Check className="h-3.5 w-3.5" />{tr("Проект уже актуален.", "Project is already up to date.")}
                  </div>
                ) : null}
                {!review.preview.safe_to_commit ? (
                  <div className="flex items-start gap-2 rounded-sm border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    {tr("Проверка обнаружила блокирующие предупреждения. Исправьте источник и повторите предпросмотр.", "Validation found blocking warnings. Fix the source and preview it again.")}
                  </div>
                ) : null}

                <div className="grid gap-3 lg:grid-cols-2">
                  <section className="overflow-hidden rounded-sm border border-border">
                    <div className="flex items-center gap-2 border-b border-border bg-surface-0 px-3 py-2 text-xs font-medium text-foreground">
                      <FileCode2 className="h-3.5 w-3.5 text-primary" />
                      {tr("Структура снимка", "Snapshot structure")}
                      <span className="ml-auto text-muted-foreground">{review.preview.file_count}</span>
                    </div>
                    <div className="max-h-56 overflow-auto p-2">
                      {review.preview.files.map((file) => (
                        <div key={file.path} className="flex items-center gap-2 rounded-sm px-2 py-1 font-mono text-2xs text-muted-foreground">
                          <span className="min-w-0 flex-1 truncate">{file.path}</span>
                          {file.path === review.preview.selected_entrypoint ? <Badge className="shrink-0">main</Badge> : null}
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="overflow-hidden rounded-sm border border-border">
                    <div className="border-b border-border bg-surface-0 px-3 py-2 text-xs font-medium text-foreground">
                      {tr("Изменения относительно версии", "Changes from revision")} #{review.refresh.base_revision_id}
                    </div>
                    <div className="max-h-56 space-y-2 overflow-auto p-3">
                      <DiffPaths label={tr("Добавлено", "Added")} paths={diff.added} marker="+" className="text-success" />
                      <DiffPaths label={tr("Изменено", "Changed")} paths={diff.changed} marker="~" className="text-warning" />
                      <DiffPaths label={tr("Удалено", "Removed")} paths={diff.removed} marker="−" className="text-destructive" />
                      {changedCount === 0 ? <p className="text-xs text-muted-foreground">{tr("Изменений файлов нет.", "No file changes.")}</p> : null}
                    </div>
                  </section>
                </div>

                {dependencies.length ? (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-foreground">{tr("Зависимости", "Dependencies")}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {dependencies.map((dependency) => <Badge key={dependency} variant="secondary">{dependency}</Badge>)}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </DialogBody>

          <DialogFooter>
            <Button variant="ghost" onClick={() => handleOpenChange(false)} disabled={busy !== null}>
              {tr("Отмена", "Cancel")}
            </Button>
            {!review ? (
              <Button className="gap-1.5" onClick={() => void previewRefresh()} disabled={busy !== null}>
                {busy === "preview" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {busy === "preview" ? tr("Проверяем…", "Checking…") : tr("Проверить изменения", "Review changes")}
              </Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => void previewRefresh()} disabled={busy !== null}>
                  {tr("Проверить снова", "Review again")}
                </Button>
                <Button
                  className="gap-1.5"
                  disabled={busy !== null || changedCount === 0 || !review.preview.safe_to_commit}
                  onClick={() => void commitRefresh()}
                >
                  {busy === "commit" ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitBranch className="h-4 w-4" />}
                  {busy === "commit" ? tr("Создаём…", "Creating…") : tr("Создать новую версию", "Create new revision")}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DiffMetric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  const toneClass = {
    neutral: "text-foreground",
    success: "text-success",
    warning: "text-warning",
    danger: "text-destructive",
  }[tone];
  return (
    <div className="rounded-sm border border-border bg-surface-0 px-3 py-2">
      <p className="text-2xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`mt-1 font-mono text-lg font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}

function DiffPaths({
  label,
  paths,
  marker,
  className,
}: {
  label: string;
  paths: string[];
  marker: string;
  className: string;
}) {
  if (!paths.length) return null;
  return (
    <div>
      <p className={`mb-1 text-2xs font-medium uppercase tracking-wider ${className}`}>{label}</p>
      {paths.map((path) => (
        <p key={path} className="truncate font-mono text-2xs text-muted-foreground" title={path}>
          <span className={`mr-1.5 ${className}`}>{marker}</span>{path}
        </p>
      ))}
    </div>
  );
}
