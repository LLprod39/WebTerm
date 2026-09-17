import { useState } from "react";
import { AlertTriangle, Download, Loader2 } from "lucide-react";

import {
  downloadPlaybookBundleExport,
  exportPlaybookRevisionBundle,
} from "@/api/playbook-bundles";
import { Button } from "@/components/ui/button";
import { notify } from "@/lib/notify";

interface PlaybookBundleExportButtonProps {
  playbookId: number;
  revisionId: number;
  revisionNumber: number;
  canExport: boolean;
  lang: string;
}

export function PlaybookBundleExportButton({
  playbookId,
  revisionId,
  revisionNumber,
  canExport,
  lang,
}: PlaybookBundleExportButtonProps) {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);

  if (!canExport) return null;

  const exportBundle = async () => {
    setExporting(true);
    setError("");
    try {
      const artifact = await exportPlaybookRevisionBundle(playbookId, revisionId);
      downloadPlaybookBundleExport(artifact);
      notify.success({
        title: tr("Архив скачан", "Bundle downloaded"),
        description: artifact.redactionCount
          ? tr(
              `Удалено чувствительных значений: ${artifact.redactionCount}`,
              `Sensitive values redacted: ${artifact.redactionCount}`,
            )
          : tr("Экспорт не содержит секретных значений", "The export contains no secret values"),
      });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message);
      notify.error({ title: tr("Экспорт не удался", "Export failed"), description: message });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <Button
        size="sm"
        variant="outline"
        className="h-8 gap-1"
        disabled={exporting}
        aria-label={tr(
          `Экспортировать неизменяемую ревизию ${revisionNumber}`,
          `Export immutable revision ${revisionNumber}`,
        )}
        onClick={() => void exportBundle()}
      >
        {exporting ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : error ? (
          <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
        ) : (
          <Download className="h-3.5 w-3.5" />
        )}
        {exporting ? tr("Экспорт…", "Exporting…") : tr("Экспорт ZIP", "Export ZIP")}
      </Button>
      {error ? (
        <span role="alert" className="max-w-40 truncate text-2xs text-destructive" title={error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}
