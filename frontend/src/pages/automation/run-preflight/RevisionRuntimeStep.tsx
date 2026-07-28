import { AlertTriangle, CheckCircle2, GitCommitHorizontal, LockKeyhole } from "lucide-react";

import type { PlaybookCapabilities, PlaybookRevision } from "@/api/playbooks";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

interface RevisionRuntimeStepProps {
  lang: string;
  revisions: PlaybookRevision[];
  selectedRevisionId: number | null;
  publishedRevisionId: number | null;
  capabilities: PlaybookCapabilities;
  ansibleAvailable: boolean;
  workerReady: boolean;
  loading: boolean;
  onRevisionChange: (revisionId: number) => void;
}

export function RevisionRuntimeStep({
  lang,
  revisions,
  selectedRevisionId,
  publishedRevisionId,
  capabilities,
  ansibleAvailable,
  workerReady,
  loading,
  onRevisionChange,
}: RevisionRuntimeStepProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const selectedRevision = revisions.find((revision) => revision.id === selectedRevisionId) || null;
  const isRunbook = selectedRevision?.content_format === "runbook_json";
  const runtimeReady = isRunbook ? workerReady : ansibleAvailable && workerReady;

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <GitCommitHorizontal className="h-4 w-4 text-muted-foreground" />
        <div>
          <h3 className="text-sm font-semibold text-foreground">{tr("Версия для запуска", "Revision to run")}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">{tr("Во время запуска содержимое не изменится.", "Its content cannot change during execution.")}</p>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">{tr("Загрузка версий…", "Loading revisions…")}</p>
      ) : revisions.length ? (
        <div className="grid gap-3 md:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] md:items-end">
          {capabilities.can_edit ? (
            <div className="space-y-1.5">
              <Label htmlFor="run-revision">{tr("Версия", "Revision")}</Label>
              <Select value={selectedRevisionId ? String(selectedRevisionId) : ""} onValueChange={(value) => onRevisionChange(Number(value))}>
                <SelectTrigger id="run-revision" aria-label={tr("Версия", "Revision")}>
                  <SelectValue placeholder={tr("Выберите версию", "Choose revision")} />
                </SelectTrigger>
                <SelectContent>
                  {revisions.map((revision) => (
                    <SelectItem key={revision.id} value={String(revision.id)}>
                      #{revision.revision_number}{revision.id === publishedRevisionId ? ` · ${tr("опубликована", "published")}` : ` · ${tr("черновик", "draft")}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className="flex items-start gap-2 text-xs text-muted-foreground">
              <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{tr("Для общего playbook доступна только опубликованная версия.", "Shared playbooks can run only their published revision.")}</p>
            </div>
          )}

          {selectedRevision ? (
            <div className="min-w-0 rounded-md bg-secondary/45 px-3 py-2 text-xs">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-medium text-foreground">#{selectedRevision.revision_number}</span>
                <span className="truncate font-mono text-muted-foreground" title={selectedRevision.content_hash}>{selectedRevision.content_hash}</span>
                <span className={runtimeReady ? "inline-flex items-center gap-1 text-success" : "inline-flex items-center gap-1 text-warning"}>
                  {runtimeReady ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                  {runtimeReady ? tr("Runtime готов", "Runtime ready") : tr("Запуск недоступен", "Execution unavailable")}
                </span>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="text-sm text-destructive">{tr("Нет доступной опубликованной версии.", "No published revision is available.")}</div>
      )}
    </section>
  );
}
