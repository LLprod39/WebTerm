import { memo, useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AlertCircle, Check, ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import type { StreamToolStep } from "./useOperatorChatWs";

export type ThinkingPhase = "thinking" | "tools" | "streaming" | "idle";

type Props = {
  phase: ThinkingPhase;
  startedAt: number | null;
  iteration?: number | null;
  /** Kept for transport compatibility. Raw model reasoning is deliberately never rendered. */
  reasoningText?: string;
  /** True when the model is actively reasoning; only the safe activity stage is shown. */
  hasReasoningStream?: boolean;
  /** Backend status is classified into a safe stage and is never printed verbatim. */
  statusMessage?: string;
  toolSteps?: StreamToolStep[];
  compact?: boolean;
  /** Prefer expanded activity details at the beginning of a turn. */
  preferExpanded?: boolean;
};

const ease = [0.22, 1, 0.36, 1] as const;

function formatElapsed(ms: number) {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

type ActivityKind = "analyzing" | "checking" | "executing" | "composing";

function resolveActivity(opts: {
  phase: ThinkingPhase;
  statusMessage: string;
  toolSteps: StreamToolStep[];
}): ActivityKind {
  if (opts.phase === "streaming") return "composing";
  if (opts.toolSteps.some((step) => step.status === "running") || opts.phase === "tools") {
    return "executing";
  }

  const status = opts.statusMessage.toLowerCase();
  if (/генерац|формир|пиш|generat|compos|writ/.test(status)) return "composing";
  if (opts.toolSteps.length > 0 || /провер|запраш|получ|search|fetch|inspect|check/.test(status)) {
    return "checking";
  }
  return "analyzing";
}

function hasConfirmationStatus(statusMessage: string) {
  return /подтверж|согласован|разрешен|confirm|approval|permission/i.test(statusMessage);
}

function hasErrorStatus(statusMessage: string) {
  return /ошиб|сбой|не удалось|error|failed|failure/i.test(statusMessage);
}

function safeToolPreview(value?: string) {
  if (!value) return "";
  const compact = value.replace(/[\r\n\t]+/g, " ").replace(/\s{2,}/g, " ").trim();
  const redacted = compact.replace(
    /((?:password|passwd|token|secret|api[-_ ]?key)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi,
    "$1•••",
  );
  return redacted.length > 140 ? `${redacted.slice(0, 137)}…` : redacted;
}

/** Compact activity timeline. It exposes safe stages and tool summaries, never raw chain-of-thought. */
export const OperatorThinkingPanel = memo(function OperatorThinkingPanel({
  phase,
  startedAt,
  iteration,
  statusMessage = "",
  toolSteps = [],
  compact = false,
  preferExpanded = false,
}: Props) {
  const { lang } = useI18n();
  const reduceMotion = useReducedMotion();
  const detailsId = useId();
  const [now, setNow] = useState(() => Date.now());
  const [expanded, setExpanded] = useState(preferExpanded);
  const previousPhaseRef = useRef<ThinkingPhase>("idle");
  const manuallyToggledRef = useRef(false);

  const hasToolError = toolSteps.some((step) => step.status === "error");
  const needsConfirmation = hasConfirmationStatus(statusMessage);
  const hasError = hasToolError || hasErrorStatus(statusMessage);
  const requiresAttention = needsConfirmation || hasError;
  const hasDetails = toolSteps.length > 0 || requiresAttention;

  useEffect(() => {
    const previousPhase = previousPhaseRef.current;
    if (phase === "idle") {
      manuallyToggledRef.current = false;
    } else if (previousPhase === "idle") {
      setExpanded(preferExpanded);
      setNow(Date.now());
    } else if (
      phase === "streaming" &&
      previousPhase !== "streaming" &&
      !manuallyToggledRef.current &&
      !requiresAttention
    ) {
      setExpanded(false);
    }
    previousPhaseRef.current = phase;
  }, [phase, preferExpanded, requiresAttention]);

  useEffect(() => {
    if (!startedAt || phase === "idle") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt, phase]);

  useEffect(() => {
    if (phase !== "idle" && requiresAttention) setExpanded(true);
  }, [phase, requiresAttention]);

  if (phase === "idle") return null;

  const elapsed = startedAt ? formatElapsed(Math.max(0, now - startedAt)) : "";
  const activity = resolveActivity({ phase, statusMessage, toolSteps });
  const labels: Record<ActivityKind, { ru: string; en: string }> = {
    analyzing: { ru: "Анализирует", en: "Analyzing" },
    checking: { ru: "Проверяет данные", en: "Checking data" },
    executing: { ru: "Выполняет", en: "Working" },
    composing: { ru: "Формирует ответ", en: "Composing answer" },
  };
  const label = localize(lang, labels[activity].ru, labels[activity].en);
  const showBody = expanded && hasDetails;
  const transition = reduceMotion ? { duration: 0 } : { duration: 0.17, ease };

  const row = (
    <>
      {hasDetails ? (
        expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-60" />
        )
      ) : (
        <Loader2
          className={cn("h-3.5 w-3.5 shrink-0 opacity-65", !reduceMotion && "animate-spin")}
        />
      )}
      <span aria-live="polite" className="font-medium tracking-tight">
        {label}
      </span>
      {elapsed ? (
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground/65">{elapsed}</span>
      ) : null}
      {iteration != null && iteration > 1 ? (
        <span className="text-[11px] text-muted-foreground/45">· {iteration}</span>
      ) : null}
    </>
  );

  return (
    <motion.div
      layout={!reduceMotion}
      transition={transition}
      className={cn("max-w-[min(42rem,100%)]", compact && "text-[12px]")}
      data-operator-activity
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={activity}
          initial={reduceMotion ? false : { opacity: 0, y: 2 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? { opacity: 1 } : { opacity: 0, y: -2 }}
          transition={transition}
        >
          {hasDetails ? (
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={detailsId}
              onClick={() => {
                manuallyToggledRef.current = true;
                setExpanded((value) => !value);
              }}
              className="group inline-flex min-h-7 items-center gap-1.5 rounded-full px-1 py-0.5 text-left text-[13px] text-muted-foreground transition-colors [transition-duration:120ms] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 active:scale-[0.98] motion-reduce:transform-none"
            >
              {row}
            </button>
          ) : (
            <div
              role="status"
              className="inline-flex min-h-7 items-center gap-1.5 px-1 py-0.5 text-[13px] text-muted-foreground"
            >
              {row}
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {showBody ? (
          <motion.div
            key="activity-details"
            id={detailsId}
            layout={!reduceMotion}
            initial={reduceMotion ? false : { opacity: 0, height: 0, y: -2 }}
            animate={{ opacity: 1, height: "auto", y: 0 }}
            exit={reduceMotion ? { opacity: 1 } : { opacity: 0, height: 0, y: -2 }}
            transition={transition}
            className="mt-1.5 overflow-hidden border-l border-border/60 pl-3"
          >
            {needsConfirmation ? (
              <p className="mb-2 flex items-center gap-1.5 text-[12px] text-warning">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {localize(lang, "Требуется подтверждение для продолжения", "Confirmation is required to continue")}
              </p>
            ) : hasError ? (
              <p className="mb-2 flex items-center gap-1.5 text-[12px] text-destructive">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {localize(lang, "Один из шагов завершился с ошибкой", "One of the steps failed")}
              </p>
            ) : null}

            {toolSteps.length > 0 ? (
              <ul className="max-h-48 space-y-1 overflow-y-auto pr-1 text-[12px] text-muted-foreground">
                {toolSteps.slice(-8).map((step) => {
                  const preview = step.status === "running" ? "" : safeToolPreview(step.preview);
                  const stepElapsed = step.startedAt
                    ? formatElapsed(Math.max(0, (step.completedAt ?? now) - step.startedAt))
                    : "";
                  const statusLabel =
                    step.status === "running"
                      ? localize(lang, "Выполняется", "Running")
                      : step.status === "done"
                        ? localize(lang, "Готово", "Done")
                        : localize(lang, "Ошибка", "Failed");
                  return (
                    <li
                      key={step.id}
                      className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-x-2 rounded-md py-1 transition-colors [transition-duration:120ms]"
                    >
                      <span className="mt-0.5 flex h-4 w-4 items-center justify-center" aria-hidden="true">
                        {step.status === "running" ? (
                          <Loader2
                            className={cn("h-3 w-3 opacity-65", !reduceMotion && "animate-spin")}
                          />
                        ) : step.status === "done" ? (
                          <Check className="h-3 w-3 text-success/80" />
                        ) : (
                          <AlertCircle className="h-3 w-3 text-destructive" />
                        )}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-mono text-[11px] text-foreground/75">
                          {step.name}
                        </span>
                        {preview ? (
                          <span className="mt-0.5 block break-words text-[11px] leading-4 text-muted-foreground/70">
                            {preview}
                          </span>
                        ) : null}
                      </span>
                      <span
                        className={cn(
                          "text-[10px]",
                          step.status === "error" ? "text-destructive" : "text-muted-foreground/55",
                        )}
                      >
                        <span className="block">{statusLabel}</span>
                        {stepElapsed ? (
                          <span className="mt-0.5 block text-right font-mono tabular-nums opacity-75">
                            {stepElapsed}
                          </span>
                        ) : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  );
});
