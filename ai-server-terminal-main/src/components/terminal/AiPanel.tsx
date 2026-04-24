import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Bot,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Clock,
  Copy,
  FileText,
  Footprints,
  HelpCircle,
  ListTodo,
  Loader2,
  Pause,
  RotateCcw,
  Send,
  Server as ServerIcon,
  Settings2,
  Sparkles,
  Square,
  Terminal as TerminalIcon,
  Trash2,
  Wand2,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { riskBadgeClass, useAiCommandRisk } from "@/hooks/useAiCommandRisk";
import { AiQuestionCard } from "./AiQuestionCard";
import type {
  AiAssistantSettings,
  AiChatMode,
  AiCommand,
  AiExecutionMode,
  AiMessage,
} from "./ai-types";
import { NovaContextCard } from "./nova/NovaContextCard";
import { NovaContextSettings } from "./nova/NovaContextSettings";

interface AiPanelProps {
  onClose: () => void;
  onSend: (text: string) => void;
  onStop: () => void;
  onConfirm?: (id: number) => void;
  onCancel?: (id: number) => void;
  onReply?: (qId: string, text: string) => void;
  onClearChat?: () => void;
  onGenerateReport?: (force?: boolean) => void;
  onClearMemory?: () => void;
  // A6: ask the backend to explain a single executed command inline.
  onExplainCommand?: (cmd: AiCommand) => void;
  onSettingsChange: (settings: AiAssistantSettings) => void;
  onSaveDefaults?: () => void;
  onResetToDefaults?: () => void;
  messages: AiMessage[];
  isGenerating: boolean;
  chatMode: AiChatMode;
  onChatModeChange: (mode: AiChatMode) => void;
  executionMode: AiExecutionMode;
  settings: AiAssistantSettings;
  onModeChange: (mode: AiExecutionMode) => void;
  // Nova: full server list (from bootstrap) for the extra-targets picker.
  // Optional because the panel is usable without multi-target granting.
  availableServers?: ReadonlyArray<{ id: number; name: string; host: string; server_type?: string | null }>;
  currentServerId?: number;
}

const quickPrompts = ["Объясни вывод", "Предложи команду", "Проверь синтаксис", "Что означает ошибка"];

const modeConfig: Record<AiExecutionMode, { icon: typeof Zap; label: string; desc: string }> = {
  auto: { icon: Wand2, label: "Авто", desc: "AI сам решает" },
  fast: { icon: Zap, label: "Fast", desc: "Быстрый ответ без лишних шагов" },
  step: { icon: Footprints, label: "Step", desc: "Пошаговый и более подробный режим" },
  // Nova: ReAct agent — no pre-plan, picks tools one at a time. Can
  // operate on extra servers (see settings → Agent → Extra targets).
  agent: {
    icon: Sparkles,
    label: "Nova",
    desc: "Агент: сам выбирает инструменты, делает todo-лист, может работать с несколькими серверами",
  },
};

const chatModeConfig: Record<AiChatMode, { label: string; desc: string }> = {
  ask: {
    label: "Ask",
    desc: "Объясняет и предлагает команды. Запуск только после вашего подтверждения.",
  },
  agent: {
    label: "Agent",
    desc: "Сразу запускает безопасные команды в терминале. Опасные действия требуют подтверждения.",
  },
};

function normalizePatternList(text: string) {
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const row of text.replace(/\r/g, "").split("\n")) {
    const line = row.trim();
    if (!line) continue;
    const key = line.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push(line);
  }
  return normalized.slice(0, 50);
}

function isExecutedCommandStatus(status?: AiCommand["status"]) {
  return status === "running" || status === "done" || status === "skipped" || status === "cancelled";
}

// Which execution modes are currently exposed to end users in the
// segmented control. Keep `modeConfig` comprehensive so we can re-enable
// hidden modes without duplicating labels/descriptions — just update
// this list. The `useEffect` in `AiPanel` normalises any out-of-list
// value persisted in settings back into the first exposed mode.
const EXPOSED_EXECUTION_MODES: AiExecutionMode[] = ["fast", "agent"];

// Linear-style segmented control: flat neutral surface, active segment
// raised with a subtle inner shadow + 1px hairline ring. No per-item
// colour — the active state is conveyed by surface contrast alone.
function ModeSelector({ mode, onChange }: { mode: AiExecutionMode; onChange: (mode: AiExecutionMode) => void }) {
  return (
    <div className="inline-flex items-center rounded-md border border-border/70 bg-background/40 p-0.5">
      {EXPOSED_EXECUTION_MODES.map((item) => {
        const cfg = modeConfig[item];
        const active = item === mode;
        return (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            title={cfg.desc}
            aria-pressed={active}
            className={`inline-flex items-center gap-1 rounded-[5px] px-2 py-1 text-[11px] font-medium transition-colors ${
              active
                ? "bg-secondary/80 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--border))]"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <cfg.icon className="h-3 w-3 opacity-80" />
            {cfg.label}
          </button>
        );
      })}
    </div>
  );
}

function ChatModeSelector({
  mode,
  onChange,
}: {
  mode: AiChatMode;
  onChange: (mode: AiChatMode) => void;
}) {
  return (
    <div className="inline-flex items-center rounded-md border border-border/70 bg-background/40 p-0.5">
      {(["ask", "agent"] as AiChatMode[]).map((item) => {
        const cfg = chatModeConfig[item];
        const active = item === mode;
        return (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            title={cfg.desc}
            aria-pressed={active}
            className={`rounded-[5px] px-2.5 py-1 text-[11px] font-medium transition-colors ${
              active
                ? "bg-secondary/80 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--border))]"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {cfg.label}
          </button>
        );
      })}
    </div>
  );
}

function CodeBlock({ children, language }: { children: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="relative my-2 overflow-hidden rounded-md border border-border">
      <div className="flex items-center justify-between bg-secondary px-3 py-1.5 text-xs text-muted-foreground">
        <span>{language || "code"}</span>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard.writeText(children);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          }}
          className="transition-colors hover:text-foreground"
          aria-label="Copy code"
        >
          {copied ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
        </button>
      </div>
      <pre className="overflow-x-auto bg-[hsl(220,25%,5%)] px-4 py-3 text-[12px] leading-6 text-foreground/85">
        <code className="font-mono">{children}</code>
      </pre>
    </div>
  );
}

function MD({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        code: ({ className, children }) => {
          const match = /language-(\w+)/.exec(className || "");
          const code = String(children).replace(/\n$/, "");
          if (match || code.includes("\n")) return <CodeBlock language={match?.[1]}>{code}</CodeBlock>;
          // Inline code reads as a semantic highlight, not an accent —
          // foreground text on a subtle surface keeps prose legible.
          return <code className="rounded border border-border/40 bg-muted/80 px-1 py-0.5 text-[12px] font-mono text-foreground">{children}</code>;
        },
        p: ({ children }) => <p className="mb-1.5 text-sm leading-relaxed last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="mb-1.5 list-disc space-y-0.5 pl-4 text-sm">{children}</ul>,
        ol: ({ children }) => <ol className="mb-1.5 list-decimal space-y-0.5 pl-4 text-sm">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        h1: ({ children }) => <h1 className="mb-1 text-sm font-bold text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-1 text-sm font-semibold text-foreground">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1 text-sm font-semibold text-foreground">{children}</h3>,
        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto rounded-lg border border-border">
            <table className="w-full border-collapse text-sm">{children}</table>
          </div>
        ),
        th: ({ children }) => <th className="border-b border-border bg-secondary/60 px-3 py-2 text-left font-semibold text-foreground">{children}</th>,
        td: ({ children }) => <td className="border-b border-border/40 px-3 py-1.5 text-secondary-foreground">{children}</td>,
        hr: () => <hr className="my-2 border-border" />,
        blockquote: ({ children }) => <blockquote className="my-2 border-l-2 border-primary/40 pl-3 text-sm italic text-muted-foreground">{children}</blockquote>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

/**
 * F2-5 / F2-8 risk badge — shown next to the command line. Clicking the badge
 * is not interactive; ``title`` provides the native tooltip listing
 * ``risk_reasons`` and the resolved reason message.
 */
function CmdRiskBadge({ command }: { command: AiCommand }) {
  const risk = useAiCommandRisk(command);
  // Don't render anything for safe commands without risk categories — keeps
  // the UI quiet on ``ls``/``pwd``/etc.
  if (risk.level === "safe" && risk.categories.length === 0 && risk.execMode !== "direct") {
    return null;
  }
  const showExecHint = risk.execMode === "direct" && risk.level === "safe";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
        showExecHint
          ? "border-border/60 bg-secondary/40 text-muted-foreground"
          : riskBadgeClass(risk.level)
      }`}
      title={risk.tooltip}
    >
      {showExecHint ? "DIRECT" : risk.label}
    </span>
  );
}

function CmdStatusBadge({ status, exit_code }: { status?: AiCommand["status"]; exit_code?: number }) {
  if (!status || status === "pending") {
    return <span className="rounded-md border border-border/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">ожидает</span>;
  }
  if (status === "running") {
    return (
      <span className="flex items-center gap-1 whitespace-nowrap rounded-md border border-warning/30 bg-warning/10 px-1.5 py-0.5 text-[11px] text-warning">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> выполняется
      </span>
    );
  }
  if (status === "done") {
    const ok = exit_code === 0 || exit_code === undefined;
    return (
      <span className={`flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] ${
        ok ? "border-success/30 bg-success/10 text-success" : "border-destructive/30 bg-destructive/10 text-destructive"
      }`}>
        {ok ? <CheckCircle2 className="h-2.5 w-2.5" /> : <AlertTriangle className="h-2.5 w-2.5" />}
        {ok ? "готово" : `ошибка (${exit_code})`}
      </span>
    );
  }
  if (status === "skipped" || status === "cancelled") {
    return <span className="px-1.5 py-0.5 text-[11px] text-muted-foreground/50 line-through">пропущено</span>;
  }
  if (status === "confirmed") {
    return <span className="rounded-md border border-info/30 bg-info/10 px-1.5 py-0.5 text-[11px] text-info">подтверждено</span>;
  }
  return null;
}

function CommandsMsg({
  msg,
  settings,
  onConfirm,
  onCancel,
  onExplainCommand,
}: {
  msg: AiMessage;
  settings: AiAssistantSettings;
  onConfirm?: (id: number) => void;
  onCancel?: (id: number) => void;
  onExplainCommand?: (cmd: AiCommand) => void;
}) {
  const allCommands = msg.commands || [];
  const visibleCommands = allCommands.filter((command) => {
    const isExecuted = isExecutedCommandStatus(command.status);
    if (isExecuted) return settings.showExecutedCommands;
    return settings.showSuggestedCommands;
  });
  const hiddenCount = allCommands.length - visibleCommands.length;

  return (
    <div className="w-full space-y-2">
      {msg.content ? (
        <div className="text-sm text-secondary-foreground">
          <MD content={msg.content} />
        </div>
      ) : null}

      {allCommands.length > 0 ? (
        visibleCommands.length > 0 ? (
          <div className="overflow-hidden rounded-xl border border-border">
            <div className="flex items-center gap-1.5 bg-secondary/40 px-3 py-2 text-[11px] font-medium text-muted-foreground">
              <TerminalIcon className="h-3 w-3" /> Команды ({visibleCommands.length}/{allCommands.length})
            </div>
            <div className="divide-y divide-border/40">
              {visibleCommands.map((cmd) => (
                <div key={cmd.id} className="space-y-1.5 px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <code className="flex-1 break-all font-mono text-xs leading-relaxed text-foreground">{cmd.cmd}</code>
                    <div className="flex shrink-0 items-center gap-1 pt-0.5">
                      {/* F2-5 / F2-8: expose risk categories / exec_mode hint */}
                      <CmdRiskBadge command={cmd} />
                      <CmdStatusBadge status={cmd.status} exit_code={cmd.exit_code} />
                    </div>
                  </div>
                  {cmd.why ? <p className="text-xs text-muted-foreground">{cmd.why}</p> : null}
                  {cmd.direct_output ? (
                    // F2-8 v2: the command ran outside the interactive PTY,
                    // so we render its captured output here — otherwise the
                    // user would not see it anywhere.
                    <pre className="max-h-48 overflow-auto rounded-md border border-border/60 bg-secondary/40 px-2 py-1.5 font-mono text-[11px] leading-relaxed text-muted-foreground">
                      {cmd.direct_output}
                    </pre>
                  ) : null}
                  {/* A6: explain-output affordance — visible once the command has finished.
                      We only show the button if the parent supplied a handler and the
                      command actually ran (exit_code is defined). */}
                  {onExplainCommand && cmd.status === "done" && typeof cmd.exit_code === "number" ? (
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 gap-1 px-2 text-[11px]"
                        disabled={!!cmd.explaining}
                        onClick={() => onExplainCommand(cmd)}
                      >
                        {cmd.explaining ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <HelpCircle className="h-3 w-3" />
                        )}
                        {cmd.explanation ? "Переобъяснить" : "Объяснить"}
                      </Button>
                    </div>
                  ) : null}
                  {cmd.explanation ? (
                    <div className="rounded-md border border-border/50 bg-secondary/20 px-2 py-1.5 text-[12px] leading-relaxed text-secondary-foreground">
                      <ReactMarkdown>{cmd.explanation}</ReactMarkdown>
                    </div>
                  ) : null}
                  {cmd.requires_confirm && (!cmd.status || cmd.status === "pending") ? (
                    <div className="flex gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-6 border-success/50 px-2 text-xs text-success hover:bg-success/10"
                        onClick={() => onConfirm?.(cmd.id)}
                      >
                        <Check className="mr-1 h-3 w-3" /> Выполнить
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-6 border-destructive/40 px-2 text-xs text-destructive/80 hover:bg-destructive/10"
                        onClick={() => onCancel?.(cmd.id)}
                      >
                        <X className="mr-1 h-3 w-3" /> Пропустить
                      </Button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
            {hiddenCount > 0 ? (
              <div className="border-t border-border/40 bg-secondary/20 px-3 py-2 text-[11px] text-muted-foreground">
                {hiddenCount} команд скрыто настройками видимости.
              </div>
            ) : null}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border bg-secondary/20 px-3 py-2 text-sm text-muted-foreground">
            Команды скрыты настройками видимости для этого чата.
          </div>
        )
      ) : null}
    </div>
  );
}

function ReportMsg({ msg }: { msg: AiMessage }) {
  const [expanded, setExpanded] = useState(true);
  const cfg = {
      ok: {
        border: "border-success/40",
        header: "bg-success/10 text-success",
        Icon: CheckCircle2,
        label: "Выполнено успешно",
      },
      warning: {
        border: "border-warning/40",
        header: "bg-warning/10 text-warning",
        Icon: AlertTriangle,
        label: "Выполнено с предупреждениями",
      },
      error: {
        border: "border-destructive/40",
        header: "bg-destructive/10 text-destructive",
        Icon: AlertTriangle,
        label: "Ошибки при выполнении",
      },
    }[msg.reportStatus || "ok"];

  return (
    <div className={`overflow-hidden rounded-2xl border ${cfg.border}`}>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className={`flex w-full items-center justify-between gap-2 px-4 py-3 text-sm font-medium transition-colors hover:opacity-90 ${cfg.header}`}
      >
        <div className="flex items-center gap-2">
          <cfg.Icon className="h-4 w-4" />
          <FileText className="h-3.5 w-3.5 opacity-60" />
          <span>{cfg.label}</span>
        </div>
        {expanded ? <ChevronUp className="h-3.5 w-3.5 opacity-60" /> : <ChevronDown className="h-3.5 w-3.5 opacity-60" />}
      </button>
      {expanded ? (
        <div className="report-content px-4 py-3 text-sm text-secondary-foreground">
          <MD content={msg.content} />
        </div>
      ) : null}
    </div>
  );
}

function ProgressMsg({ msg }: { msg: AiMessage }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border">
      <div className="flex items-center justify-between bg-secondary/30 px-4 py-3">
        <div className="min-w-0 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-warning" />
          <code className="truncate font-mono">{msg.progressCmd}</code>
        </div>
        <span className="ml-2 flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground">
          <Clock className="h-3 w-3" />
          {msg.progressElapsed}s
        </span>
      </div>
      {msg.progressTail ? (
        <div className="max-h-24 overflow-y-auto whitespace-pre-wrap break-all bg-terminal-bg/60 px-4 py-2 text-[11px] font-mono text-muted-foreground/80">
          {msg.progressTail}
        </div>
      ) : null}
    </div>
  );
}

// ── Nova agent message renderers ────────────────────────────────────────

// Compact Timeline: узкая однострочная шапка, без большой карточки.
// Показывает primary + extras бейджами; goal показываем tooltip'ом.
// Run-started marker — intentionally subdued so it reads as a
// boundary, not a hero banner. "Nova" is the brand word, primary
// target is a muted monospace chip.
function AgentStartMsg({ msg }: { msg: AiMessage }) {
  const extras = msg.agentExtras ?? [];
  return (
    <div className="space-y-2">
      <div
        className="flex flex-wrap items-center gap-1.5 rounded-md border border-border/50 bg-background/40 px-2.5 py-1.5 text-[11px] text-muted-foreground"
        title={msg.content || undefined}
      >
        <Sparkles className="h-3 w-3 text-primary/80" />
        <span className="font-medium text-foreground">Nova</span>
        <span className="opacity-40">·</span>
        <ServerIcon className="h-2.5 w-2.5 opacity-60" />
        <code className="rounded border border-border/50 bg-secondary/40 px-1 py-0 font-mono text-foreground/80">
          {msg.agentPrimary || "primary"}
        </code>
        {extras.length > 0 ? (
          <>
            <span className="opacity-40">+</span>
            {extras.slice(0, 3).map((name) => (
              <code
                key={name}
                className="rounded border border-border/50 bg-secondary/40 px-1 py-0 font-mono text-[10px] text-muted-foreground"
              >
                {name}
              </code>
            ))}
            {extras.length > 3 ? (
              <span className="text-[10px] text-muted-foreground">+{extras.length - 3}</span>
            ) : null}
          </>
        ) : null}
      </div>
      <NovaContextCard context={msg.agentContext} />
    </div>
  );
}

// Compact inline "thinking" line — barely noticeable by default, click to
// expand. Meant to read like a subtle side-note between tool rows, not a
// full-width card. Keeps the timeline dense.
function AgentThinkingMsg({ msg }: { msg: AiMessage }) {
  const [expanded, setExpanded] = useState(false);
  if (!msg.content.trim()) return null;
  const preview = msg.content.split("\n")[0].slice(0, 120);
  return (
    <button
      type="button"
      onClick={() => setExpanded((v) => !v)}
      className="group flex w-full items-start gap-1.5 px-2 py-0.5 text-left text-[11px] italic leading-snug text-muted-foreground/70 transition-colors hover:text-foreground"
      title={expanded ? undefined : msg.content}
    >
      <Brain className="h-3 w-3 mt-0.5 shrink-0 opacity-60" />
      <span className={`min-w-0 flex-1 ${expanded ? "whitespace-pre-wrap" : "truncate"}`}>
        {expanded ? msg.content : preview}
      </span>
    </button>
  );
}

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
function AgentToolMsg({ msg }: { msg: AiMessage }) {
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
        className={`flex w-full items-center gap-1.5 px-2 py-1 text-left text-[11px] transition-colors hover:bg-secondary/30 ${
          errorState ? "bg-destructive/5 text-destructive" : "bg-secondary/15 text-foreground"
        }`}
        title={cmdPreview || tool}
      >
        {statusIcon}
        <Wrench className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{tool}</span>
        {target ? (
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground/80">·{target}</span>
        ) : null}
        {cmdPreview ? (
          <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-foreground">
            {cmdPreview}
          </code>
        ) : (
          <span className="flex-1" />
        )}
        {nonZeroExit ? (
          <span
            className="shrink-0 rounded border border-destructive/40 bg-destructive/10 px-1 font-mono text-[9px] font-semibold uppercase tracking-wide text-destructive"
            title={`exit code ${exitCode}`}
          >
            exit {exitCode}
          </span>
        ) : null}
        {duration ? (
          <span className="shrink-0 text-[10px] text-muted-foreground">{duration}</span>
        ) : null}
        {expanded ? (
          <ChevronUp className="h-3 w-3 shrink-0 opacity-40" />
        ) : (
          <ChevronDown className="h-3 w-3 shrink-0 opacity-40" />
        )}
      </button>
      {expanded ? (
        <div className="space-y-1.5 border-t border-border/30 bg-background/40 px-2 py-1.5 text-[11px]">
          {Object.keys(args).length > 0 ? (
            <details className="group">
              <summary className="cursor-pointer text-[10px] text-muted-foreground hover:text-foreground">
                аргументы ({Object.keys(args).length})
              </summary>
              <pre className="mt-1 max-h-32 overflow-auto rounded bg-secondary/40 p-1.5 font-mono text-[10px] leading-snug text-muted-foreground">
                {JSON.stringify(args, null, 2)}
              </pre>
            </details>
          ) : null}
          {output ? (
            <pre className="max-h-80 overflow-auto rounded border border-border/30 bg-terminal-bg/80 p-1.5 font-mono text-[10px] leading-snug text-secondary-foreground">
              {output}
            </pre>
          ) : null}
          {!output && outputLines.length === 0 && running ? (
            <p className="text-[10px] italic text-muted-foreground">выполняется…</p>
          ) : null}
          {msg.agentToolError ? (
            <p className="rounded border border-destructive/30 bg-destructive/5 px-1.5 py-1 text-[10px] text-destructive">
              {msg.agentToolError}
            </p>
          ) : null}
        </div>
      ) : output ? (
        // Collapsed inline preview — up to 2 lines of output so the user
        // sees immediate feedback without expanding.
        <div className="border-t border-border/20 bg-background/30 px-2 py-0.5 font-mono text-[10px] leading-snug text-muted-foreground/80">
          <div className="max-h-8 overflow-hidden">
            {outputLines.slice(0, 2).map((line, idx) => (
              <div key={idx} className="truncate">
                {line || "\u00a0"}
              </div>
            ))}
          </div>
          {outputLines.length > 2 ? (
            <div className="text-[9px] italic text-muted-foreground/60">
              +{outputLines.length - 2} строк — кликните чтобы раскрыть
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function AgentTodoMsg({ msg }: { msg: AiMessage }) {
  const todos = msg.agentTodos || [];
  if (todos.length === 0) return null;
  const completed = todos.filter((t) => t.status === "completed").length;
  return (
    <div className="overflow-hidden rounded-md border border-border/60 bg-card/70">
      <div className="flex items-center gap-2 border-b border-border/50 px-3 py-1.5 text-[11px] font-medium text-foreground">
        <ListTodo className="h-3 w-3 text-muted-foreground" />
        <span>Todo</span>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {completed}/{todos.length}
        </span>
      </div>
      <ul className="space-y-1 px-3 py-2 text-[12px]">
        {todos.map((t) => {
          const icon =
            t.status === "completed" ? (
              <CheckCircle2 className="h-3 w-3 shrink-0 text-success" />
            ) : t.status === "in_progress" ? (
              <Loader2 className="h-3 w-3 shrink-0 animate-spin text-warning" />
            ) : t.status === "cancelled" ? (
              <X className="h-3 w-3 shrink-0 text-muted-foreground" />
            ) : (
              <CircleDot className="h-3 w-3 shrink-0 text-muted-foreground" />
            );
          return (
            <li
              key={t.id}
              className={`flex items-start gap-2 ${
                t.status === "completed"
                  ? "text-muted-foreground line-through"
                  : t.status === "cancelled"
                    ? "text-muted-foreground/60 line-through"
                    : "text-foreground"
              }`}
            >
              <span className="pt-0.5">{icon}</span>
              <span className="min-w-0 break-words">{t.content}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AgentStoppedMsg({ msg }: { msg: AiMessage }) {
  const reasonLabel =
    {
      max_iterations: "лимит шагов исчерпан",
      total_timeout: "превышено общее время",
      llm_timeout: "LLM не ответил вовремя",
      llm_error: "ошибка LLM",
      user_stop: "остановлено пользователем",
      fatal_tool_error: "критическая ошибка инструмента",
      cancelled: "отменено",
    }[msg.agentStopReason || ""] || msg.agentStopReason || "остановлен";
  return (
    <div className="flex items-center gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-[12px] text-warning">
      <Pause className="h-3.5 w-3.5" />
      <span>Nova остановлен: {reasonLabel}</span>
    </div>
  );
}

function RecoveryMsg({ msg }: { msg: AiMessage }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-warning/30 bg-warning/5">
      <div className="flex items-center gap-2 bg-warning/10 px-4 py-3 text-sm font-medium text-warning">
        <RotateCcw className="h-4 w-4" /> Автоисправление
      </div>
      <div className="space-y-2 px-4 py-3 text-xs">
        <div className="flex items-start gap-2">
          <span className="shrink-0 pt-0.5 font-medium text-muted-foreground">Было:</span>
          <code className="break-all rounded bg-destructive/5 px-2 py-0.5 font-mono text-destructive/80">{msg.recoveryOriginal}</code>
        </div>
        <div className="flex items-start gap-2">
          <span className="shrink-0 pt-0.5 font-medium text-muted-foreground">Стало:</span>
          <code className="break-all rounded bg-success/5 px-2 py-0.5 font-mono text-success">{msg.recoveryNew}</code>
        </div>
        {msg.recoveryWhy ? <p className="pt-0.5 text-muted-foreground">{msg.recoveryWhy}</p> : null}
      </div>
    </div>
  );
}

// Timeline wrapper — renders a vertical line + coloured dot on the left
// of an agent message so consecutive agent rows read as a connected
// sequence. Non-agent messages break the line naturally because they
// don't use this wrapper.
function TimelineRow({
  children,
  dot,
  first = false,
  last = false,
}: {
  children: React.ReactNode;
  dot: "start" | "think" | "tool-ok" | "tool-err" | "tool-run" | "todo" | "stop";
  first?: boolean;
  last?: boolean;
}) {
  const dotClass = {
    start: "bg-primary",
    think: "bg-muted-foreground/40",
    "tool-ok": "bg-success",
    "tool-err": "bg-destructive",
    "tool-run": "bg-warning animate-pulse",
    todo: "bg-primary/70",
    stop: "bg-warning",
  }[dot];
  return (
    <div className="relative pl-4">
      {/* Two separate line segments around the dot so the timeline
          bridges the ``space-y-3`` gap between messages (the default
          sibling margin would otherwise cut the line). Segments are
          omitted on first / last messages so the line doesn't extend
          past the sequence. */}
      {!first ? (
        <span
          className="absolute left-[5px] -top-3 h-[18px] w-px bg-muted-foreground/30"
          aria-hidden="true"
        />
      ) : null}
      {!last ? (
        <span
          className="absolute left-[5px] top-[14px] -bottom-3 w-px bg-muted-foreground/30"
          aria-hidden="true"
        />
      ) : null}
      <span
        className={`absolute left-[2px] top-1.5 h-2 w-2 rounded-full ring-2 ring-background ${dotClass}`}
        aria-hidden="true"
      />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function dotKindForMsg(msg: AiMessage): "start" | "think" | "tool-ok" | "tool-err" | "tool-run" | "todo" | "stop" {
  const type = msg.type || "text";
  if (type === "agent_start") return "start";
  if (type === "agent_thinking") return "think";
  if (type === "agent_todo") return "todo";
  if (type === "agent_stopped") return "stop";
  if (type === "agent_tool") {
    const running = msg.agentToolOutput === undefined && msg.agentToolError === undefined;
    if (running) return "tool-run";
    // Non-zero exit code is a failure even if the tool itself ran fine.
    const nonZeroExit =
      typeof msg.agentToolExitCode === "number" && msg.agentToolExitCode !== 0;
    return msg.agentToolOk !== false && !nonZeroExit ? "tool-ok" : "tool-err";
  }
  return "think";
}

function MsgRenderer({
  msg,
  settings,
  onConfirm,
  onCancel,
  onReply,
  onExplainCommand,
  isFirstAgent,
  isLastAgent,
}: {
  msg: AiMessage;
  settings: AiAssistantSettings;
  onConfirm?: (id: number) => void;
  onCancel?: (id: number) => void;
  onReply?: (qId: string, text: string) => void;
  onExplainCommand?: (cmd: AiCommand) => void;
  isFirstAgent?: boolean;
  isLastAgent?: boolean;
}) {
  const type = msg.type || "text";

  if (type === "commands") return <div className="w-full"><CommandsMsg msg={msg} settings={settings} onConfirm={onConfirm} onCancel={onCancel} onExplainCommand={onExplainCommand} /></div>;
  if (type === "report") return <div className="w-full"><ReportMsg msg={msg} /></div>;
  if (type === "question") return <div className="w-full"><AiQuestionCard msg={msg} onReply={onReply} /></div>;
  if (type === "progress") return <div className="w-full"><ProgressMsg msg={msg} /></div>;
  if (type === "recovery") return <div className="w-full"><RecoveryMsg msg={msg} /></div>;

  // Agent messages share a vertical timeline on the left.
  if (type === "agent_start") return <div className="w-full"><TimelineRow dot="start" first={isFirstAgent} last={isLastAgent}><AgentStartMsg msg={msg} /></TimelineRow></div>;
  if (type === "agent_thinking") return <div className="w-full"><TimelineRow dot="think" first={isFirstAgent} last={isLastAgent}><AgentThinkingMsg msg={msg} /></TimelineRow></div>;
  if (type === "agent_tool") return <div className="w-full"><TimelineRow dot={dotKindForMsg(msg)} first={isFirstAgent} last={isLastAgent}><AgentToolMsg msg={msg} /></TimelineRow></div>;
  if (type === "agent_todo") return <div className="w-full"><TimelineRow dot="todo" first={isFirstAgent} last={isLastAgent}><AgentTodoMsg msg={msg} /></TimelineRow></div>;
  if (type === "agent_stopped") return <div className="w-full"><TimelineRow dot="stop" first={isFirstAgent} last={isLastAgent}><AgentStoppedMsg msg={msg} /></TimelineRow></div>;

  if (msg.role === "user") {
    // Linear/Vercel style: no colored bubble. Right-aligned neutral
    // card with a thin left accent rail so the user's turn is
    // unmistakable without screaming colour at the operator.
    return (
      <div className="flex justify-end">
        <div className="relative max-w-[85%] rounded-md border border-border/60 bg-secondary/30 px-3 py-2 text-[13px] leading-relaxed text-foreground">
          <span
            aria-hidden="true"
            className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-primary/70"
          />
          <div className="pl-1.5">{msg.content}</div>
        </div>
      </div>
    );
  }

  if (msg.role === "system") {
    return (
      <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] text-destructive/90">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <div className="flex-1 leading-relaxed">{msg.content}</div>
      </div>
    );
  }

  // Assistant free-form reply — no chat-bubble tail, just a clean
  // document-like surface so prose and markdown read well.
  return (
    <div className="rounded-md border border-border/50 bg-card/60 px-3.5 py-2.5 text-[13px] leading-relaxed text-foreground">
      <MD content={msg.content} />
    </div>
  );
}

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2.5">
      <div className="px-0.5">
        <h4 className="text-[13px] font-semibold text-foreground">{title}</h4>
        <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{description}</p>
      </div>
      <div className="rounded-lg border border-border/50 bg-secondary/15 p-3">
        {children}
      </div>
    </section>
  );
}

function ToggleRow({
  title,
  description,
  checked,
  onCheckedChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-foreground">{title}</div>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}

function InputLabel({ children }: { children: ReactNode }) {
  return <label className="mb-1 block text-[11px] font-medium text-muted-foreground">{children}</label>;
}

export function AiPanel({
  onClose,
  onSend,
  onStop,
  onConfirm,
  onCancel,
  onReply,
  onClearChat,
  onGenerateReport,
  onClearMemory,
  onExplainCommand,
  onSettingsChange,
  onSaveDefaults,
  onResetToDefaults,
  messages,
  isGenerating,
  chatMode,
  onChatModeChange,
  executionMode,
  settings,
  onModeChange,
  availableServers,
  currentServerId,
}: AiPanelProps) {
  const [input, setInput] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  // Product decision: Ask/Agent are both exposed. Execution-mode is
  // restricted to Fast + Nova (agent) for now — Auto and Step are
  // hidden from the UI (see EXPOSED_EXECUTION_MODES) until they are
  // ready for users. If a saved setting picked auto/step, fall back
  // to fast so the segmented control still reflects the live mode.
  useEffect(() => {
    if (executionMode !== "fast" && executionMode !== "agent") {
      onModeChange("fast");
    }
  }, [executionMode, onModeChange]);

  // Sticky-todo logic: find the latest agent_todo message and show it
  // pinned to the top of the scroll area while an agent run is active
  // (between agent_start and agent_stopped / agent_done). After the run
  // finishes, we stop pinning so the chronological position in the
  // timeline remains visible during scroll-back.
  const { stickyTodo, stickyTodoId } = useMemo(() => {
    let runActive = false;
    let latestTodo: AiMessage | null = null;
    for (let i = 0; i < messages.length; i += 1) {
      const t = messages[i].type;
      if (t === "agent_start") {
        runActive = true;
        latestTodo = null; // reset — each run has its own todo
      } else if (t === "agent_stopped") {
        runActive = false;
      } else if (t === "agent_todo") {
        latestTodo = messages[i];
      }
    }
    return {
      stickyTodo: runActive ? latestTodo : null,
      stickyTodoId: runActive ? latestTodo?.id : null,
    };
  }, [messages]);

  const whitelistText = useMemo(() => settings.whitelistPatterns.join("\n"), [settings.whitelistPatterns]);
  const blacklistText = useMemo(() => settings.blacklistPatterns.join("\n"), [settings.blacklistPatterns]);
  const canGenerateReport = messages.length > 0 && !isGenerating;

  const updateSettings = (patch: Partial<AiAssistantSettings>) => {
    onSettingsChange({
      ...settings,
      ...patch,
      whitelistPatterns: patch.whitelistPatterns ? [...patch.whitelistPatterns] : [...settings.whitelistPatterns],
      blacklistPatterns: patch.blacklistPatterns ? [...patch.blacklistPatterns] : [...settings.blacklistPatterns],
    });
  };

  const handleSend = (text?: string) => {
    const message = (text || input).trim();
    if (!message) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    onSend(message);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleInput = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
    event.target.style.height = "auto";
    event.target.style.height = `${Math.min(event.target.scrollHeight, 120)}px`;
  };

  return (
    <>
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-hidden rounded-xl border-border/60">
          <DialogHeader className="pb-0">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Settings2 className="h-4 w-4 text-muted-foreground" />
              Настройки AI
            </DialogTitle>
            <DialogDescription className="text-[11px]">
              Параметры применяются сразу к текущему чату.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="max-h-[calc(85vh-8rem)] space-y-5 overflow-y-auto py-2">
            <SettingsSection
              title="Режим"
              description="Как AI ведёт диалог и исполняет команды."
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[13px] text-foreground">Чат</span>
                  <ChatModeSelector mode={chatMode} onChange={onChatModeChange} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[13px] text-foreground">Стиль</span>
                  <ModeSelector mode={executionMode} onChange={onModeChange} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[13px] text-foreground">Авто-отчёт</span>
                  <select
                    value={settings.autoReport}
                    onChange={(event) => updateSettings({ autoReport: event.target.value === "on" || event.target.value === "off" ? event.target.value : "auto" })}
                    className="h-8 rounded-md border border-border bg-background px-2.5 text-xs text-foreground focus:border-primary focus:outline-none"
                  >
                    <option value="auto">Auto</option>
                    <option value="on">Всегда On</option>
                    <option value="off">Всегда Off</option>
                  </select>
                </div>
              </div>
            </SettingsSection>

            <SettingsSection
              title="Память"
              description="Контекст между запросами и управление историей."
            >
              <div className="space-y-2">
                <ToggleRow
                  title="Сохранять контекст"
                  description="AI помнит предыдущие запросы в рамках сессии."
                  checked={settings.memoryEnabled}
                  onCheckedChange={(checked) => updateSettings({ memoryEnabled: checked })}
                />

                <div className="flex items-center justify-between gap-3 py-1.5">
                  <div>
                    <div className="text-[13px] font-medium text-foreground">TTL памяти</div>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">Количество запросов (1–20)</p>
                  </div>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={settings.memoryTtlRequests}
                    disabled={!settings.memoryEnabled}
                    onChange={(event) => updateSettings({ memoryTtlRequests: Math.max(1, Math.min(20, Number(event.target.value || 1))) })}
                    className="h-8 w-16 rounded-md border border-border bg-background px-2.5 text-center text-xs text-foreground focus:border-primary focus:outline-none disabled:opacity-40"
                  />
                </div>

                <div className="flex items-center justify-between gap-3 pt-1">
                  <span className="text-[13px] text-foreground">Очистить память</span>
                  <Button type="button" variant="outline" size="sm" onClick={onClearMemory} className="h-7 gap-1.5 text-xs">
                    <Trash2 className="h-3 w-3" />
                    Очистить
                  </Button>
                </div>
              </div>
            </SettingsSection>

            <SettingsSection
              title="Безопасность"
              description="Контроль опасных команд и ограничение допустимых операций."
            >
              <div className="space-y-2">
                <ToggleRow
                  title="Подтверждать опасные"
                  description="Требовать ручное подтверждение для опасных операций."
                  checked={settings.confirmDangerousCommands}
                  onCheckedChange={(checked) => updateSettings({ confirmDangerousCommands: checked })}
                />
                <ToggleRow
                  title="Dry-run режим"
                  description="AI показывает, что выполнило бы, но не трогает сервер."
                  checked={settings.dryRun}
                  onCheckedChange={(checked) => updateSettings({ dryRun: checked })}
                />

                <div className="grid gap-2.5 pt-1 md:grid-cols-2">
                  <div>
                    <InputLabel>Whitelist</InputLabel>
                    <textarea
                      value={whitelistText}
                      onChange={(event) => updateSettings({ whitelistPatterns: normalizePatternList(event.target.value) })}
                      rows={4}
                      placeholder={"sudo systemctl\nre:^docker\\s+ps"}
                      className="w-full rounded-md border border-border bg-background px-2.5 py-2 font-mono text-[11px] text-foreground placeholder:text-muted-foreground/50 focus:border-primary focus:outline-none"
                    />
                  </div>
                  <div>
                    <InputLabel>Blocklist</InputLabel>
                    <textarea
                      value={blacklistText}
                      onChange={(event) => updateSettings({ blacklistPatterns: normalizePatternList(event.target.value) })}
                      rows={4}
                      placeholder={"rm -rf /\nshutdown\nre:^mkfs"}
                      className="w-full rounded-md border border-border bg-background px-2.5 py-2 font-mono text-[11px] text-foreground placeholder:text-muted-foreground/50 focus:border-primary focus:outline-none"
                    />
                  </div>
                </div>
              </div>
            </SettingsSection>

            {/* Nova: extra-target picker — only makes sense when the
                 agent mode is selected; render it always so the user
                 can prepare the list before switching to Nova. */}
            <SettingsSection
              title="Nova: дополнительные серверы"
              description="Разрешить агенту работать с другими серверами в этой сессии. Только те, к которым у вас уже есть доступ. Вступает в силу при следующем запросе в Nova-режиме."
            >
              {(() => {
                const others = (availableServers || []).filter(
                  (s) => s.id !== currentServerId,
                );
                if (others.length === 0) {
                  return (
                    <p className="text-[11px] text-muted-foreground">
                      Нет других доступных серверов.
                    </p>
                  );
                }
                const selected = new Set(settings.extraTargetServerIds);
                const toggle = (id: number) => {
                  const next = new Set(selected);
                  if (next.has(id)) {
                    next.delete(id);
                  } else {
                    if (next.size >= 10) return; // Nova hard cap: 10 extras
                    next.add(id);
                  }
                  updateSettings({ extraTargetServerIds: Array.from(next) });
                };
                return (
                  <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                    {others.map((srv) => (
                      <label
                        key={srv.id}
                        className={`flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-[12px] transition-colors ${
                          selected.has(srv.id)
                            ? "border-primary/40 bg-primary/5 text-foreground"
                            : "border-border/40 bg-transparent text-muted-foreground hover:bg-secondary/30"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selected.has(srv.id)}
                          onChange={() => toggle(srv.id)}
                          className="h-3 w-3 accent-primary"
                        />
                        <span className="truncate font-medium">{srv.name}</span>
                        <span className="truncate text-[10px] text-muted-foreground">
                          {srv.host}
                        </span>
                        {selected.has(srv.id) ? (
                          <span className="ml-auto rounded border border-primary/30 bg-primary/10 px-1 py-0 font-mono text-[9px] text-primary">
                            srv-{srv.id}
                          </span>
                        ) : null}
                      </label>
                    ))}
                  </div>
                );
              })()}
            </SettingsSection>

            <NovaContextSettings settings={settings} onChange={updateSettings} />

            <SettingsSection
              title="Отображение"
              description="Какие элементы показывать в чате."
            >
              <div className="space-y-1">
                <ToggleRow
                  title="Предлагаемые команды"
                  description="Показывать команды в статусе pending."
                  checked={settings.showSuggestedCommands}
                  onCheckedChange={(checked) => updateSettings({ showSuggestedCommands: checked })}
                />
                <ToggleRow
                  title="Выполненные команды"
                  description="Показывать done/skipped/cancelled команды."
                  checked={settings.showExecutedCommands}
                  onCheckedChange={(checked) => updateSettings({ showExecutedCommands: checked })}
                />
              </div>
            </SettingsSection>
          </DialogBody>

          <DialogFooter className="gap-2 pt-0">
            <Button type="button" variant="ghost" size="sm" onClick={onResetToDefaults} className="gap-1.5 text-xs text-muted-foreground">
              <RotateCcw className="h-3 w-3" />
              Сбросить
            </Button>
            <Button type="button" size="sm" onClick={onSaveDefaults} className="gap-1.5 text-xs">
              <Check className="h-3 w-3" />
              Сохранить глобально
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="flex h-full flex-col bg-card">
        {/* Header — neutral status dot + workspace label. No loud pills. */}
        <div className="shrink-0 border-b border-border px-3.5 py-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-md border border-border/50 bg-background/60">
                <Bot className="h-3 w-3 text-muted-foreground" />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-medium text-foreground">Assistant</span>
                <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <span
                    aria-hidden="true"
                    className={`h-1.5 w-1.5 rounded-full ${
                      isGenerating
                        ? "bg-warning animate-pulse"
                        : "bg-success"
                    }`}
                  />
                  {isGenerating ? "думает…" : "готов"}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-0.5">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                  onClick={() => setSettingsOpen(true)}
                title="Настройки"
                aria-label="AI settings"
              >
                <Settings2 className="h-3.5 w-3.5" />
              </Button>

              {isGenerating ? (
                <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 text-warning hover:bg-warning/10" onClick={onStop} title="Стоп" aria-label="Stop">
                  <Square className="h-3.5 w-3.5" />
                </Button>
              ) : null}

              {messages.length > 0 ? (
                <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive" onClick={onClearChat} title="Очистить" aria-label="Clear">
                  <Trash2 className="h-3 w-3" />
                </Button>
              ) : null}

              <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground" onClick={onClose} aria-label="Close">
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>

        {/* Compact mode bar — chat behaviour (Ask/Agent) on the left,
            execution style (Fast/Nova) on the right. Dry-run badge sits
            between them only when the safety toggle is on. */}
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border/50 px-3.5 py-2">
          <ChatModeSelector mode={chatMode} onChange={onChatModeChange} />
          <div className="flex items-center gap-1.5">
            {settings.dryRun ? (
              <span className="inline-flex items-center rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warning">
                dry-run
              </span>
            ) : null}
            <ModeSelector mode={executionMode} onChange={onModeChange} />
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
          {stickyTodo ? (
            <div className="sticky top-0 z-10 -mx-3 -mt-3 mb-1 border-b border-border/40 bg-background/95 px-3 pt-2 pb-2 backdrop-blur">
              <AgentTodoMsg msg={stickyTodo} />
            </div>
          ) : null}
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center space-y-5 py-8 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-md border border-border/60 bg-background/40">
                <Sparkles className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="space-y-1">
                <p className="text-[13px] font-medium text-foreground">Чем могу помочь?</p>
                <p className="text-[12px] leading-relaxed text-muted-foreground">
                  Задайте вопрос о терминале, сервере или текущем выводе.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-1.5">
                {quickPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => handleSend(prompt)}
                    className="rounded-md border border-border/60 bg-background/40 px-2.5 py-1.5 text-[12px] text-muted-foreground transition-colors hover:border-border hover:bg-secondary/60 hover:text-foreground"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            (() => {
              // Hide the currently-sticky todo from the inline list so
              // it doesn't render twice. Keep prev/next neighbour
              // detection correct by computing flags against the
              // filtered list.
              const visible = stickyTodoId
                ? messages.filter((m) => m.id !== stickyTodoId)
                : messages;
              return visible.map((message, idx) => {
                // Mark first/last in a contiguous run of agent messages
                // so the TimelineRow clips the vertical line at the ends.
                const isAgent = (message.type || "").startsWith("agent_");
                const prev = idx > 0 ? visible[idx - 1] : null;
                const next = idx < visible.length - 1 ? visible[idx + 1] : null;
                const prevIsAgent = !!prev && (prev.type || "").startsWith("agent_");
                const nextIsAgent = !!next && (next.type || "").startsWith("agent_");
                return (
                  <MsgRenderer
                    key={message.id}
                    msg={message}
                    settings={settings}
                    onConfirm={onConfirm}
                    onCancel={onCancel}
                    onReply={onReply}
                    onExplainCommand={onExplainCommand}
                    isFirstAgent={isAgent && !prevIsAgent}
                    isLastAgent={isAgent && !nextIsAgent}
                  />
                );
              });
            })()
          )}

          {isGenerating ? (
            <div className="flex items-center gap-2 px-0.5 py-1 text-[11px] text-muted-foreground">
              <div className="flex gap-1">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="h-1 w-1 animate-bounce rounded-full bg-muted-foreground/60"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </div>
              <span>думает…</span>
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>

        <div className="shrink-0 border-t border-border p-2">
          {messages.length > 0 ? (
            <div className="mb-1.5 flex items-center justify-between gap-2 rounded-md border border-border/50 bg-background/40 px-2.5 py-1.5">
              <span className="text-[11px] text-muted-foreground">Сформировать отчёт</span>
              <Button type="button" size="sm" variant="ghost" onClick={() => onGenerateReport?.(false)} disabled={!canGenerateReport} className="h-7 gap-1 px-2 text-[11px]">
                <FileText className="h-3 w-3" />
                Отчёт
              </Button>
            </div>
          ) : null}

          <div className="flex items-end gap-1.5">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              aria-label="AI message"
              placeholder="Сообщение… (Enter — отправить)"
              rows={1}
              className="min-h-[36px] max-h-[120px] flex-1 resize-none rounded-md border border-border bg-background/60 px-3 py-2 text-[13px] text-foreground transition-colors placeholder:text-muted-foreground/50 focus:border-primary/60 focus:bg-background focus:outline-none"
            />
            <Button
              type="button"
              size="sm"
              onClick={() => handleSend()}
              disabled={!input.trim() || isGenerating}
              className="h-[36px] w-[36px] shrink-0 rounded-md p-0"
              aria-label="Send"
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
