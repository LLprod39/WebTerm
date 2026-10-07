"use client";

import { useState } from "react";
import { cx } from "@/boardui/utils/cx";

export type ActivityRing = {
  id: string;
  label: string;
  valueLabel: string;
  /** 0–1 progress */
  progress: number;
  color?: string;
};

type Props = {
  title?: string;
  rings?: ActivityRing[];
  className?: string;
};

const DEFAULT_RINGS: ActivityRing[] = [
  { id: "move", label: "Move", valueLabel: "420 kcal", progress: 0.82, color: "var(--color-chart-3)" },
  { id: "exercise", label: "Exercise", valueLabel: "1h 45m", progress: 0.6, color: "var(--color-chart-2)" },
  { id: "running", label: "Running", valueLabel: "5.2 km", progress: 0.75, color: "var(--color-chart-4)" },
];

/** BoardUI Pro Activity Rings Card — visual recreate on WebTerm tokens. */
export function ActivityRingsCard({
  title = "Activity",
  rings = DEFAULT_RINGS,
  className,
}: Props) {
  const [focus, setFocus] = useState<string | null>(null);
  const radii = [82, 58, 34];

  return (
    <section
      className={cx(
        "flex w-full flex-col gap-3 rounded-2xl border border-border-button-default bg-background-primary-default p-4 shadow-xs",
        className,
      )}
      data-testid="activity-rings-card"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-body-medium text-text-primary">{title}</h3>
      </div>

      <div className="flex flex-wrap gap-2">
        {rings.slice(0, 3).map((ring) => (
          <button
            key={ring.id}
            type="button"
            className={cx(
              "flex min-w-[6.5rem] flex-1 flex-col items-start justify-end gap-px rounded-2lg bg-background-inner-default px-2.5 py-2 text-left transition-opacity duration-200 ease-out",
              focus && focus !== ring.id && "opacity-45",
            )}
            onMouseEnter={() => setFocus(ring.id)}
            onMouseLeave={() => setFocus(null)}
            onFocus={() => setFocus(ring.id)}
            onBlur={() => setFocus(null)}
          >
            <div className="flex items-center gap-1.5">
              <span
                className="size-3 shrink-0 rounded-[4px]"
                style={{ backgroundColor: ring.color || "var(--color-chart-3)" }}
              />
              <span className="text-body-regular whitespace-nowrap text-text-secondary">{ring.label}</span>
            </div>
            <span className="text-body-medium whitespace-nowrap text-text-primary">{ring.valueLabel}</span>
          </button>
        ))}
      </div>

      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        <svg
          viewBox="0 0 200 200"
          className="h-full max-h-[210px] w-full overflow-visible"
          role="img"
          aria-label={rings.map((r) => `${r.label} ${Math.round(r.progress * 100)}%`).join(", ")}
        >
          {rings.slice(0, 3).map((ring, index) => {
            const r = radii[index] ?? 34;
            const pct = Math.max(0, Math.min(100, Math.round(ring.progress * 100)));
            const dimmed = Boolean(focus && focus !== ring.id);
            const color = ring.color || `var(--color-chart-${index + 2})`;
            return (
              <g
                key={ring.id}
                className="cursor-pointer"
                transform="rotate(-90 100 100)"
                onMouseEnter={() => setFocus(ring.id)}
                onMouseLeave={() => setFocus(null)}
              >
                <circle
                  cx="100"
                  cy="100"
                  r={r}
                  fill="none"
                  stroke={color}
                  strokeWidth="18"
                  opacity={dimmed ? 0.08 : 0.16}
                  className="transition-opacity duration-200 ease-out"
                />
                <circle
                  cx="100"
                  cy="100"
                  r={r}
                  pathLength="100"
                  fill="none"
                  stroke={color}
                  strokeWidth="18"
                  strokeLinecap="round"
                  strokeDasharray={`${pct} ${100 - pct}`}
                  opacity={dimmed ? 0.35 : 1}
                  className="transition-[stroke,stroke-dasharray,opacity] duration-200 ease-out"
                />
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}
