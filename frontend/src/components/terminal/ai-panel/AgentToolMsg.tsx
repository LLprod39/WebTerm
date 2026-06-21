import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Wrench,
} from "lucide-react";
import type { AiMessage } from "../ai-types";

function formatDuration(ms?: number): string {
  if (ms === undefined || ms < 0) return "";
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(sec < 10 ? 1 : 0)}s`;
  const min = Math.floor(sec / 60);
  return `${min}m${Math.round(sec - min * 60)}s`;
}

// Collapsed-by-default tool call row. Shows a single-line summary so the
// timeline stays dense; click to expand args + output + error details.
// Short commands are shown inline in the header so the user sees *what*
// was run without having to expand.
export function AgentToolMsg({ msg }: { msg: AiMessage }) {
  const [expanded, setExpanded] = useState(false);
  const tool = msg.agentToolName || "tool";
  const ok = msg.agentToolOk !== false;
  const running = msg.agentToolOutput === undefined && msg.agentToolError === undefined;
  const args = msg.agentToolArgs || {};
  const target =
    typeof (args as Record<string, unknown>).target === "string"
      ? (args as Record<string, string>).target
      : "";
  // Show the command itself on the collapsed row for shell-like tools so
  // the user instantly sees the intent without clicking.
  const cmdPreview =
    typeof (args as Record<string, unknown>).cmd === "string"
      ? (args as Record<string, string>).cmd
      : typeof (args as Record<string, unknown>).command === "string"
        ? (args as Record<string, string>).command
        : "";
  const duration = formatDuration(msg.agentDurationMs);
  const exitCode = msg.agentToolExitCode;
  const nonZeroExit = typeof exitCode === "number" && exitCode !== 0;
  const statusIcon = running ? (
    <Loader2 className="h-3 w-3 shrink-0 animate-spin text-warning" />
  ) : ok && !nonZeroExit ? (
    <CheckCircle2 className="h-3 w-3 shrink-0 text-success" />
  ) : (
    <AlertTriangle className="h-3 w-3 shrink-0 text-destructive" />
  );
  // Shell tool prefixes its output with "Target: X\nExit: N\n" for the
  // LLM. We already surface target/exit as structured badges, so strip
  // that prefix from the user-facing preview to kill noise.
  const rawOutput = msg.agentToolOutput || "";
  const output = rawOutput.replace(
    /^Target:\s*\S+\s*\n(?:Exit:\s*-?\d+\s*\n)?/,
    "",
  );
  const outputLines = output ? output.split("\n") : [];
  const errorState = !ok || nonZeroExit;
  return (
    <div className={`overflow-hidden rounded-lg border ${errorState ? "border-destructive/40" : "border-border/50"}`}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={`flex w-full items-center gap-1.5 px-2 py-1 text-left text-xs transition-colors hover:bg-secondary/30 ${
          errorState ? "bg-destructive/5 text-destructive" : "bg-secondary/15 text-foreground"
        }`}
        title={cmdPreview || tool}
      >
        {statusIcon}
        <Wrench className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="shrink-0 font-mono text-xs text-muted-foreground">{tool}</span>
        {target ? (
          <span className="shrink-0 font-mono text-xs text-muted-foreground/80">·{target}</span>
        ) : null}
        {cmdPreview ? (
          <code className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">
            {cmdPreview}
          </code>
        ) : (
          <span className="flex-1" />
        )}
        {nonZeroExit ? (
          <span
            className="shrink-0 rounded border border-destructive/40 bg-destructive/10 px-1 font-mono text-xs font-semibold uppercase tracking-wide text-destructive"
            title={`exit code ${exitCode}`}
          >
            exit {exitCode}
          </span>
        ) : null}
        {duration ? (
          <span className="shrink-0 text-xs text-muted-foreground">{duration}</span>
        ) : null}
        {expanded ? (
          <ChevronUp className="h-3 w-3 shrink-0 opacity-40" />
        ) : (
          <ChevronDown className="h-3 w-3 shrink-0 opacity-40" />
        )}
      </button>
      {expanded ? (
        <div className="space-y-1.5 border-t border-border/30 bg-background/40 px-2 py-1.5 text-xs">
          {Object.keys(args).length > 0 ? (
            <details className="group">
              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                аргументы ({Object.keys(args).length})
              </summary>
              <pre className="mt-1 max-h-32 overflow-auto rounded bg-secondary/40 p-1.5 font-mono text-xs leading-snug text-muted-foreground">
                {JSON.stringify(args, null, 2)}
              </pre>
            </details>
          ) : null}
          {output ? (
            <pre className="max-h-80 overflow-auto rounded border border-border/30 bg-terminal-bg/80 p-1.5 font-mono text-xs leading-snug text-secondary-foreground">
              {output}
            </pre>
          ) : null}
          {!output && outputLines.length === 0 && running ? (
            <p className="text-xs italic text-muted-foreground">выполняется…</p>
          ) : null}
          {msg.agentToolError ? (
            <p className="rounded border border-destructive/30 bg-destructive/5 px-1.5 py-1 text-xs text-destructive">
              {msg.agentToolError}
            </p>
          ) : null}
        </div>
      ) : output ? (
        // Collapsed inline preview — up to 2 lines of output so the user
        // sees immediate feedback without expanding.
        <div className="border-t border-border/20 bg-background/30 px-2 py-0.5 font-mono text-xs leading-snug text-muted-foreground/80">
          <div className="max-h-8 overflow-hidden">
            {outputLines.slice(0, 2).map((line, idx) => (
              <div key={idx} className="truncate">
                {line || "\u00a0"}
              </div>
            ))}
          </div>
          {outputLines.length > 2 ? (
            <div className="text-xs italic text-muted-foreground/60">
              +{outputLines.length - 2} строк — кликните чтобы раскрыть
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
