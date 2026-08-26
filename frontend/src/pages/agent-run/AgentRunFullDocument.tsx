import { useMemo, useState, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { Check, Copy, Download, ExternalLink, FileWarning } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { backendPath } from "@/lib/api";

import { copyText, downloadTextFile } from "./reportShared";
import type { ReportDocumentViewModel } from "./reportViewModel";

interface TocItem {
  depth: number;
  label: string;
  id: string;
  line: number;
}

function slug(value: string) {
  return value
    .toLocaleLowerCase("ru-RU")
    .normalize("NFKD")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "") || "section";
}

function extractToc(markdown: string): TocItem[] {
  const seen = new Map<string, number>();
  const result: TocItem[] = [];
  let fenced = false;
  markdown.split(/\r?\n/).forEach((line, index) => {
    if (/^\s*(```|~~~)/.test(line)) {
      fenced = !fenced;
      return;
    }
    if (fenced) return;
    const match = /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(line);
    if (!match) return;
    const label = match[2].replace(/[*_`~]/g, "").trim();
    const base = slug(label);
    const count = (seen.get(base) || 0) + 1;
    seen.set(base, count);
    result.push({ depth: match[1].length, label, id: count === 1 ? base : `${base}-${count}`, line: index + 1 });
  });
  return result;
}

function normalizeMarkdownForDisplay(markdown: string) {
  return markdown
    .replace(/([.!?])\s*-\s+(?=\S)/g, "$1\n- ")
    .replace(/^Outcome:\s*/gim, "Техническое завершение запуска: ")
    .replace(/^Техническое завершение запуска:\s*failed\b/gim, "Техническое завершение запуска: ошибка")
    .replace(/\bLLM call failed\b/gi, "ошибка LLM");
}

function headingId(node: { position?: { start?: { line?: number } } } | undefined, toc: TocItem[]) {
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
      ? "mt-8 scroll-mt-28 border-b border-border pb-2 text-xl font-semibold"
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
  const toc = useMemo(() => extractToc(markdown), [markdown]);
  const isPreview = !fullText && document.previewTruncated;
  const hasLegacyTechnicalOutcome = /^Outcome:/im.test(sourceMarkdown);
  const filename = `agent-run-${runId}-report.md`;

  if (!document.available) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-sm text-muted-foreground">
        Полный документ ещё не сформирован.
      </div>
    );
  }

  return (
    <section aria-labelledby="full-report-heading" className="space-y-4">
      <div className="flex flex-col gap-3 rounded-sm border border-border bg-card p-4 shadow-elev-1 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id="full-report-heading" className="font-display text-lg font-semibold text-foreground">
            {document.title || "Полный отчёт"}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {document.contentType} · {document.sizeBytes ? `${document.sizeBytes.toLocaleString("ru-RU")} байт` : "размер не указан"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={!markdown}
            onClick={() => {
              void copyText(markdown).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1800);
              });
            }}
          >
            {copied ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
            {copied ? "Скопировано" : "Копировать"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={!markdown}
            onClick={() => downloadTextFile(filename, markdown, document.contentType)}
          >
            <Download className="h-4 w-4" aria-hidden />
            {isPreview ? "Скачать фрагмент" : "Скачать текст"}
          </Button>
          {document.downloadUrl ? (
            <Button size="sm" variant="outline" className="gap-1.5" asChild>
              <a href={backendPath(document.downloadUrl)} download>
                <ExternalLink className="h-4 w-4" aria-hidden />
                Скачать оригинал
              </a>
            </Button>
          ) : null}
        </div>
      </div>

      {loading ? <p role="status" className="text-sm text-muted-foreground">Загружаем полный документ…</p> : null}
      {error ? (
        <div role="alert" className="flex gap-2 rounded-sm border border-warning/35 bg-warning/10 p-3 text-sm text-foreground">
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
          <span>{error instanceof Error ? error.message : "Полный документ недоступен."} Показан сохранённый фрагмент.</span>
        </div>
      ) : null}
      {isPreview ? (
        <div role="status" className="flex gap-2 rounded-sm border border-warning/35 bg-warning/10 p-3 text-sm text-foreground">
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
          <span>Показан усечённый фрагмент. Используйте «Оригинал», чтобы скачать документ без потерь.</span>
        </div>
      ) : null}
      {hasLegacyTechnicalOutcome ? (
        <div role="note" className="rounded-sm border border-border bg-surface-0 p-3 text-sm leading-6 text-muted-foreground">
          В исходном legacy-документе поле Outcome относится к техническому завершению запуска. Основной результат задачи показан отдельно в сводке; оригинал сохранён без изменений.
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[13rem_minmax(0,1fr)]">
        {toc.length ? (
          <nav aria-label="Содержание отчёта" className="self-start rounded-sm border border-border bg-surface-0 p-3 lg:sticky lg:top-28">
            <p className="type-label mb-2 text-muted-foreground">Содержание</p>
            <ol className="space-y-1 text-sm">
              {toc.map((item) => (
                <li key={`${item.line}-${item.id}`} style={{ paddingInlineStart: `${(item.depth - 1) * 0.75}rem` }}>
                  <a className="block rounded-sm px-2 py-1.5 text-muted-foreground hover:bg-surface-1 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" href={`#${item.id}`}>
                    {item.label}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}

        <article className="min-w-0 rounded-sm border border-border bg-card p-4 text-sm leading-7 text-foreground shadow-elev-1 sm:p-6">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ node, children }) => <MarkdownHeading level={1} id={headingId(node, toc)}>{children}</MarkdownHeading>,
              h2: ({ node, children }) => <MarkdownHeading level={2} id={headingId(node, toc)}>{children}</MarkdownHeading>,
              h3: ({ node, children }) => <MarkdownHeading level={3} id={headingId(node, toc)}>{children}</MarkdownHeading>,
              a: ({ href, children, ...props }: ComponentPropsWithoutRef<"a">) => (
                <a {...props} href={href} className="font-medium text-primary underline decoration-primary/45 underline-offset-4 hover:decoration-primary" target={href?.startsWith("http") ? "_blank" : undefined} rel={href?.startsWith("http") ? "noreferrer" : undefined}>
                  {children}
                </a>
              ),
              p: ({ children }) => <p className="my-3">{children}</p>,
              ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,
              ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,
              blockquote: ({ children }) => <blockquote className="my-4 border-l-2 border-primary/50 bg-surface-0 px-4 py-1 text-muted-foreground">{children}</blockquote>,
              table: ({ children }) => <div className="my-4 overflow-x-auto"><table className="w-full border-collapse text-left text-sm">{children}</table></div>,
              th: ({ children }) => <th className="border border-border bg-surface-1 px-3 py-2 font-semibold">{children}</th>,
              td: ({ children }) => <td className="border border-border px-3 py-2 align-top">{children}</td>,
              code: ({ className, children }) => className ? (
                <code className={`${className} block overflow-x-auto rounded-sm bg-surface-2 p-3 font-mono text-xs leading-6`}>{children}</code>
              ) : <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs">{children}</code>,
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
