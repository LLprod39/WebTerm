import { useMemo, useState } from "react";
import { Check, Clipboard, Download, FileArchive, FileCode2, FileText, Search, WrapText } from "lucide-react";

import type { AgentRunReportArtifact, AgentRunReportLog, AgentRunReportResponse } from "@/lib/api";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { formatDuration } from "./formatters";
import { copyText, downloadArtifact, downloadArtifactBundle, LOG_PAGE_SIZE } from "./reportShared";


export function LogsTab({ report, logs }: { report: AgentRunReportResponse; logs: AgentRunReportLog[] }) {
  const [query, setQuery] = useState("");
  const [wrap, setWrap] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(LOG_PAGE_SIZE);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return logs;
    return logs.filter((log) => `${log.title}\n${log.command}\n${log.stdout}\n${log.stderr}`.toLowerCase().includes(q));
  }, [logs, query]);
  const visible = filtered.slice(0, visibleCount);
  const hasMore = visible.length < filtered.length;

  const copyLog = async (log: AgentRunReportLog) => {
    await copyText(`$ ${log.command}\n\n${log.stdout || ""}\n${log.stderr || ""}`.trim());
    setCopied(log.id);
    window.setTimeout(() => setCopied(null), 1200);
  };

  return (
    <div className="enterprise-panel overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-border/70 p-4 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setVisibleCount(LOG_PAGE_SIZE);
            }}
            placeholder="Поиск по командам и output"
            className="pl-9"
          />
        </div>
        <Button variant={wrap ? "default" : "outline"} size="sm" className="h-10 gap-1.5" onClick={() => setWrap((value) => !value)}>
          <WrapText className="h-4 w-4" />
          Wrap
        </Button>
      </div>
      <div className="space-y-3 p-4">
        {visible.length ? visible.map((log) => (
          <div key={log.id} className="overflow-hidden rounded-lg border border-border/70 bg-[#0f141c]">
            <div className="flex flex-wrap items-center gap-2 border-b border-white/5 bg-white/[0.03] px-4 py-3">
              <StatusBadge label={log.exit_code === 0 ? "Завершено" : `Код ${log.exit_code}`} tone={log.exit_code === 0 ? "success" : "danger"} />
              <span className="min-w-0 flex-1 break-all font-mono text-xs text-foreground">{log.command || log.title}</span>
              <span className="text-xs text-muted-foreground">{formatDuration(log.duration_ms)}</span>
              <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => void copyLog(log)} aria-label="Copy log">
                {copied === log.id ? <Check className="h-3.5 w-3.5 text-success" /> : <Clipboard className="h-3.5 w-3.5" />}
              </Button>
            </div>
            {log.stdout ? (
              <pre className={cn("max-h-80 overflow-auto px-4 py-3 font-mono text-xs leading-5 text-foreground/80", wrap && "whitespace-pre-wrap")}>
                {log.stdout}
              </pre>
            ) : null}
            {log.stderr ? (
              <pre className={cn("max-h-60 overflow-auto border-t border-destructive/20 px-4 py-3 font-mono text-xs leading-5 text-destructive", wrap && "whitespace-pre-wrap")}>
                {log.stderr}
              </pre>
            ) : null}
          </div>
        )) : <EmptyRunDataPanel report={report} kind="logs" />}
        {hasMore ? (
          <div className="flex justify-center">
            <Button variant="outline" size="sm" onClick={() => setVisibleCount((value) => value + LOG_PAGE_SIZE)}>
              Показать ещё {Math.min(LOG_PAGE_SIZE, filtered.length - visible.length)}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ArtifactsTab({ report }: { report: AgentRunReportResponse }) {
  const artifacts = report.artifacts;
  const ready = Boolean(report.artifact_state?.ready ?? report.report_state?.artifacts_ready ?? report.report_state?.report_ready);
  const [downloadError, setDownloadError] = useState("");
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const handleDownload = async (artifact: AgentRunReportArtifact) => {
    setDownloadError("");
    setDownloadingId(artifact.id);
    try {
      await downloadArtifact(artifact);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Не удалось скачать артефакт.");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDownloadAll = async () => {
    setDownloadError("");
    setDownloadingId("all");
    try {
      const downloadedBundle = await downloadArtifactBundle(report);
      if (!downloadedBundle) {
        for (const artifact of artifacts) {
          await downloadArtifact(artifact);
        }
      }
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Не удалось скачать артефакты.");
    } finally {
      setDownloadingId(null);
    }
  };

  if (!ready) {
    return (
      <div className="enterprise-panel overflow-hidden">
        <div className="border-b border-border/70 p-4">
          <h3 className="text-base font-semibold text-foreground">{report.artifact_state?.title || "Артефакты ещё не готовы"}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {report.artifact_state?.description || "Артефакты появятся после финального отчёта."}
          </p>
        </div>
        <div className="workspace-empty m-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">{report.artifact_state?.empty_title || "Артефакты появятся после финального отчёта"}</p>
          <p className="mt-1">{report.artifact_state?.empty_description || report.report_state?.next_expected}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="enterprise-panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-border/70 p-4">
        <div>
          <h3 className="text-base font-semibold text-foreground">{report.artifact_state?.title || "Артефакты запуска"}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {report.artifact_state?.description || "Файлы собраны из сохранённых данных запуска"}
            {report.artifact_state?.bundle_ready && report.artifact_state?.total_size_label ? (
              <span className="ml-2 text-muted-foreground/80">
                {report.artifact_state.artifact_count || artifacts.length} файлов · {report.artifact_state.total_size_label}
              </span>
            ) : null}
            {report.artifact_state?.manifest_ready ? (
              <span className="ml-2 text-success">manifest проверен</span>
            ) : null}
          </p>
        </div>
        {artifacts.length ? (
          <Button
            size="sm"
            className="h-10 gap-1.5"
            disabled={downloadingId !== null}
            onClick={() => void handleDownloadAll()}
          >
            <Download className="h-4 w-4" />
            {downloadingId === "all" ? "Скачивание" : "Скачать всё"}
          </Button>
        ) : null}
      </div>
      {downloadError ? <div className="border-b border-border/70 px-4 py-3 text-sm text-destructive">{downloadError}</div> : null}
      {artifacts.length ? (
        <ul className="divide-y divide-border/70">
          {artifacts.map((artifact) => (
            <li key={artifact.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/45 text-primary">
                {artifact.name.endsWith(".json") ? <FileCode2 className="h-5 w-5" /> : artifact.name.endsWith(".zip") ? <FileArchive className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="break-all font-mono text-sm font-medium text-foreground">{artifact.name}</span>
                  <span className="rounded-md border border-border/70 bg-background/45 px-2 py-0.5 text-xs text-muted-foreground">{artifact.type}</span>
                  {artifact.truncated ? <span className="text-xs text-warning">truncated</span> : null}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{artifact.description}</p>
                <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs text-muted-foreground">
                  <span>{artifact.size_label}</span>
                  {artifact.checksum_sha256 ? <span>sha256:{artifact.checksum_sha256.slice(0, 12)}</span> : null}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="h-10 gap-1.5"
                disabled={downloadingId !== null}
                onClick={() => void handleDownload(artifact)}
              >
                <Download className="h-4 w-4" />
                {downloadingId === artifact.id ? "Скачивание" : "Скачать"}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="workspace-empty m-4 text-sm text-muted-foreground">Артефакты не сформированы.</div>
      )}
    </div>
  );
}

function EmptyRunDataPanel({ report, kind }: { report: AgentRunReportResponse; kind: "logs" | "steps" }) {
  const active = !report.report_state?.is_terminal && !report.report_state?.report_ready;
  const title = kind === "logs" ? "Логи ещё не записаны" : "Шаги агента ещё не сохранены";
  const terminalTitle = kind === "logs" ? "Логи не найдены" : "Шаги агента не найдены";
  const description = active
    ? report.report_state?.next_expected || "Данные появятся после того, как агент начнёт выполнять команды и задачи."
    : "В этом запуске backend не сохранил данные для этой вкладки.";

  return (
    <div className="workspace-empty text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{active ? title : terminalTitle}</p>
      <p className="mt-1 max-w-2xl leading-6">{description}</p>
    </div>
  );
}

