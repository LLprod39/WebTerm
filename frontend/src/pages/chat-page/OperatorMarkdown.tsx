import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Server } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

import { normalizeOperatorMarkdown, stripMarkdownTables } from "./markdownNormalize";

/** Readable, low-chrome markdown for operator chat. */
const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-1.5 mt-0 text-[15px] font-semibold tracking-tight leading-snug text-foreground">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-1 mt-2.5 text-[13.5px] font-semibold tracking-tight leading-snug text-foreground first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-0.5 mt-2 text-[13px] font-semibold text-foreground first:mt-0">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="my-1.5 text-[13.5px] leading-6 text-foreground/90 first:mt-0 last:mb-0">{children}</p>
  ),
  ul: ({ children }) => <ul className="my-1.5 space-y-1 pl-4 list-disc marker:text-primary/55">{children}</ul>,
  ol: ({ children }) => (
    <ol className="my-1.5 list-decimal space-y-1 pl-4 marker:font-mono marker:text-[10px] marker:text-muted-foreground">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="text-[13.5px] leading-6 text-foreground/90 pl-0.5">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic text-foreground/85">{children}</em>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-primary underline decoration-primary/25 underline-offset-2 hover:decoration-primary"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-1.5 border-l-2 border-primary/35 py-0.5 pl-2 text-[12px] text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-2 border-border/50" />,
  code: ({ className, children, ...props }) => {
    const isBlock = Boolean(className?.includes("language-")) || String(children).includes("\n");
    if (!isBlock) {
      return (
        <code
          className="rounded border border-border/40 bg-muted/50 px-1 py-px font-mono text-[11px] text-foreground"
          {...props}
        >
          {children}
        </code>
      );
    }
    return <CodeBlock className={className}>{children}</CodeBlock>;
  },
  pre: ({ children }) => <>{children}</>,
  table: ({ children }) => (
    <div className="my-1.5 overflow-hidden rounded-sm border border-border/60">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[360px] border-collapse text-left text-[11.5px] leading-4">{children}</table>
      </div>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-muted/25 text-[10px] text-muted-foreground">{children}</thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-border/30 last:border-0 odd:bg-transparent even:bg-muted/[0.08] hover:bg-primary/[0.03]">
      {children}
    </tr>
  ),
  th: ({ children }) => (
    <th className="whitespace-nowrap px-2 py-1 font-medium first:pl-2.5 last:pr-2.5">{children}</th>
  ),
  td: ({ children }) => (
    <td className="whitespace-nowrap px-2 py-0.5 align-middle first:pl-2.5 last:pr-2.5">
      <TableCell>{children}</TableCell>
    </td>
  ),
};

function TableCell({ children }: { children: ReactNode }) {
  const text = flattenText(children).trim();
  if (!text || text === "—" || /^-+$/.test(text)) {
    return <span className="text-muted-foreground/50">—</span>;
  }
  if (text === "true" || text === "false" || text === "yes" || text === "no") {
    const on = text === "true" || text === "yes";
    return (
      <span className={cn("font-mono text-[10px]", on ? "text-success" : "text-muted-foreground")}>
        {text}
      </span>
    );
  }
  if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(text)) {
    return <span className="font-mono text-[11px] text-info/90">{text}</span>;
  }
  if (/^\d+$/.test(text) && text.length <= 5) {
    return <span className="font-mono tabular-nums text-muted-foreground">{text}</span>;
  }
  if (/^[a-z0-9]+(?:-[a-z0-9]+)+$/i.test(text) && text.length > 3) {
    return (
      <span className="inline-flex items-center gap-1 font-medium text-foreground">
        <Server className="h-2.5 w-2.5 shrink-0 opacity-70" />
        {text}
      </span>
    );
  }
  return <span className="text-foreground/90">{children}</span>;
}

function flattenText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(flattenText).join("");
  if (typeof node === "object" && "props" in (node as object)) {
    return flattenText((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

function CodeBlock({ className, children }: { className?: string; children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const code = String(children).replace(/\n$/, "");
  const lang = /language-(\w+)/.exec(className || "")?.[1] || "";

  return (
    <div className="group relative my-1.5 overflow-hidden rounded-sm border border-border/60 bg-[#0c0f14]">
      <div className="flex items-center justify-between border-b border-white/5 px-2 py-0.5">
        <span className="font-mono text-[9px] uppercase tracking-wider text-white/35">{lang || "code"}</span>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[9px] text-white/40 opacity-0 transition hover:bg-white/10 hover:text-white/75 group-hover:opacity-100"
          onClick={() => {
            void navigator.clipboard.writeText(code);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          }}
        >
          {copied ? <Check className="h-2.5 w-2.5" /> : <Copy className="h-2.5 w-2.5" />}
        </button>
      </div>
      <pre className="overflow-x-auto p-2 font-mono text-[11px] leading-4 text-success/90">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export function OperatorMarkdown({
  content,
  className,
  streaming = false,
  stripTables = false,
}: {
  content: string;
  className?: string;
  streaming?: boolean;
  /** When true, remove markdown tables (structured DataTableCard already shown). */
  stripTables?: boolean;
}) {
  let normalized = normalizeOperatorMarkdown(content);
  if (stripTables) {
    normalized = stripMarkdownTables(normalized);
  }
  if (!normalized.trim()) {
    return streaming ? (
      <span className="inline-block h-3.5 w-0.5 animate-pulse bg-primary/80" />
    ) : null;
  }

  return (
    <div className={cn("operator-md max-w-[min(920px,100%)]", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {normalized}
      </ReactMarkdown>
      {streaming ? (
        <span className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse bg-primary/80 align-middle" />
      ) : null}
    </div>
  );
}
