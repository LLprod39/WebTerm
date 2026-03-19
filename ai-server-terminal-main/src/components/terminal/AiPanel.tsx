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
import type { AiAssistantSettings, AiChatMode, AiExecutionMode } from "./XTerminal";

export interface AiCommand {
  id: number;
  cmd: string;
  why: string;
  requires_confirm: boolean;
  status?: "pending" | "running" | "done" | "skipped" | "cancelled" | "confirmed";
  exit_code?: number;
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
    <div className="flex items-center gap-0.5 rounded-lg bg-secondary/80 p-0.5">
      {(["auto", "fast", "step"] as AiExecutionMode[]).map((item) => {
        const cfg = modeConfig[item];
        const active = item === mode;
        return (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            title={cfg.desc}
            className={`flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-all ${
              active ? `bg-background shadow-sm ${cfg.color}` : "text-muted-foreground hover:text-foreground"
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
    <div className="flex items-center gap-0.5 rounded-lg bg-secondary/80 p-0.5">
      {(["ask", "agent"] as AiChatMode[]).map((item) => {
        const cfg = chatModeConfig[item];
        const active = item === mode;
        return (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            title={cfg.desc}
            className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-all ${
              active ? `bg-background shadow-sm ${cfg.tone}` : "text-muted-foreground hover:text-foreground"
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
        h3: ({ children }) => <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</h3>,
        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto rounded-lg border border-border">
            <table className="w-full border-collapse text-xs">{children}</table>
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

function CmdStatusBadge({ status, exit_code }: { status?: AiCommand["status"]; exit_code?: number }) {
  if (!status || status === "pending") {
    return <span className="rounded border border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground">ожидает</span>;
  }
  if (status === "running") {
    return (
      <span className="flex items-center gap-1 whitespace-nowrap rounded border border-warning/30 bg-warning/10 px-1.5 py-0.5 text-[10px] text-warning">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> выполняется
      </span>
    );
  }
  if (status === "done") {
    const ok = exit_code === 0 || exit_code === undefined;
    return (
      <span className={`flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${
        ok ? "border-success/30 bg-success/10 text-success" : "border-destructive/30 bg-destructive/10 text-destructive"
      }`}>
        {ok ? <CheckCircle2 className="h-2.5 w-2.5" /> : <AlertTriangle className="h-2.5 w-2.5" />}
        {ok ? "готово" : `ошибка (${exit_code})`}
      </span>
    );
  }
  if (status === "skipped" || status === "cancelled") {
    return <span className="px-1.5 py-0.5 text-[10px] text-muted-foreground/50 line-through">пропущено</span>;
  }
  if (status === "confirmed") {
    return <span className="rounded border border-info/30 bg-info/10 px-1.5 py-0.5 text-[10px] text-info">подтверждено</span>;
  }
  return null;
}

function CommandsMsg({
  msg,
  settings,
  onConfirm,
  onCancel,
}: {
  msg: AiMessage;
  settings: AiAssistantSettings;
  onConfirm?: (id: number) => void;
  onCancel?: (id: number) => void;
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
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex items-center gap-1.5 bg-secondary/60 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              <TerminalIcon className="h-3 w-3" /> Команды ({visibleCommands.length}/{allCommands.length})
            </div>
            <div className="divide-y divide-border/40">
              {visibleCommands.map((cmd) => (
                <div key={cmd.id} className="space-y-1.5 px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <code className="flex-1 break-all font-mono text-xs leading-relaxed text-primary">{cmd.cmd}</code>
                    <div className="shrink-0 pt-0.5">
                      <CmdStatusBadge status={cmd.status} exit_code={cmd.exit_code} />
                    </div>
                  </div>
                  {cmd.why ? <p className="text-xs text-muted-foreground">{cmd.why}</p> : null}
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
          <div className="rounded-lg border border-dashed border-border bg-secondary/20 px-3 py-2 text-xs text-muted-foreground">
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
      header: "bg-gradient-to-r from-success/15 to-success/5 text-success",
      Icon: CheckCircle2,
      label: "Выполнено успешно",
      glow: "shadow-[0_0_12px_rgba(34,197,94,0.08)]",
    },
    warning: {
      border: "border-warning/40",
      header: "bg-gradient-to-r from-warning/15 to-warning/5 text-warning",
      Icon: AlertTriangle,
      label: "Выполнено с предупреждениями",
      glow: "shadow-[0_0_12px_rgba(234,179,8,0.08)]",
    },
    error: {
      border: "border-destructive/40",
      header: "bg-gradient-to-r from-destructive/15 to-destructive/5 text-destructive",
      Icon: AlertTriangle,
      label: "Ошибки при выполнении",
      glow: "shadow-[0_0_12px_rgba(239,68,68,0.08)]",
    },
  }[msg.reportStatus || "ok"];

  return (
    <div className={`overflow-hidden rounded-xl border ${cfg.border} ${cfg.glow}`}>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className={`flex w-full items-center justify-between gap-2 px-4 py-2.5 text-xs font-semibold transition-colors hover:opacity-90 ${cfg.header}`}
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
    <div className="overflow-hidden rounded-xl border border-primary/30 bg-primary/5">
      <div className="flex items-center gap-2 bg-gradient-to-r from-primary/15 to-primary/5 px-4 py-2.5 text-xs font-semibold text-primary">
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
              autoFocus
              className="flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs text-foreground transition-colors placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <Button size="sm" className="h-8 rounded-lg px-2.5 text-xs" onClick={() => doReply(answer)} disabled={!answer.trim()}>
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
    <div className="overflow-hidden rounded-xl border border-border">
      <div className="flex items-center justify-between bg-secondary/40 px-4 py-2.5">
        <div className="min-w-0 flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-warning" />
          <code className="truncate font-mono">{msg.progressCmd}</code>
        </div>
        <span className="ml-2 flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
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
    <div className="overflow-hidden rounded-xl border border-warning/30 bg-warning/5">
      <div className="flex items-center gap-2 bg-gradient-to-r from-warning/15 to-warning/5 px-4 py-2.5 text-xs font-semibold text-warning">
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
}: {
  msg: AiMessage;
  settings: AiAssistantSettings;
  onConfirm?: (id: number) => void;
  onCancel?: (id: number) => void;
  onReply?: (qId: string, text: string) => void;
}) {
  const type = msg.type || "text";

  if (type === "commands") return <div className="w-full"><CommandsMsg msg={msg} settings={settings} onConfirm={onConfirm} onCancel={onCancel} /></div>;
  if (type === "report") return <div className="w-full"><ReportMsg msg={msg} /></div>;
  if (type === "question") return <div className="w-full"><QuestionMsg msg={msg} onReply={onReply} /></div>;
  if (type === "progress") return <div className="w-full"><ProgressMsg msg={msg} /></div>;
  if (type === "recovery") return <div className="w-full"><RecoveryMsg msg={msg} /></div>;

  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-sm">
          {msg.content}
        </div>
      </div>
    );
  }

  if (msg.role === "system") {
    return (
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
        <div className="flex-1 rounded-xl border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive/90">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] rounded-2xl rounded-tl-sm bg-secondary px-3.5 py-3 text-secondary-foreground shadow-sm">
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
  return <label className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{children}</label>;
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
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-hidden">
          <DialogHeader>
            <DialogTitle>Настройки AI Assistant</DialogTitle>
            <DialogDescription>
              Параметры применяются к текущему чату сразу. При необходимости сохраните их как глобальные значения по умолчанию.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="max-h-[calc(90vh-9.5rem)] space-y-4 overflow-y-auto">
            <SettingsSection
              title="Режим ответа"
              description="Fast подходит для коротких ответов и быстрых действий. Step оставляет больше пояснений и чаще просит подтверждение."
            >
              <div className="space-y-3 rounded-lg border border-border/60 bg-background/80 px-3 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-foreground">Режим чата</div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      `Ask` предлагает команды без автозапуска. `Agent` выполняет их сразу. Быстрый переключатель: `/mode ask` и `/mode agent`.
                    </p>
                  </div>
                  <ChatModeSelector mode={chatMode} onChange={onChatModeChange} />
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-foreground">Стиль выполнения</div>
                    <p className="mt-0.5 text-xs text-muted-foreground">Можно переключать прямо в чате или здесь.</p>
                  </div>
                  <ModeSelector mode={executionMode} onChange={onModeChange} />
                </div>

                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px]">
                  <div>
                    <InputLabel>Авто-отчёт</InputLabel>
                    <p className="mb-2 text-xs text-muted-foreground">
                      `Auto` включает summary в `Step` и отключает в `Fast`. `On` и `Off` принудительно переопределяют это поведение.
                    </p>
                  </div>
                  <select
                    value={settings.autoReport}
                    onChange={(event) => updateSettings({ autoReport: event.target.value === "on" || event.target.value === "off" ? event.target.value : "auto" })}
                    className="h-10 rounded-lg border border-border bg-background px-3 text-sm text-foreground focus:border-primary focus:outline-none"
                  >
                    <option value="auto">Auto</option>
                    <option value="on">Всегда On</option>
                    <option value="off">Всегда Off</option>
                  </select>
                </div>
              </div>
            </SettingsSection>

            <SettingsSection
              title="Память и отчёты"
              description="Контекст можно хранить между запросами, ограничивать по TTL и очищать отдельно от видимого чата."
            >
              <div className="space-y-3">
                <ToggleRow
                  title="Сохранять контекст"
                  description="Если выключить, каждый новый запрос пойдёт без накопленной памяти и без записи summary в backend-память."
                  checked={settings.memoryEnabled}
                  onCheckedChange={(checked) => updateSettings({ memoryEnabled: checked })}
                />

                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_120px]">
                  <div className="rounded-lg border border-border/60 bg-background/80 px-3 py-2.5">
                    <InputLabel>TTL памяти</InputLabel>
                    <p className="text-xs text-muted-foreground">Сколько последних пользовательских запросов учитывать в памяти чата. Диапазон: 1-20.</p>
                  </div>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={settings.memoryTtlRequests}
                    disabled={!settings.memoryEnabled}
                    onChange={(event) => updateSettings({ memoryTtlRequests: Math.max(1, Math.min(20, Number(event.target.value || 1))) })}
                    className="h-10 rounded-lg border border-border bg-background px-3 text-sm text-foreground focus:border-primary focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                  />
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/60 bg-background/80 px-3 py-3">
                  <div>
                    <div className="text-sm font-medium text-foreground">Ручное управление памятью</div>
                    <p className="mt-0.5 text-xs text-muted-foreground">Очищает server-side memory текущего AI-чата, но не удаляет сообщения из панели.</p>
                  </div>
                  <Button type="button" variant="outline" onClick={onClearMemory} className="gap-2">
                    <Trash2 className="h-4 w-4" />
                    Очистить память
                  </Button>
                </div>
              </div>
            </SettingsSection>

            <SettingsSection
              title="Безопасность"
              description="Опасные команды можно отправлять только с подтверждением, а allowlist/blocklist ограничивает набор допустимых команд."
            >
              <div className="space-y-3">
                <ToggleRow
                  title="Подтверждать опасные команды"
                  description="Опасные операции останутся в плане, но потребуют явного подтверждения пользователя."
                  checked={settings.confirmDangerousCommands}
                  onCheckedChange={(checked) => updateSettings({ confirmDangerousCommands: checked })}
                />

                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-border/60 bg-background/80 p-3">
                    <InputLabel>Whitelist команд</InputLabel>
                    <p className="mb-2 text-xs text-muted-foreground">
                      Одна маска на строку. Если список не пустой, AI сможет запускать только совпадающие команды. Поддерживается `re:`.
                    </p>
                    <textarea
                      value={whitelistText}
                      onChange={(event) => updateSettings({ whitelistPatterns: normalizePatternList(event.target.value) })}
                      rows={6}
                      placeholder={"sudo systemctl\njournalctl -u nginx\nre:^docker\\s+ps"}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                    />
                  </div>

                  <div className="rounded-lg border border-border/60 bg-background/80 p-3">
                    <InputLabel>Blocklist команд</InputLabel>
                    <p className="mb-2 text-xs text-muted-foreground">
                      Всё, что совпадёт с этими паттернами, backend сразу заблокирует. Поддерживается `re:`.
                    </p>
                    <textarea
                      value={blacklistText}
                      onChange={(event) => updateSettings({ blacklistPatterns: normalizePatternList(event.target.value) })}
                      rows={6}
                      placeholder={"rm -rf /\nshutdown\nre:^mkfs"}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                    />
                  </div>
                </div>
              </div>
            </SettingsSection>

            <SettingsSection
              title="Видимость в чате"
              description="Можно отдельно показывать предлагаемые команды и уже выполненные действия, не меняя поведение backend."
            >
              <div className="space-y-3">
                <ToggleRow
                  title="Показывать предлагаемые команды"
                  description="Команды в статусе `pending` и ожидающие подтверждения будут видны в AI-чате."
                  checked={settings.showSuggestedCommands}
                  onCheckedChange={(checked) => updateSettings({ showSuggestedCommands: checked })}
                />
                <ToggleRow
                  title="Показывать выполненные команды"
                  description="Команды со статусами `running`, `done`, `skipped` и `cancelled` будут оставаться в ленте чата."
                  checked={settings.showExecutedCommands}
                  onCheckedChange={(checked) => updateSettings({ showExecutedCommands: checked })}
                />
              </div>
            </SettingsSection>
          </DialogBody>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onResetToDefaults} className="gap-2">
              <RotateCcw className="h-4 w-4" />
              Сбросить чат к глобальным
            </Button>
            <Button type="button" onClick={onSaveDefaults} className="gap-2">
              <Check className="h-4 w-4" />
              Сохранить как глобальные
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="flex h-full flex-col bg-card">
        <div className="shrink-0 border-b border-border px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className={`flex h-7 w-7 items-center justify-center rounded-lg transition-all ${
                isGenerating ? "bg-primary/25 shadow-md shadow-primary/20" : "bg-primary/10"
              }`}>
                <Bot className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-medium leading-none text-foreground">AI Assistant</h3>
                <p className="mt-0.5 text-[10px]">
                  {isGenerating ? <span className="animate-pulse text-warning">обрабатывает...</span> : <span className="text-success">готов</span>}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                onClick={() => setSettingsOpen(true)}
                title="Настройки ассистента"
                aria-label="AI settings"
              >
                <Settings2 className="h-3.5 w-3.5" />
              </Button>

              {isGenerating ? (
                <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 text-warning hover:bg-warning/10" onClick={onStop} title="Остановить" aria-label="Stop">
                  <Square className="h-3.5 w-3.5" />
                </Button>
              ) : null}

              {messages.length > 0 ? (
                <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive" onClick={onClearChat} title="Очистить чат" aria-label="Clear chat">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              ) : null}

              <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground" onClick={onClose} aria-label="Close">
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <div className="space-y-2 border-b border-border/60 px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Режим чата</span>
            <ChatModeSelector mode={chatMode} onChange={onChatModeChange} />
          </div>
          <div className={`rounded-xl border px-3 py-2 ${currentChatMode.badge}`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold">{currentChatMode.label}</div>
                <p className="mt-0.5 text-[11px] opacity-90">{currentChatMode.desc}</p>
              </div>
              <code className="rounded bg-background/60 px-2 py-1 text-[10px] font-mono text-foreground/80">/mode {chatMode}</code>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-between border-b border-border/60 px-3 py-1.5">
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Стиль</span>
          <ModeSelector mode={executionMode} onChange={onModeChange} />
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center space-y-4 py-8 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10">
                <Sparkles className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">Чем могу помочь?</p>
                <p className="mt-1 text-xs text-muted-foreground">Задайте вопрос о терминале, сервере или текущем выводе.</p>
              </div>
              <div className="flex flex-wrap justify-center gap-1.5">
                {quickPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => handleSend(prompt)}
                    className="rounded-full border border-border/60 px-2.5 py-1.5 text-xs text-muted-foreground transition-all hover:border-primary/50 hover:bg-primary/5 hover:text-primary"
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
              />
            ))
          )}

          {isGenerating ? (
            <div className="flex justify-start">
              <div className="flex items-center gap-2.5 rounded-2xl rounded-tl-sm bg-secondary px-3.5 py-3 shadow-sm">
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

        <div className="shrink-0 border-t border-border p-2.5">
          {messages.length > 0 ? (
            <div className="mb-2 flex items-center justify-between gap-2 rounded-xl border border-border/70 bg-secondary/25 px-3 py-2">
              <div>
                <div className="text-xs font-medium text-foreground">Ручной отчёт</div>
                <p className="mt-0.5 text-[11px] text-muted-foreground">Сформировать summary по завершённым командам текущего AI-диалога.</p>
              </div>
              <Button type="button" size="sm" variant="outline" onClick={() => onGenerateReport?.(false)} disabled={!canGenerateReport}>
                <FileText className="h-3.5 w-3.5" />
                Сформировать отчёт
              </Button>
            </div>
          ) : null}

          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Сообщение... (Enter — отправить, /mode ask | /mode agent)"
              rows={1}
              className="min-h-[36px] max-h-[120px] flex-1 resize-none rounded-xl border border-border bg-secondary px-3 py-2 text-sm text-foreground transition-colors placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <Button type="button" size="sm" onClick={() => handleSend()} disabled={!input.trim() || isGenerating} className="h-9 w-9 shrink-0 rounded-xl p-0" aria-label="Send">
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
