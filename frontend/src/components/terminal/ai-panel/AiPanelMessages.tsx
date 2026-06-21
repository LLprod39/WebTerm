import { useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  FileText,
  HelpCircle,
  Loader2,
  RotateCcw,
  Terminal as TerminalIcon,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { riskBadgeClass, useAiCommandRisk } from "@/hooks/useAiCommandRisk";
import { AiQuestionCard } from "../AiQuestionCard";
import type { AiAssistantSettings, AiCommand, AiMessage } from "../ai-types";
import { AgentTimelineMessage } from "./AgentTimelineMessages";

function isExecutedCommandStatus(status?: AiCommand["status"]) {
  return status === "running" || status === "done" || status === "skipped" || status === "cancelled";
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

function CmdRiskBadge({ command }: { command: AiCommand }) {
  const risk = useAiCommandRisk(command);
  if (risk.level === "safe" && risk.categories.length === 0 && risk.execMode !== "direct") {
    return null;
  }
  const showExecHint = risk.execMode === "direct" && risk.level === "safe";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium ${
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
    return <span className="rounded-md border border-border/60 px-1.5 py-0.5 text-xs text-muted-foreground">ожидает</span>;
  }
  if (status === "running") {
    return (
      <span className="flex items-center gap-1 whitespace-nowrap rounded-md border border-warning/30 bg-warning/10 px-1.5 py-0.5 text-xs text-warning">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> выполняется
      </span>
    );
  }
  if (status === "done") {
    const ok = exit_code === 0 || exit_code === undefined;
    return (
      <span className={`flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-xs ${
        ok ? "border-success/30 bg-success/10 text-success" : "border-destructive/30 bg-destructive/10 text-destructive"
      }`}>
        {ok ? <CheckCircle2 className="h-2.5 w-2.5" /> : <AlertTriangle className="h-2.5 w-2.5" />}
        {ok ? "готово" : `ошибка (${exit_code})`}
      </span>
    );
  }
  if (status === "skipped" || status === "cancelled") {
    return <span className="px-1.5 py-0.5 text-xs text-muted-foreground/50 line-through">пропущено</span>;
  }
  if (status === "confirmed") {
    return <span className="rounded-md border border-info/30 bg-info/10 px-1.5 py-0.5 text-xs text-info">подтверждено</span>;
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
            <div className="flex items-center gap-1.5 bg-secondary/40 px-3 py-2 text-xs font-medium text-muted-foreground">
              <TerminalIcon className="h-3 w-3" /> Команды ({visibleCommands.length}/{allCommands.length})
            </div>
            <div className="divide-y divide-border/40">
              {visibleCommands.map((cmd) => (
                <div key={cmd.id} className="space-y-1.5 px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <code className="flex-1 break-all font-mono text-xs leading-relaxed text-foreground">{cmd.cmd}</code>
                    <div className="flex shrink-0 items-center gap-1 pt-0.5">
                      <CmdRiskBadge command={cmd} />
                      <CmdStatusBadge status={cmd.status} exit_code={cmd.exit_code} />
                    </div>
                  </div>
                  {cmd.why ? <p className="text-xs text-muted-foreground">{cmd.why}</p> : null}
                  {cmd.direct_output ? (
                    <pre className="max-h-48 overflow-auto rounded-md border border-border/60 bg-secondary/40 px-2 py-1.5 font-mono text-xs leading-relaxed text-muted-foreground">
                      {cmd.direct_output}
                    </pre>
                  ) : null}
                  {onExplainCommand && cmd.status === "done" && typeof cmd.exit_code === "number" ? (
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 gap-1 px-2 text-xs"
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
              <div className="border-t border-border/40 bg-secondary/20 px-3 py-2 text-xs text-muted-foreground">
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
        <span className="ml-2 flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {msg.progressElapsed}s
        </span>
      </div>
      {msg.progressTail ? (
        <div className="max-h-24 overflow-y-auto whitespace-pre-wrap break-all bg-terminal-bg/60 px-4 py-2 text-xs font-mono text-muted-foreground/80">
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

export function AiMessageRenderer({
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

  if (type.startsWith("agent_")) {
    return (
      <div className="w-full">
        <AgentTimelineMessage
          msg={msg}
          isFirstAgent={isFirstAgent}
          isLastAgent={isLastAgent}
        />
      </div>
    );
  }

  if (msg.role === "user") {
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

  return (
    <div className="rounded-md border border-border/50 bg-card/60 px-3.5 py-2.5 text-[13px] leading-relaxed text-foreground">
      <MD content={msg.content} />
    </div>
  );
}
