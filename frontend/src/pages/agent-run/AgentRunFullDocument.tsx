import { useMemo, useState, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { Check, Copy, Download, FileWarning } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { backendPath } from "@/lib/api";
import { cn } from "@/lib/utils";

import { collapseRepeatedCompactBlocks } from "./compactReportDisplay";
import { copyText, downloadTextFile } from "./reportShared";
import { extractReportToc, shouldShowReportToc, type ReportTocItem } from "./reportToc";
import type { ReportDocumentViewModel } from "./reportViewModel";

/** Drop legacy standalone «Доказательства» dumps — facts belong in narrative sections. */
function stripEvidenceDumpSection(markdown: string) {
  return markdown
    .replace(/^##\s*Доказательства\s*\r?\n[\s\S]*?(?=^##\s|\Z)/gim, "")
    .replace(/\n{3,}/g, "\n\n");
}

function normalizeMarkdownForDisplay(markdown: string) {
  return stripEvidenceDumpSection(collapseRepeatedCompactBlocks(markdown))
    .replace(/([.!?])\s*-\s+(?=\S)/g, "$1\n- ")
    .replace(/^Outcome:\s*/gim, "Техническое завершение запуска: ")
    .replace(/^Техническое завершение запуска:\s*failed\b/gim, "Техническое завершение запуска: ошибка")
    .replace(/\bLLM call failed\b/gi, "ошибка LLM");
}

function headingId(node: { position?: { start?: { line?: number } } } | undefined, toc: ReportTocItem[]) {
  const line = node?.position?.start?.line;
  return toc.find((item) => item.line === line)?.id;
}

function MarkdownHeading({
  level,
  id,
  children,
}: {
  level: 1 | 2 | 3;
  id?: string;
  children: ReactNode;
}) {
  const Tag = `h${level}` as const;
  const classes = level === 1
    ? "mt-8 scroll-mt-28 text-2xl font-bold tracking-tight first:mt-0"
    : level === 2
      ? "mt-8 scroll-mt-28 border-b border-border/70 pb-2 text-xl font-semibold"
      : "mt-6 scroll-mt-28 text-base font-semibold";
  return <Tag id={id} className={classes}>{children}</Tag>;
}

export function AgentRunFullDocument({
  document,
  fullText,
  loading,
  error,
  runId,
}: {
  document: ReportDocumentViewModel;
  fullText?: string;
  loading: boolean;
  error: unknown;
  runId: number;
}) {
  const [copied, setCopied] = useState(false);
  const sourceMarkdown = fullText || document.preview;
  const markdown = normalizeMarkdownForDisplay(sourceMarkdown);
  const toc = useMemo(() => extractReportToc(markdown), [markdown]);
  const showToc = shouldShowReportToc(markdown, toc);
  const isPreview = !fullText && document.previewTruncated;
  const filename = `agent-run-${runId}-report.md`;

  if (!document.available) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-sm text-muted-foreground">
        Полный документ ещё не сформирован.
      </div>
    );
  }

  return (
    <section aria-labelledby="full-report-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="full-report-heading" className="sr-only">
          {document.title || "Отчёт"}
        </h2>
        <div className="flex flex-wrap gap-1.5">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 gap-1.5 text-muted-foreground"
            disabled={!markdown}
            onClick={() => {
              void copyText(markdown).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1800);
              });
            }}
          >
            {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
            {copied ? "Скопировано" : "Копировать"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 gap-1.5 text-muted-foreground"
            disabled={!markdown}
            onClick={() => downloadTextFile(filename, markdown, document.contentType)}
          >
            <Download className="h-3.5 w-3.5" aria-hidden />
            {isPreview ? "Фрагмент" : "Скачать"}
          </Button>
          {document.downloadUrl ? (
            <Button size="sm" variant="ghost" className="h-8 gap-1.5 text-muted-foreground" asChild>
              <a href={backendPath(document.downloadUrl)} download>
                <Download className="h-3.5 w-3.5" aria-hidden />
                Оригинал
              </a>
            </Button>
          ) : null}
        </div>
      </div>

      {loading ? <p role="status" className="text-sm text-muted-foreground">Загружаем отчёт…</p> : null}
      {error ? (
        <div role="alert" className="flex gap-2 rounded-sm border border-warning/35 bg-warning/10 px-3 py-2 text-sm text-foreground">
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
          <span>{error instanceof Error ? error.message : "Полный документ недоступен."} Показан сохранённый фрагмент.</span>
        </div>
      ) : null}
      {isPreview ? (
        <div role="status" className="flex gap-2 rounded-sm border border-warning/35 bg-warning/10 px-3 py-2 text-sm text-foreground">
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
          <span>Показан усечённый фрагмент. Скачайте оригинал без потерь.</span>
        </div>
      ) : null}

      <div className={cn("grid gap-6", showToc ? "lg:grid-cols-[11rem_minmax(0,1fr)]" : "")}>
        {showToc ? (
          <nav aria-label="Содержание отчёта" className="hidden self-start lg:sticky lg:top-28 lg:block">
            <p className="type-label mb-2 text-muted-foreground">Содержание</p>
            <ol className="space-y-0.5 text-sm">
              {toc.filter((item) => item.depth <= 2).map((item) => (
                <li key={`${item.line}-${item.id}`} style={{ paddingInlineStart: `${(item.depth - 1) * 0.65}rem` }}>
                  <a
                    className="block rounded-sm px-1.5 py-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    href={`#${item.id}`}
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}

        <article className="min-w-0 text-[15px] leading-7 text-foreground">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ node, children }) => <MarkdownHeading level={1} id={headingId(node, toc)}>{children}</MarkdownHeading>,
              h2: ({ node, children }) => <MarkdownHeading level={2} id={headingId(node, toc)}>{children}</MarkdownHeading>,
              h3: ({ node, children }) => <MarkdownHeading level={3} id={headingId(node, toc)}>{children}</MarkdownHeading>,
              a: ({ href, children, ...props }: ComponentPropsWithoutRef<"a">) => (
                <a
                  {...props}
                  href={href}
                  className="font-medium text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary"
                  target={href?.startsWith("http") ? "_blank" : undefined}
                  rel={href?.startsWith("http") ? "noreferrer" : undefined}
                >
                  {children}
                </a>
              ),
              p: ({ children }) => <p className="my-3 text-foreground/90">{children}</p>,
              ul: ({ children }) => <ul className="my-3 list-disc space-y-1.5 pl-5 text-foreground/90">{children}</ul>,
              ol: ({ children }) => <ol className="my-3 list-decimal space-y-1.5 pl-5 text-foreground/90">{children}</ol>,
              blockquote: ({ children }) => (
                <blockquote className="my-5 border-l-2 border-primary/45 pl-4 text-muted-foreground">{children}</blockquote>
              ),
              table: ({ children }) => (
                <div className="my-4 overflow-x-auto rounded-sm border border-border">
                  <table className="w-full border-collapse text-left text-sm">{children}</table>
                </div>
              ),
              th: ({ children }) => <th className="border-b border-border bg-surface-1 px-3 py-2 font-semibold">{children}</th>,
              td: ({ children }) => <td className="border-b border-border/70 px-3 py-2 align-top">{children}</td>,
              code: ({ className, children }) =>
                className ? (
                  <code className={`${className} block overflow-x-auto rounded-sm bg-surface-1 p-3 font-mono text-xs leading-6`}>{children}</code>
                ) : (
                  <code className="rounded bg-surface-1 px-1.5 py-0.5 font-mono text-[0.85em]">{children}</code>
                ),
              pre: ({ children }) => <pre className="my-4 overflow-x-auto">{children}</pre>,
            }}
          >
            {markdown || "_Документ пуст._"}
          </ReactMarkdown>
        </article>
      </div>
    </section>
  );
}
