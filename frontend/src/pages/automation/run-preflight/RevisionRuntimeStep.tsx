import { AlertTriangle, CheckCircle2 } from "lucide-react";

import type { PlaybookCapabilities, PlaybookRevision } from "@/api/playbooks";

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

/** Runtime readiness only — revision picking is silent under Run. */
export function RevisionRuntimeStep({
  lang,
  revisions,
  selectedRevisionId,
  ansibleAvailable,
  workerReady,
  loading,
}: RevisionRuntimeStepProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const selectedRevision = revisions.find((revision) => revision.id === selectedRevisionId) || null;
  const isRunbook = selectedRevision?.content_format === "runbook_json";
  const runtimeReady = isRunbook ? workerReady : ansibleAvailable && workerReady;

  if (loading) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        {tr("Подготовка запуска…", "Preparing run…")}
      </p>
    );
  }

  if (!revisions.length) {
    return (
      <div className="text-sm text-destructive">
        {tr("Скрипт ещё не готов к запуску.", "The script is not ready to run yet.")}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className={runtimeReady ? "inline-flex items-center gap-1 text-success" : "inline-flex items-center gap-1 text-warning"}>
        {runtimeReady ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
        {runtimeReady ? tr("Среда готова", "Runtime ready") : tr("Запуск недоступен", "Execution unavailable")}
      </span>
    </div>
  );
}
