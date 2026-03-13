import { useRef, useState, useEffect } from "react";
import {
  Bot, Send, X, Square, Sparkles, Copy, Check, Terminal as TerminalIcon,
  AlertTriangle, CheckCircle2, RotateCcw, HelpCircle, Loader2, Clock,
  Trash2, Zap, Footprints, Wand2,
  FileText, ChevronDown, ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import ReactMarkdown from "react-markdown";
import type { AiExecutionMode } from "./XTerminal";

// ─── Types ────────────────────────────────────────────────────────────────────

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
  messages: AiMessage[];
  isGenerating: boolean;
  executionMode: AiExecutionMode;
  onModeChange: (mode: AiExecutionMode) => void;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

const quickPrompts = ["Объясни вывод", "Предложи команду", "Проверь синтаксис", "Что означает ошибка"];

const modeConfig: Record<AiExecutionMode, { icon: typeof Zap; label: string; desc: string; color: string }> = {
  auto: { icon: Wand2, label: "Авто", desc: "AI сам решает", color: "text-primary" },
  fast: { icon: Zap, label: "Быстрый", desc: "Без подтверждений", color: "text-warning" },
  step: { icon: Footprints, label: "Пошагово", desc: "С подтверждением", color: "text-success" },
};

function ModeSelector({ mode, onChange }: { mode: AiExecutionMode; onChange: (m: AiExecutionMode) => void }) {
  return (
    <div className="flex items-center gap-0.5 bg-secondary/80 rounded-lg p-0.5">
      {(["auto", "fast", "step"] as AiExecutionMode[]).map((m) => {
        const cfg = modeConfig[m];
        const active = m === mode;
        return (
          <button
            key={m}
            onClick={() => onChange(m)}
            title={cfg.desc}
            className={`flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium transition-all ${
              active
                ? `bg-background shadow-sm ${cfg.color}`
                : "text-muted-foreground hover:text-foreground"
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

function CodeBlock({ children, language }: { children: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative my-2 rounded-md overflow-hidden border border-border">
      <div className="flex items-center justify-between bg-secondary px-3 py-1.5 text-xs text-muted-foreground">
        <span>{language || "code"}</span>
        <button
          onClick={() => { navigator.clipboard.writeText(children); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
          className="hover:text-foreground transition-colors"
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
          return <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono text-primary">{children}</code>;
        },
        p: ({ children }) => <p className="mb-1.5 last:mb-0 text-sm leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-4 mb-1.5 space-y-0.5 text-sm">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 mb-1.5 space-y-0.5 text-sm">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        h1: ({ children }) => <h1 className="text-sm font-bold mb-1 text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-semibold mb-1 text-primary">{children}</h2>,
        h3: ({ children }) => <h3 className="text-xs font-semibold mb-1 text-muted-foreground uppercase tracking-wide">{children}</h3>,
        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
        table: ({ children }) => (
          <div className="overflow-x-auto my-2 rounded-lg border border-border">
            <table className="text-xs border-collapse w-full">{children}</table>
          </div>
        ),
        th: ({ children }) => <th className="border-b border-border px-3 py-2 bg-secondary/60 text-left font-semibold text-foreground">{children}</th>,
        td: ({ children }) => <td className="border-b border-border/40 px-3 py-1.5 text-secondary-foreground">{children}</td>,
        hr: () => <hr className="border-border my-2" />,
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-primary/40 pl-3 my-2 text-muted-foreground italic text-sm">{children}</blockquote>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function CmdStatusBadge({ status, exit_code }: { status?: AiCommand["status"]; exit_code?: number }) {
  if (!status || status === "pending")
    return <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 rounded border border-border/60">ожидает</span>;
  if (status === "running")
    return (
      <span className="flex items-center gap-1 text-[10px] text-warning px-1.5 py-0.5 rounded border border-warning/30 bg-warning/10 whitespace-nowrap">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> выполняется
      </span>
    );
  if (status === "done") {
    const ok = exit_code === 0 || exit_code === undefined;
    return (
      <span className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border whitespace-nowrap ${
        ok ? "text-success border-success/30 bg-success/10" : "text-destructive border-destructive/30 bg-destructive/10"
      }`}>
        {ok ? <CheckCircle2 className="h-2.5 w-2.5" /> : <AlertTriangle className="h-2.5 w-2.5" />}
        {ok ? "готово" : `ошибка (${exit_code})`}
      </span>
    );
  }
  if (status === "skipped" || status === "cancelled")
    return <span className="text-[10px] text-muted-foreground/50 px-1.5 py-0.5 line-through">пропущено</span>;
  if (status === "confirmed")
    return <span className="text-[10px] text-info px-1.5 py-0.5 rounded border border-info/30 bg-info/10">подтверждено</span>;
  return null;
}

function CommandsMsg({ msg, onConfirm, onCancel }: { msg: AiMessage; onConfirm?: (id: number) => void; onCancel?: (id: number) => void }) {
  return (
    <div className="space-y-2 w-full">
      {msg.content && (
        <div className="text-sm text-secondary-foreground">
          <MD content={msg.content} />
        </div>
      )}
      {msg.commands && msg.commands.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <div className="bg-secondary/60 px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
            <TerminalIcon className="h-3 w-3" /> Команды ({msg.commands.length})
          </div>
          <div className="divide-y divide-border/40">
            {msg.commands.map((cmd) => (
              <div key={cmd.id} className="px-3 py-2 space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <code className="text-xs font-mono text-primary flex-1 break-all leading-relaxed">{cmd.cmd}</code>
                  <div className="shrink-0 pt-0.5">
                    <CmdStatusBadge status={cmd.status} exit_code={cmd.exit_code} />
                  </div>
                </div>
                {cmd.why && <p className="text-xs text-muted-foreground">{cmd.why}</p>}
                {cmd.requires_confirm && (!cmd.status || cmd.status === "pending") && (
                  <div className="flex gap-1.5">
                    <Button size="sm" variant="outline"
                      className="h-6 text-xs px-2 border-success/50 text-success hover:bg-success/10"
                      onClick={() => onConfirm?.(cmd.id)}>
                      <Check className="h-3 w-3 mr-1" /> Выполнить
                    </Button>
                    <Button size="sm" variant="outline"
                      className="h-6 text-xs px-2 border-destructive/40 text-destructive/80 hover:bg-destructive/10"
                      onClick={() => onCancel?.(cmd.id)}>
                      <X className="h-3 w-3 mr-1" /> Пропустить
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ReportMsg({ msg }: { msg: AiMessage }) {
  const [expanded, setExpanded] = useState(true);
  const cfg = {
    ok:      { border: "border-success/40",      header: "bg-gradient-to-r from-success/15 to-success/5 text-success",      Icon: CheckCircle2,   label: "Выполнено успешно", glow: "shadow-[0_0_12px_rgba(34,197,94,0.08)]" },
    warning: { border: "border-warning/40",      header: "bg-gradient-to-r from-warning/15 to-warning/5 text-warning",      Icon: AlertTriangle,  label: "Выполнено с предупреждениями", glow: "shadow-[0_0_12px_rgba(234,179,8,0.08)]" },
    error:   { border: "border-destructive/40",  header: "bg-gradient-to-r from-destructive/15 to-destructive/5 text-destructive", Icon: AlertTriangle, label: "Ошибки при выполнении", glow: "shadow-[0_0_12px_rgba(239,68,68,0.08)]" },
  }[msg.reportStatus || "ok"];

  return (
    <div className={`rounded-xl border overflow-hidden ${cfg.border} ${cfg.glow}`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className={`w-full flex items-center justify-between gap-2 px-4 py-2.5 text-xs font-semibold ${cfg.header} transition-colors hover:opacity-90`}
      >
        <div className="flex items-center gap-2">
          <cfg.Icon className="h-4 w-4" />
          <FileText className="h-3.5 w-3.5 opacity-60" />
          <span>{cfg.label}</span>
        </div>
        {expanded ? <ChevronUp className="h-3.5 w-3.5 opacity-60" /> : <ChevronDown className="h-3.5 w-3.5 opacity-60" />}
      </button>
      {expanded && (
        <div className="px-4 py-3 text-sm text-secondary-foreground report-content">
          <MD content={msg.content} />
        </div>
      )}
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
    <div className="rounded-xl border border-primary/30 bg-primary/5 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 text-xs font-semibold text-primary bg-gradient-to-r from-primary/15 to-primary/5">
        <HelpCircle className="h-4 w-4" /> Вопрос от AI
      </div>
      <div className="px-4 py-3 space-y-2.5">
        <p className="text-sm text-foreground">{msg.question || msg.content}</p>
        {msg.questionCmd && (
          <code className="block text-xs font-mono text-muted-foreground bg-muted px-2.5 py-1.5 rounded-lg">
            $ {msg.questionCmd}
          </code>
        )}
        {msg.questionExitCode !== undefined && (
          <p className="text-xs text-muted-foreground">Код выхода: {msg.questionExitCode}</p>
        )}
        {!answered ? (
          <div className="flex gap-2">
            <input
              value={answer}
              onChange={e => setAnswer(e.target.value)}
              onKeyDown={e => e.key === "Enter" && doReply(answer)}
              placeholder="Ваш ответ..."
              autoFocus
              className="flex-1 text-xs bg-background border border-border rounded-lg px-2.5 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
            />
            <Button size="sm" className="h-8 px-2.5 text-xs rounded-lg" onClick={() => doReply(answer)} disabled={!answer.trim()}>
              <Send className="h-3 w-3" />
            </Button>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground italic">Ответ отправлен</p>
        )}
      </div>
    </div>
  );
}

function ProgressMsg({ msg }: { msg: AiMessage }) {
  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 bg-secondary/40">
        <div className="flex items-center gap-2 text-xs text-muted-foreground min-w-0">
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0 text-warning" />
          <code className="font-mono truncate">{msg.progressCmd}</code>
        </div>
        <span className="flex items-center gap-1 text-xs text-muted-foreground shrink-0 ml-2">
          <Clock className="h-3 w-3" />{msg.progressElapsed}s
        </span>
      </div>
      {msg.progressTail && (
        <div className="px-4 py-2 text-[11px] font-mono text-muted-foreground/80 bg-terminal-bg/60 max-h-24 overflow-y-auto whitespace-pre-wrap break-all">
          {msg.progressTail}
        </div>
      )}
    </div>
  );
}

function RecoveryMsg({ msg }: { msg: AiMessage }) {
  return (
    <div className="rounded-xl border border-warning/30 bg-warning/5 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 text-xs font-semibold text-warning bg-gradient-to-r from-warning/15 to-warning/5">
        <RotateCcw className="h-4 w-4" /> Автоисправление
      </div>
      <div className="px-4 py-3 space-y-2 text-xs">
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground shrink-0 pt-0.5 font-medium">Было:</span>
          <code className="font-mono text-destructive/80 break-all bg-destructive/5 px-2 py-0.5 rounded">{msg.recoveryOriginal}</code>
        </div>
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground shrink-0 pt-0.5 font-medium">Стало:</span>
          <code className="font-mono text-success break-all bg-success/5 px-2 py-0.5 rounded">{msg.recoveryNew}</code>
        </div>
        {msg.recoveryWhy && <p className="text-muted-foreground pt-0.5">{msg.recoveryWhy}</p>}
      </div>
    </div>
  );
}

function MsgRenderer({ msg, onConfirm, onCancel, onReply }: {
  msg: AiMessage;
  onConfirm?: (id: number) => void;
  onCancel?: (id: number) => void;
  onReply?: (qId: string, text: string) => void;
}) {
  const t = msg.type || "text";

  if (t === "commands") return <div className="w-full"><CommandsMsg msg={msg} onConfirm={onConfirm} onCancel={onCancel} /></div>;
  if (t === "report")   return <div className="w-full"><ReportMsg msg={msg} /></div>;
  if (t === "question") return <div className="w-full"><QuestionMsg msg={msg} onReply={onReply} /></div>;
  if (t === "progress") return <div className="w-full"><ProgressMsg msg={msg} /></div>;
  if (t === "recovery") return <div className="w-full"><RecoveryMsg msg={msg} /></div>;

  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm px-3.5 py-2.5 text-sm bg-primary text-primary-foreground leading-relaxed shadow-sm">
          {msg.content}
        </div>
      </div>
    );
  }
  if (msg.role === "system") {
    return (
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
        <div className="flex-1 text-xs text-destructive/90 bg-destructive/10 border border-destructive/20 rounded-xl px-3 py-2">
          {msg.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] rounded-2xl rounded-tl-sm px-3.5 py-3 bg-secondary text-secondary-foreground shadow-sm">
        <MD content={msg.content} />
      </div>
    </div>
  );
}

// ─── Main panel ───────────────────────────────────────────────────────────────

export function AiPanel({
  onClose, onSend, onStop, onConfirm, onCancel, onReply,
  onClearChat, messages, isGenerating, executionMode, onModeChange,
}: AiPanelProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  const handleSend = (text?: string) => {
    const msg = (text || input).trim();
    if (!msg) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    onSend(msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

  return (
    <div className="flex flex-col h-full bg-card">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <div className={`h-7 w-7 rounded-lg flex items-center justify-center transition-all ${
            isGenerating ? "bg-primary/25 shadow-md shadow-primary/20" : "bg-primary/10"
          }`}>
            <Bot className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground leading-none">AI Assistant</h3>
            <p className="text-[10px] mt-0.5">
              {isGenerating
                ? <span className="text-warning animate-pulse">обрабатывает...</span>
                : <span className="text-success">готов</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isGenerating && (
            <Button size="sm" variant="ghost"
              className="h-7 w-7 p-0 text-warning hover:bg-warning/10"
              onClick={onStop} title="Остановить" aria-label="Stop">
              <Square className="h-3.5 w-3.5" />
            </Button>
          )}
          {messages.length > 0 && (
            <Button size="sm" variant="ghost"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
              onClick={onClearChat} title="Очистить чат" aria-label="Clear chat">
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button size="sm" variant="ghost"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
            onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Mode selector */}
      <div className="px-3 py-1.5 border-b border-border/60 shrink-0 flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">Режим</span>
        <ModeSelector mode={executionMode} onChange={onModeChange} />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-4 py-8">
            <div className="h-12 w-12 rounded-2xl bg-primary/10 flex items-center justify-center">
              <Sparkles className="h-6 w-6 text-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">Чем могу помочь?</p>
              <p className="text-xs text-muted-foreground mt-1">Задайте вопрос о терминале или сервере</p>
            </div>
            <div className="flex flex-wrap gap-1.5 justify-center">
              {quickPrompts.map((p) => (
                <button key={p} onClick={() => handleSend(p)}
                  className="text-xs px-2.5 py-1.5 rounded-full border border-border/60 text-muted-foreground hover:text-primary hover:border-primary/50 hover:bg-primary/5 transition-all">
                  {p}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <MsgRenderer key={msg.id} msg={msg} onConfirm={onConfirm} onCancel={onCancel} onReply={onReply} />
          ))
        )}

        {isGenerating && (
          <div className="flex justify-start">
            <div className="bg-secondary rounded-2xl rounded-tl-sm px-3.5 py-3 flex items-center gap-2.5 shadow-sm">
              <div className="flex gap-0.5">
                {[0, 150, 300].map((delay) => (
                  <span key={delay} className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce"
                    style={{ animationDelay: `${delay}ms` }} />
                ))}
              </div>
              <span className="text-xs text-muted-foreground">AI думает...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border p-2.5 shrink-0">
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Сообщение... (Enter — отправить)"
            rows={1}
            className="flex-1 bg-secondary border border-border rounded-xl px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors resize-none min-h-[36px] max-h-[120px]"
          />
          <Button size="sm" onClick={() => handleSend()} disabled={!input.trim() || isGenerating}
            className="h-9 w-9 p-0 shrink-0 rounded-xl" aria-label="Send">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
