"use client";

import { useState } from "react";
import { Link } from "react-router-dom";
import { RiArrowRightUpLine, RiArrowDownSLine } from "@remixicon/react";
import { cx } from "@/boardui/utils/cx";

export type AgentLimitsSegment = {
  label: string;
  tokens: number;
  color?: string;
  deferred?: boolean;
};

export type AgentLimitsGroup = {
  label: string;
  tokens: number;
  items: Array<{ label: string; tokens: number }>;
};

export type AgentLimitsContext = {
  max: number;
  segments: AgentLimitsSegment[];
  groups?: AgentLimitsGroup[];
};

export type AgentPlanLimit = {
  label: string;
  used: number;
  resets: string;
};

type Props = {
  context: AgentLimitsContext;
  plan?: string;
  planHref?: string;
  limits?: AgentPlanLimit[];
  defaultExpanded?: boolean;
  onExpandedChange?: (open: boolean) => void;
  className?: string;
};

function formatTokens(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}k`;
  return String(value);
}

const SEGMENT_COLORS = [
  "var(--color-chart-6)",
  "var(--color-chart-5)",
  "var(--color-chart-3)",
  "var(--color-chart-8)",
  "var(--color-chart-7)",
  "var(--color-chart-4)",
  "var(--color-chart-1)",
  "var(--color-chart-2)",
];

/** BoardUI Pro Agent Limits Card — visual recreate on WebTerm tokens. */
export function AgentLimitsCard({
  context,
  plan = "Operator",
  planHref = "/settings/ai",
  limits = [],
  defaultExpanded = false,
  onExpandedChange,
  className,
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const counted = context.segments.filter((s) => !s.deferred);
  const used = counted.reduce((sum, s) => sum + s.tokens, 0);
  const pct = context.max > 0 ? Math.min(100, Math.round((used / context.max) * 100)) : 0;

  const setOpen = (open: boolean) => {
    setExpanded(open);
    onExpandedChange?.(open);
  };

  return (
    <section
      className={cx(
        "flex w-full min-w-0 flex-col rounded-2xl bg-background-secondary-default px-4 pt-2.5 pb-4",
        className,
      )}
      data-testid="agent-limits-card"
    >
      <button
        type="button"
        aria-expanded={expanded}
        className="group -mx-2 flex cursor-pointer items-center justify-between gap-3 rounded-2lg px-2 py-1 text-start outline-none transition-colors duration-150 hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
        onClick={() => setOpen(!expanded)}
      >
        <span className="text-body-medium text-text-secondary">Context window</span>
        <span className="flex items-center gap-2">
          <span className="text-body-medium whitespace-nowrap text-text-secondary tabular-nums">
            {formatTokens(used)} / {formatTokens(context.max)}{" "}
            <span className="text-text-primary">({pct}%)</span>
          </span>
          <RiArrowDownSLine
            className={cx(
              "size-4 shrink-0 text-text-tertiary transition-transform duration-200 ease-out group-hover:text-text-secondary",
              expanded && "rotate-180",
            )}
          />
        </span>
      </button>

      <div className="mt-1.5 flex h-1.5 w-full gap-px overflow-hidden rounded-full bg-chart-track">
        {counted.map((segment, index) => {
          const width = context.max > 0 ? (segment.tokens / context.max) * 100 : 0;
          return (
            <div
              key={segment.label}
              className="h-full shrink-0 transition-[width] duration-500 ease-out"
              style={{
                width: `${width}%`,
                backgroundColor: segment.color || SEGMENT_COLORS[index % SEGMENT_COLORS.length],
              }}
              title={`${segment.label} · ${formatTokens(segment.tokens)}`}
            />
          );
        })}
      </div>

      {expanded ? (
        <div className="mt-3 space-y-2">
          {context.segments.map((segment, index) => (
            <div key={segment.label} className="flex items-center justify-between gap-3 text-body-2-regular">
              <span className="flex min-w-0 items-center gap-2 text-text-secondary">
                <span
                  className="size-2.5 shrink-0 rounded-sm"
                  style={{ backgroundColor: segment.color || SEGMENT_COLORS[index % SEGMENT_COLORS.length] }}
                />
                <span className="truncate">
                  {segment.label}
                  {segment.deferred ? " (deferred)" : ""}
                </span>
              </span>
              <span className="tabular-nums text-text-primary">{formatTokens(segment.tokens)}</span>
            </div>
          ))}
          {(context.groups || []).map((group) => (
            <details key={group.label} className="rounded-xl bg-background-primary-default px-2.5 py-2">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-body-2-medium text-text-secondary">
                <span>{group.label}</span>
                <span className="tabular-nums text-text-primary">{formatTokens(group.tokens)}</span>
              </summary>
              <ul className="mt-2 space-y-1 border-t border-border-button-default/50 pt-2">
                {group.items.map((item) => (
                  <li key={item.label} className="flex justify-between gap-2 text-caption-1-regular text-text-tertiary">
                    <span className="truncate">{item.label}</span>
                    <span className="tabular-nums">{formatTokens(item.tokens)}</span>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      ) : null}

      <div className="my-3 h-px w-full bg-separator-border-strong" />

      <div className="flex items-center justify-between gap-3 py-1">
        <span className="text-body-medium text-text-secondary">
          Plan usage limits · {plan}
        </span>
        <Link
          to={planHref}
          aria-label="Manage plan"
          className="flex size-6 items-center justify-center rounded-md text-text-tertiary outline-none transition-colors duration-150 hover:bg-background-secondary-hover hover:text-text-secondary focus-visible:ring-2 focus-visible:ring-border-focus-ring"
        >
          <RiArrowRightUpLine className="size-4 rtl:rotate-180" />
        </Link>
      </div>

      <div className="flex flex-col gap-3 pt-1">
        {limits.map((limit) => (
          <div key={limit.label} className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate text-body-medium text-text-primary">{limit.label}</span>
              <span className="flex shrink-0 items-baseline gap-2">
                <span className="text-body-regular text-text-tertiary">{limit.resets}</span>
                <span className="w-9 text-end text-body-medium text-text-primary tabular-nums">
                  {Math.round(limit.used * 100)}%
                </span>
              </span>
            </div>
            <div className="flex h-1.5 w-full gap-px overflow-hidden rounded-full bg-chart-track">
              <div
                className="h-full rounded-full transition-[width] duration-500 ease-out"
                style={{
                  width: `${Math.min(100, Math.max(0, limit.used * 100))}%`,
                  backgroundColor: "var(--color-chart-6)",
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
