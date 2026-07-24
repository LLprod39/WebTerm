import { AlertTriangle, GitCommitHorizontal, LockKeyhole, ShieldCheck } from "lucide-react";

import type { PlaybookCapabilities, PlaybookRevision } from "@/api/playbooks";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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
  const runtimeReady = isRunbook ? workerReady : ansibleAvailable;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <section className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
        <div className="flex items-center gap-2">
          <GitCommitHorizontal className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            {tr("Неизменяемая ревизия", "Immutable revision")}
          </h3>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {tr(
            "Проверка и запуск будут привязаны к одному content hash.",
            "Validation and execution will use the same content hash.",
          )}
        </p>

        {loading ? (
          <p className="mt-4 text-sm text-muted-foreground" role="status">
            {tr("Загрузка ревизий…", "Loading revisions…")}
          </p>
        ) : revisions.length ? (
          <div className="mt-4 space-y-3">
            {capabilities.can_edit ? (
              <div className="space-y-1.5">
                <Label htmlFor="run-revision">{tr("Ревизия", "Revision")}</Label>
                <Select
                  value={selectedRevisionId ? String(selectedRevisionId) : ""}
                  onValueChange={(value) => onRevisionChange(Number(value))}
                >
                  <SelectTrigger id="run-revision" aria-label={tr("Ревизия", "Revision")}>
                    <SelectValue placeholder={tr("Выберите ревизию", "Choose revision")} />
                  </SelectTrigger>
                  <SelectContent>
                    {revisions.map((revision) => (
                      <SelectItem key={revision.id} value={String(revision.id)}>
                        #{revision.revision_number}
                        {revision.id === publishedRevisionId
                          ? ` · ${tr("опубликована", "published")}`
                          : ` · ${tr("не опубликована", "unpublished")}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div className="flex items-start gap-2 rounded-sm border border-border bg-surface-0 px-3 py-2.5">
                <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">
                  {tr(
                    "Для общего playbook доступен запуск только опубликованной ревизии.",
                    "Shared playbooks can run only their published revision.",
                  )}
                </p>
              </div>
            )}

            {selectedRevision ? (
              <dl className="grid gap-2 rounded-sm border border-border bg-surface-0 p-3 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">Revision</dt>
                  <dd className="mt-0.5 font-mono text-foreground">#{selectedRevision.revision_number}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Origin</dt>
                  <dd className="mt-0.5 text-foreground">{selectedRevision.origin_type}</dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-muted-foreground">Content hash</dt>
                  <dd className="mt-0.5 truncate font-mono text-foreground" title={selectedRevision.content_hash}>
                    {selectedRevision.content_hash || "—"}
                  </dd>
                </div>
                {selectedRevision.bundle_hash ? (
                  <div className="sm:col-span-2">
                    <dt className="text-muted-foreground">Bundle hash</dt>
                    <dd className="mt-0.5 truncate font-mono text-foreground" title={selectedRevision.bundle_hash}>
                      {selectedRevision.bundle_hash}
                    </dd>
                  </div>
                ) : null}
              </dl>
            ) : null}
          </div>
        ) : (
          <div className="mt-4 rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {tr("Нет доступной опубликованной ревизии.", "No published revision is available.")}
          </div>
        )}
      </section>

      <aside className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
        <div className="flex items-center gap-2">
          {runtimeReady ? (
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-amber-400" />
          )}
          <h3 className="text-sm font-semibold text-foreground">Runtime</h3>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
          {isRunbook
            ? workerReady
              ? tr(
                  "Worker готов к выполнению JSON-runbook.",
                  "The worker is ready to execute this JSON runbook.",
                )
              : tr(
                  "Worker недоступен. Запуск JSON-runbook невозможен.",
                  "The worker is unavailable. This JSON runbook cannot be executed.",
                )
            : ansibleAvailable
              ? tr(
                  "Ansible runtime доступен. Точная версия и зависимости будут проверены на шаге Review.",
                  "Ansible runtime is available. Its exact version and dependencies are checked during Review.",
                )
              : tr(
                  "Ansible runtime недоступен. Validation покажет blocker, запуск невозможен.",
                  "Ansible runtime is unavailable. Validation will report a blocker and execution is disabled.",
                )}
        </p>
      </aside>
    </div>
  );
}
