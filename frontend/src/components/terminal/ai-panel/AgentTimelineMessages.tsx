import { useState, type ReactNode } from "react";
import {
  Brain,
  CheckCircle2,
  CircleDot,
  ListTodo,
  Loader2,
  Pause,
  Server as ServerIcon,
  Sparkles,
  X,
} from "lucide-react";
import type { AiMessage } from "../ai-types";
import { NovaContextCard } from "../nova/NovaContextCard";
import { AgentToolMsg } from "./AgentToolMsg";

type TimelineDot = "start" | "think" | "tool-ok" | "tool-err" | "tool-run" | "todo" | "stop";

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
        className="flex flex-wrap items-center gap-1.5 rounded-md border border-border/50 bg-background/40 px-2.5 py-1.5 text-xs text-muted-foreground"
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
                className="rounded border border-border/50 bg-secondary/40 px-1 py-0 font-mono text-xs text-muted-foreground"
              >
                {name}
              </code>
            ))}
            {extras.length > 3 ? (
              <span className="text-xs text-muted-foreground">+{extras.length - 3}</span>
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
      className="group flex w-full items-start gap-1.5 px-2 py-0.5 text-left text-xs italic leading-snug text-muted-foreground/70 transition-colors hover:text-foreground"
      title={expanded ? undefined : msg.content}
    >
      <Brain className="h-3 w-3 mt-0.5 shrink-0 opacity-60" />
      <span className={`min-w-0 flex-1 ${expanded ? "whitespace-pre-wrap" : "truncate"}`}>
        {expanded ? msg.content : preview}
      </span>
    </button>
  );
}

export function AgentTodoMsg({ msg }: { msg: AiMessage }) {
  const todos = msg.agentTodos || [];
  if (todos.length === 0) return null;
  const completed = todos.filter((t) => t.status === "completed").length;
  return (
    <div className="overflow-hidden rounded-md border border-border/60 bg-card/70">
      <div className="flex items-center gap-2 border-b border-border/50 px-3 py-1.5 text-xs font-medium text-foreground">
        <ListTodo className="h-3 w-3 text-muted-foreground" />
        <span>Todo</span>
        <span className="ml-auto font-mono text-xs text-muted-foreground">
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
  children: ReactNode;
  dot: TimelineDot;
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

function dotKindForMsg(msg: AiMessage): TimelineDot {
  const type = msg.type || "text";
  if (type === "agent_start") return "start";
  if (type === "agent_thinking") return "think";
  if (type === "agent_todo") return "todo";
  if (type === "agent_stopped") return "stop";
  if (type === "agent_tool") {
    const running = msg.agentToolOutput === undefined && msg.agentToolError === undefined;
    if (running) return "tool-run";
    const nonZeroExit =
      typeof msg.agentToolExitCode === "number" && msg.agentToolExitCode !== 0;
    return msg.agentToolOk !== false && !nonZeroExit ? "tool-ok" : "tool-err";
  }
  return "think";
}

export function AgentTimelineMessage({
  msg,
  isFirstAgent,
  isLastAgent,
}: {
  msg: AiMessage;
  isFirstAgent?: boolean;
  isLastAgent?: boolean;
}) {
  const type = msg.type || "text";
  const dot = dotKindForMsg(msg);
  const content =
    type === "agent_start" ? (
      <AgentStartMsg msg={msg} />
    ) : type === "agent_thinking" ? (
      <AgentThinkingMsg msg={msg} />
    ) : type === "agent_tool" ? (
      <AgentToolMsg msg={msg} />
    ) : type === "agent_todo" ? (
      <AgentTodoMsg msg={msg} />
    ) : type === "agent_stopped" ? (
      <AgentStoppedMsg msg={msg} />
    ) : null;

  if (!content) return null;
  return (
    <TimelineRow dot={dot} first={isFirstAgent} last={isLastAgent}>
      {content}
    </TimelineRow>
  );
}
