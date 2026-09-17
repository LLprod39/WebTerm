import { Link } from "react-router-dom";
import { RotateCcw, Settings2 } from "lucide-react";

import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";

import { AgentRunFullDocument } from "./AgentRunFullDocument";
import type { PreparedReportMutation } from "./useAgentRunReportController";
import type { ReportViewModel } from "./reportViewModel";

/**
 * Report tab = the written report. No summary cards, metrics grids, or
 * findings/actions panels — those duplicated the markdown and buried reading.
 */
export function AgentRunResultV2({
  viewModel,
  prepare,
  documentText,
  documentLoading,
  documentError,
}: {
  viewModel: ReportViewModel;
  prepare: (kind: PreparedReportMutation) => void;
  documentText?: string;
  documentLoading?: boolean;
  documentError?: unknown;
}) {
  return (
    <div className="space-y-4" data-testid="report-result-minimal">
      <DeliveryLine viewModel={viewModel} prepare={prepare} />

      {viewModel.document.available ? (
        <div data-testid="full-report-document">
          <AgentRunFullDocument
            document={viewModel.document}
            fullText={documentText}
            loading={Boolean(documentLoading)}
            error={documentError}
            runId={viewModel.run.id}
          />
        </div>
      ) : (
        <EmptyReport viewModel={viewModel} />
      )}
    </div>
  );
}

function EmptyReport({ viewModel }: { viewModel: ReportViewModel }) {
  const fallback = viewModel.document.preview?.trim();
  if (fallback) {
    return (
      <div data-testid="full-report-document">
        <AgentRunFullDocument
          document={{ ...viewModel.document, available: true }}
          fullText={fallback}
          loading={false}
          error={undefined}
          runId={viewModel.run.id}
        />
      </div>
    );
  }
  return (
    <div className="rounded-sm border border-dashed border-border px-5 py-10 text-center">
      <p className="text-sm font-medium text-foreground">Отчёт ещё готовится</p>
      <p className="mt-1 text-sm text-muted-foreground">
        Когда агент закончит, здесь появится полный текст.
      </p>
    </div>
  );
}

/** Compact delivery row — only when delivery is enabled or needs action. */
function DeliveryLine({
  viewModel,
  prepare,
}: {
  viewModel: ReportViewModel;
  prepare: (kind: PreparedReportMutation) => void;
}) {
  const d = viewModel.delivery;
  if (!d.enabled) return null;
  if (!d.canRetry && !d.blockedReason && d.tone === "success") return null;

  return (
    <div className="flex flex-col gap-2 rounded-sm border border-border bg-surface-0 px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="text-muted-foreground">Доставка</span>
        <StatusBadge label={d.label || d.status || "—"} tone={d.tone} />
        {d.summary || d.blockedReason ? (
          <span className="truncate text-muted-foreground">{d.summary || d.blockedReason}</span>
        ) : null}
      </div>
      {d.canRetry ? (
        <Button type="button" size="sm" variant="outline" className="h-8 shrink-0 gap-1.5" onClick={() => prepare("retry-delivery")}>
          <RotateCcw className="h-3.5 w-3.5" aria-hidden />
          Повторить
        </Button>
      ) : d.blockedReason ? (
        <Button size="sm" variant="ghost" className="h-8 shrink-0 gap-1.5" asChild>
          <Link to={d.setupUrl || "/settings/notifications"}>
            <Settings2 className="h-3.5 w-3.5" aria-hidden />
            Настроить
          </Link>
        </Button>
      ) : null}
    </div>
  );
}
