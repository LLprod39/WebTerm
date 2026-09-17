import type { Components, Options } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Server } from "lucide-react";
import { Children, Fragment, memo, useMemo, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

import { normalizeOperatorMarkdown, stripMarkdownTables } from "./markdownNormalize";

const STREAM_CURSOR_MARKER = "\uE000";

type MarkdownAstNode = {
  type: string;
  value?: string;
  children?: MarkdownAstNode[];
};

const cursorParentTypes = new Set(["paragraph", "heading"]);

function findLastCursorParent(node: MarkdownAstNode): MarkdownAstNode | null {
  if (cursorParentTypes.has(node.type) && node.children) return node;
  const lastChild = node.children?.at(-1);
  return lastChild ? findLastCursorParent(lastChild) : null;
}

/** Injects an inert marker after parsing so streaming never changes markdown syntax. */
function remarkStreamingCursor() {
  return (tree: MarkdownAstNode) => {
    const parent = findLastCursorParent(tree);
    if (parent?.children) {
      parent.children.push({ type: "text", value: STREAM_CURSOR_MARKER });
      return;
    }
    tree.children ??= [];
    tree.children.push({
      type: "paragraph",
      children: [{ type: "text", value: STREAM_CURSOR_MARKER }],
    });
  };
}

const staticRemarkPlugins: NonNullable<Options["remarkPlugins"]> = [remarkGfm];
const streamingRemarkPlugins: NonNullable<Options["remarkPlugins"]> = [
  remarkGfm,
  remarkStreamingCursor,
];

function StreamingCursor() {
  return (
    <span
      aria-hidden="true"
      data-operator-stream-cursor
      className="relative inline-block h-[1em] w-0 align-[-0.12em] motion-safe:animate-pulse after:absolute after:inset-y-[0.08em] after:left-[2px] after:w-px after:rounded-full after:bg-primary/80 after:content-['']"
    />
  );
}

function withStreamingCursor(children: ReactNode): ReactNode {
  return Children.map(children, (child, childIndex) => {
    if (typeof child !== "string" || !child.includes(STREAM_CURSOR_MARKER)) return child;
    const parts = child.split(STREAM_CURSOR_MARKER);
    return parts.map((part, partIndex) => (
      <Fragment key={`${childIndex}-${partIndex}`}>
        {part}
        {partIndex < parts.length - 1 ? <StreamingCursor /> : null}
      </Fragment>
    ));
  });
}

/** Readable, low-chrome markdown for operator chat. */
const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-1.5 mt-0 text-[15px] font-semibold tracking-tight leading-snug text-foreground">
      {withStreamingCursor(children)}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-1 mt-2.5 text-[13.5px] font-semibold tracking-tight leading-snug text-foreground first:mt-0">
      {withStreamingCursor(children)}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-0.5 mt-2 text-[13px] font-semibold text-foreground first:mt-0">
      {withStreamingCursor(children)}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-0.5 mt-2 text-[13px] font-semibold text-foreground first:mt-0">
      {withStreamingCursor(children)}
    </h4>
  ),
  h5: ({ children }) => (
    <h5 className="mb-0.5 mt-2 text-[12.5px] font-semibold text-foreground first:mt-0">
      {withStreamingCursor(children)}
    </h5>
  ),
  h6: ({ children }) => (
    <h6 className="mb-0.5 mt-2 text-[12px] font-semibold text-muted-foreground first:mt-0">
      {withStreamingCursor(children)}
    </h6>
  ),
  p: ({ children }) => (
    <p className="my-2 text-[14px] leading-6 text-foreground/90 first:mt-0 last:mb-0">
      {withStreamingCursor(children)}
    </p>
  ),
  ul: ({ children }) => (
    <ul className="my-2 list-disc space-y-1.5 pl-5 marker:text-primary/55">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 list-decimal space-y-1.5 pl-5 marker:font-mono marker:text-[11px] marker:text-muted-foreground">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="pl-0.5 text-[14px] leading-6 text-foreground/90">
      {withStreamingCursor(children)}
    </li>
  ),
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
    <div
      data-operator-table
      className="my-2 w-full min-w-0 overflow-hidden rounded-md border border-border/60"
    >
      <table className="w-full min-w-0 table-fixed border-collapse text-left text-[13px] leading-[1.5]">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-muted/25 text-[11px] text-muted-foreground">{children}</thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-border/30 last:border-0 odd:bg-transparent even:bg-muted/[0.08] hover:bg-primary/[0.03]">
      {children}
    </tr>
  ),
  th: ({ children }) => (
    <th className="min-w-0 whitespace-normal break-words px-2.5 py-1.5 align-top font-medium [overflow-wrap:anywhere] first:w-[40%] first:pl-3 last:pr-3 sm:first:w-[26%]">
      {withStreamingCursor(children)}
    </th>
  ),
  td: ({ children }) => (
    <td className="min-w-0 whitespace-normal break-words px-2.5 py-1.5 align-top [overflow-wrap:anywhere] first:w-[40%] first:pl-3 last:pr-3 sm:first:w-[26%]">
      <TableCell>{withStreamingCursor(children)}</TableCell>
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
      <span className="inline-flex max-w-full min-w-0 items-start gap-1 font-medium text-foreground">
        <Server className="mt-0.5 h-2.5 w-2.5 shrink-0 opacity-70" />
        <span className="min-w-0 break-words [overflow-wrap:anywhere]">{text}</span>
      </span>
    );
  }
  return (
    <span className="block min-w-0 whitespace-normal break-words text-foreground/90 [overflow-wrap:anywhere]">
      {children}
    </span>
  );
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

type OperatorMarkdownProps = {
  content: string;
  className?: string;
  streaming?: boolean;
  /** When true, remove markdown tables (structured DataTableCard already shown). */
  stripTables?: boolean;
};

export const OperatorMarkdown = memo(function OperatorMarkdown({
  content,
  className,
  streaming = false,
  stripTables = false,
}: OperatorMarkdownProps) {
  const normalized = useMemo(() => {
    const markdown = normalizeOperatorMarkdown(content);
    return stripTables ? stripMarkdownTables(markdown) : markdown;
  }, [content, stripTables]);

  if (!normalized.trim()) {
    return streaming && !stripTables ? (
      <div className={cn("operator-md min-h-6 max-w-[min(920px,100%)]", className)}>
        <StreamingCursor />
      </div>
    ) : null;
  }

  return (
    <div className={cn("operator-md max-w-[min(920px,100%)]", className)}>
      <ReactMarkdown
        remarkPlugins={streaming ? streamingRemarkPlugins : staticRemarkPlugins}
        components={components}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
});
