import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  FileText,
  Footprints,
  HelpCircle,
  Loader2,
  RotateCcw,
  Send,
  Settings2,
  Sparkles,
  Square,
  Terminal as TerminalIcon,
  Trash2,
  Wand2,
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
import type { AiAssistantSettings, AiChatMode, AiExecutionMode } from "./XTerminal";

export interface AiCommand {
  id: number;
  cmd: string;
  why: string;
  requires_confirm: boolean;
  status?: "pending" | "running" | "done" | "skipped" | "cancelled" | "confirmed";
  exit_code?: number;
  blocked?: boolean;
  reason?: "" | "forbidden" | "outside_allowlist" | "dangerous" | "ask_mode";
  risk_categories?: string[];
  risk_reasons?: string[];
  exec_mode?: "pty" | "direct";
  // F2-8 v2: output captured from a non-PTY channel. Only populated when
  // the command was executed via ``exec_mode=direct`` — we render it inline
  // in the AI panel because the terminal did not receive this output.
  direct_output?: string;
  // A6: human-readable explanation of the command + its output. Populated
  // when the user clicks "Объяснить" and the backend replies with
  // ``ai_explanation`` keyed by the same ``id``.
  explanation?: string;
  explaining?: boolean;
}

export interface AiMessage {
  id: string;
  role: "user" | "assistant" | "system";
  type?: "text" | "commands" | "report" | "question" | "progress" | "recovery";
  content: string;
  commands?: AiCommand[];
  mode?: "execute" | "answer" | "ask";
  reportStatus?: "ok" | "warning" | "error";
  qId?: string;
  question?: string;
  questionCmd?: string;
  questionExitCode?: number;
  progressCmd?: string;
  progressElapsed?: number;
  progressTail?: string;
  recoveryOriginal?: string;
  recoveryNew?: string;
  recoveryWhy?: string;
}

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
}

const quickPrompts = ["Объясни вывод", "Предложи команду", "Проверь синтаксис", "Что означает ошибка"];

const modeConfig: Record<AiExecutionMode, { icon: typeof Zap; label: string; desc: string; color: string }> = {
  auto: { icon: Wand2, label: "Авто", desc: "AI сам решает", color: "text-primary" },
  fast: { icon: Zap, label: "Fast", desc: "Быстрый ответ без лишних шагов", color: "text-warning" },
  step: { icon: Footprints, label: "Step", desc: "Пошаговый и более подробный режим", color: "text-success" },
};

const chatModeConfig: Record<AiChatMode, { label: string; desc: string; tone: string; badge: string }> = {
  ask: {
    label: "Ask",
    desc: "Объясняет и предлагает команды. Запуск только после вашего подтверждения.",
    tone: "text-primary",
    badge: "border-primary/30 bg-primary/10 text-primary",
  },
  agent: {
    label: "Agent",
    desc: "Сразу запускает безопасные команды в терминале. Опасные действия требуют подтверждения.",
    tone: "text-warning",
    badge: "border-warning/30 bg-warning/10 text-warning",
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

function ModeSelector({ mode, onChange }: { mode: AiExecutionMode; onChange: (mode: AiExecutionMode) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-xl border border-border/70 bg-secondary/60 p-1">
      {(["auto", "fast", "step"] as AiExecutionMode[]).map((item) => {
        const cfg = modeConfig[item];
        const active = item === mode;
        return (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            title={cfg.desc}
            className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
              active ? `bg-card text-foreground ${cfg.color}` : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <cfg.icon className="h-3 w-3" />
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
    <div className="flex items-center gap-1 rounded-xl border border-border/70 bg-secondary/60 p-1">
      {(["ask", "agent"] as AiChatMode[]).map((item) => {
        const cfg = chatModeConfig[item];
        const active = item === mode;
        return (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            title={cfg.desc}
            className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
              active ? `bg-card text-foreground ${cfg.tone}` : "text-muted-foreground hover:text-foreground"
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
          return <code className="rounded bg-muted px-1 py-0.5 text-xs font-mono text-primary">{children}</code>;
        },
        p: ({ children }) => <p className="mb-1.5 text-sm leading-relaxed last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="mb-1.5 list-disc space-y-0.5 pl-4 text-sm">{children}</ul>,
        ol: ({ children }) => <ol className="mb-1.5 list-decimal space-y-0.5 pl-4 text-sm">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        h1: ({ children }) => <h1 className="mb-1 text-sm font-bold text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-1 text-sm font-semibold text-primary">{children}</h2>,
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
                    <code className="flex-1 break-all font-mono text-xs leading-relaxed text-primary">{cmd.cmd}</code>
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
                    <div className="rounded-md border border-primary/30 bg-primary/5 px-2 py-1.5 text-[12px] leading-relaxed">
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

function QuestionMsg({ msg, onReply }: { msg: AiMessage; onReply?: (qId: string, text: string) => void }) {
  const [answer, setAnswer] = useState("");
  const [answered, setAnswered] = useState(false);

  const doReply = (text: string) => {
    if (!text.trim() || !msg.qId) return;
    onReply?.(msg.qId, text.trim());
    setAnswered(true);
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-primary/30 bg-primary/5">
      <div className="flex items-center gap-2 bg-primary/10 px-4 py-3 text-sm font-medium text-primary">
        <HelpCircle className="h-4 w-4" /> Вопрос от AI
      </div>
      <div className="space-y-2.5 px-4 py-3">
        <p className="text-sm text-foreground">{msg.question || msg.content}</p>
        {msg.questionCmd ? (
          <code className="block rounded-lg bg-muted px-2.5 py-1.5 text-xs font-mono text-muted-foreground">
            $ {msg.questionCmd}
          </code>
        ) : null}
        {msg.questionExitCode !== undefined ? <p className="text-xs text-muted-foreground">Код выхода: {msg.questionExitCode}</p> : null}
        {!answered ? (
          <div className="flex gap-2">
            <input
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") doReply(answer);
              }}
              placeholder="Ваш ответ..."
              aria-label="Reply to AI question"
              autoFocus
              className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground transition-colors placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <Button size="sm" className="h-9 px-3 text-xs" onClick={() => doReply(answer)} disabled={!answer.trim()}>
              <Send className="h-3 w-3" />
            </Button>
          </div>
        ) : (
          <p className="text-xs italic text-muted-foreground">Ответ отправлен</p>
        )}
      </div>
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

function MsgRenderer({
  msg,
  settings,
  onConfirm,
  onCancel,
  onReply,
  onExplainCommand,
}: {
  msg: AiMessage;
  settings: AiAssistantSettings;
  onConfirm?: (id: number) => void;
  onCancel?: (id: number) => void;
  onReply?: (qId: string, text: string) => void;
  onExplainCommand?: (cmd: AiCommand) => void;
}) {
  const type = msg.type || "text";

  if (type === "commands") return <div className="w-full"><CommandsMsg msg={msg} settings={settings} onConfirm={onConfirm} onCancel={onCancel} onExplainCommand={onExplainCommand} /></div>;
  if (type === "report") return <div className="w-full"><ReportMsg msg={msg} /></div>;
  if (type === "question") return <div className="w-full"><QuestionMsg msg={msg} onReply={onReply} /></div>;
  if (type === "progress") return <div className="w-full"><ProgressMsg msg={msg} /></div>;
  if (type === "recovery") return <div className="w-full"><RecoveryMsg msg={msg} /></div>;

  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2.5 text-sm leading-relaxed text-primary-foreground">
          {msg.content}
        </div>
      </div>
    );
  }

  if (msg.role === "system") {
    return (
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
        <div className="flex-1 rounded-2xl border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive/90">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] rounded-2xl rounded-tl-sm border border-border/60 bg-secondary/65 px-3.5 py-3 text-secondary-foreground">
        <MD content={msg.content} />
      </div>
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
}: AiPanelProps) {
  const [input, setInput] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  const whitelistText = useMemo(() => settings.whitelistPatterns.join("\n"), [settings.whitelistPatterns]);
  const blacklistText = useMemo(() => settings.blacklistPatterns.join("\n"), [settings.blacklistPatterns]);
  const canGenerateReport = messages.length > 0 && !isGenerating;
  const currentChatMode = chatModeConfig[chatMode];

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
              <Settings2 className="h-4 w-4 text-primary" />
              Настройки AI
            </DialogTitle>
            <DialogDescription className="text-[11px]">
              Параметры применяются сразу к текущему чату.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="max-h-[calc(85vh-8rem)] space-y-5 overflow-y-auto py-2">
            <SettingsSection
              title="Режим"
              description="Выберите как AI будет отвечать и выполнять команды."
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
        {/* Header */}
        <div className="shrink-0 border-b border-border px-3.5 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className={`flex h-7 w-7 items-center justify-center rounded-lg transition-colors ${
                isGenerating ? "bg-primary/15" : "bg-secondary"
              }`}>
                <Bot className="h-3.5 w-3.5 text-primary" />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium text-foreground">AI</span>
                <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${
                  isGenerating ? "border-warning/20 bg-warning/10 text-warning" : "border-success/20 bg-success/10 text-success"
                }`}>
                  {isGenerating ? "думает..." : "готов"}
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

        {/* Compact mode bar */}
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
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center space-y-4 py-8 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-secondary">
                <Sparkles className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">Чем могу помочь?</p>
                <p className="mt-1 text-sm text-muted-foreground">Задайте вопрос о терминале, сервере или текущем выводе.</p>
              </div>
              <div className="flex flex-wrap justify-center gap-1.5">
                {quickPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => handleSend(prompt)}
                    className="rounded-xl border border-border/60 px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-primary/30 hover:bg-secondary hover:text-foreground"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <MsgRenderer
                key={message.id}
                msg={message}
                settings={settings}
                onConfirm={onConfirm}
                onCancel={onCancel}
                onReply={onReply}
                onExplainCommand={onExplainCommand}
              />
            ))
          )}

          {isGenerating ? (
            <div className="flex justify-start">
              <div className="flex items-center gap-2.5 rounded-2xl rounded-tl-sm border border-border/60 bg-secondary/70 px-3.5 py-3">
                <div className="flex gap-0.5">
                  {[0, 150, 300].map((delay) => (
                    <span key={delay} className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary" style={{ animationDelay: `${delay}ms` }} />
                  ))}
                </div>
                <span className="text-xs text-muted-foreground">AI думает...</span>
              </div>
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>

        <div className="shrink-0 border-t border-border p-2">
          {messages.length > 0 ? (
            <div className="mb-1.5 flex items-center justify-between gap-2 rounded-xl border border-border/60 bg-secondary/20 px-2.5 py-2">
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
              placeholder="Сообщение... (Enter — отправить)"
              rows={1}
              className="min-h-[38px] max-h-[120px] flex-1 resize-none rounded-xl border border-border bg-secondary/40 px-3 py-2.5 text-[13px] text-foreground transition-colors placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none"
            />
            <Button type="button" size="sm" onClick={() => handleSend()} disabled={!input.trim() || isGenerating} className="h-[38px] w-[38px] shrink-0 p-0" aria-label="Send">
              <Send className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
