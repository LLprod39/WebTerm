"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { cx } from "@/boardui/utils/cx";

export type AgentProgressStep = {
  id?: string | number;
  label: string;
  status?: "pending" | "running" | "done" | "error";
};

type Props = {
  steps: Array<string | AgentProgressStep>;
  /** Auto-advance demo timing (ms). Ignored when steps carry explicit status. */
  stepDuration?: number;
  completionDelay?: number;
  onFinished?: () => void;
  className?: string;
  defaultExpanded?: boolean;
};

function normalize(steps: Array<string | AgentProgressStep>): AgentProgressStep[] {
  return steps.map((step, index) =>
    typeof step === "string" ? { id: index, label: step, status: "pending" } : { status: "pending", ...step },
  );
}

function Ring({
  progress,
  size = 16,
  stroke = 2.5,
}: {
  progress: number;
  size?: number;
  stroke?: number;
}) {
  const r = size / 2 - stroke;
  return (
    <svg
      aria-hidden
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      className="shrink-0 -rotate-90"
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--color-border-button-default)"
        strokeWidth={stroke}
      />
      <circle
        data-progress-ring="true"
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--color-agent-progress-ring)"
        strokeWidth={stroke}
        strokeLinecap="round"
        pathLength={1}
        strokeDasharray={`${Math.max(0, Math.min(1, progress))} 1`}
      />
    </svg>
  );
}

/** BoardUI Pro Agent Progress — visual recreate on WebTerm tokens. */
export function AgentProgress({
  steps: rawSteps,
  stepDuration = 2400,
  completionDelay = 1000,
  onFinished,
  className,
  defaultExpanded = true,
}: Props) {
  const reduceMotion = useReducedMotion();
  const controlled = useMemo(
    () => rawSteps.some((step) => typeof step !== "string" && step.status && step.status !== "pending"),
    [rawSteps],
  );
  const base = useMemo(() => normalize(rawSteps), [rawSteps]);
  const [autoIndex, setAutoIndex] = useState(0);
  const [expanded, setExpanded] = useState(defaultExpanded);

  useEffect(() => {
    if (controlled || reduceMotion) return;
    if (autoIndex >= base.length) {
      const t = window.setTimeout(() => onFinished?.(), completionDelay);
      return () => window.clearTimeout(t);
    }
    const t = window.setTimeout(() => setAutoIndex((v) => v + 1), stepDuration);
    return () => window.clearTimeout(t);
  }, [autoIndex, base.length, completionDelay, controlled, onFinished, reduceMotion, stepDuration]);

  const steps = base.map((step, index) => {
    if (controlled) return step;
    if (index < autoIndex) return { ...step, status: "done" as const };
    if (index === autoIndex) return { ...step, status: "running" as const };
    return { ...step, status: "pending" as const };
  });

  const doneCount = steps.filter((s) => s.status === "done").length;
  const running = steps.find((s) => s.status === "running");
  const left = Math.max(0, steps.length - doneCount - (running ? 0 : 0));
  const overall = steps.length ? (doneCount + (running ? 0.45 : 0)) / steps.length : 0;

  return (
    <div
      className={cx(
        "relative w-full max-w-full overflow-hidden rounded-2xl border border-border-button-default bg-background-primary-default shadow-xs",
        className,
      )}
      aria-live="polite"
      data-testid="agent-progress"
    >
      <span className="pointer-events-none absolute top-[14px] start-[14px] z-20 flex size-4 items-center justify-center">
        <Ring progress={overall} />
      </span>

      <div className="flex h-10 items-center justify-between gap-2 px-2.5 ps-10">
        <span className="min-w-0 truncate text-body-medium text-text-secondary">
          {left > 0
            ? `${left} step${left === 1 ? "" : "s"} left`
            : "All steps complete"}
        </span>
        <button
          type="button"
          aria-label={expanded ? "Minimize steps" : "Expand steps"}
          aria-expanded={expanded}
          className="size-5 cursor-pointer rounded-sm transition-opacity duration-200 hover:opacity-80"
          onClick={() => setExpanded((v) => !v)}
        >
          <span aria-hidden className="relative block size-5 shrink-0">
            <span className="absolute top-px start-px size-[18px] rounded-sm bg-background-quaternary-default" />
            <span className="absolute top-[13px] start-1 h-0.5 w-3 rounded-[3px] bg-foreground-icon-secondary" />
          </span>
        </button>
      </div>

      <AnimatePresence initial={false}>
        {expanded ? (
          <motion.div
            key="expanded"
            data-testid="agent-progress-expanded"
            initial={reduceMotion ? false : { height: 0, opacity: 0, filter: "blur(3px)" }}
            animate={{ height: "auto", opacity: 1, filter: "blur(0px)" }}
            exit={reduceMotion ? undefined : { height: 0, opacity: 0, filter: "blur(3px)" }}
            transition={{ duration: reduceMotion ? 0 : 0.28 }}
            className="overflow-hidden px-2.5 pb-2.5"
          >
            <div className="mt-1 flex flex-col gap-1.5">
              {steps.map((step) => {
                const active = step.status === "running";
                const done = step.status === "done";
                return (
                  <div key={String(step.id ?? step.label)} className="h-8 w-full">
                    <div className="relative flex h-full w-full items-center gap-2 rounded-full px-1">
                      {active ? (
                        <span
                          aria-hidden
                          className="pointer-events-none absolute inset-0 rounded-full border border-border-button-default"
                        />
                      ) : null}
                      <span className="relative z-10 flex size-3.5 shrink-0 items-center justify-center">
                        {active ? (
                          <Ring progress={0.55} size={14} stroke={1.5} />
                        ) : done ? (
                          <svg aria-hidden viewBox="0 0 14 14" className="size-3.5 text-[var(--color-agent-progress-ring)]">
                            <circle cx="7" cy="7" r="6" fill="currentColor" opacity="0.15" />
                            <path
                              d="M4.2 7.1 L6.1 9 L9.8 5.2"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        ) : (
                          <svg aria-hidden viewBox="0 0 15 15" className="size-[15px]">
                            <circle
                              cx="7.5"
                              cy="7.5"
                              r="7"
                              fill="none"
                              stroke="var(--color-background-quaternary-default)"
                              strokeDasharray="2 2"
                            />
                          </svg>
                        )}
                      </span>
                      <span
                        className={cx(
                          "relative z-10 min-w-0 flex-1 truncate text-body-medium leading-5 transition-colors duration-300",
                          active || done ? "text-text-primary" : "text-text-secondary",
                          active && "agent-progress-loading-text",
                        )}
                        aria-label={step.label}
                      >
                        {step.label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
