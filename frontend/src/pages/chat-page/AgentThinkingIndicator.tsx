import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

type Variant = "wave" | "spin" | "stars";

type Props = {
  label?: string;
  startedAt?: number | null;
  variant?: Variant;
  className?: string;
};

const GRID = 3;
const DOT = 4;
const GAP = 2;
const TICK_MS = 80;
const TRAIL = 0.3;
const MIN_OPACITY = 0.12;
const SEED = [0.55, 0.3, 0.15, 0.85, 0.55, 0.3, 1, 0.85, 0.55];

function formatElapsed(ms: number) {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  return `${m}:${String(sec % 60).padStart(2, "0")}`;
}

function scalar(variant: "wave" | "spin", col: number, row: number) {
  const m = GRID - 1;
  if (variant === "wave") return ((col + row) / (2 * m)) * (GRID / (GRID + 1));
  const c = m / 2;
  return (Math.atan2(row - c, col - c) / (2 * Math.PI) + 1) % 1;
}

function opacities(variant: "wave" | "spin", phase: number) {
  return Array.from({ length: GRID * GRID }, (_, i) => {
    const s = scalar(variant, i % GRID, Math.floor(i / GRID));
    const behind = (phase - s + 1) % 1;
    const lit = Math.max(0, 1 - behind / TRAIL) ** 1.5;
    return MIN_OPACITY + (1 - MIN_OPACITY) * lit;
  });
}

function Dots({ variant, reduceMotion }: { variant: "wave" | "spin"; reduceMotion: boolean | null }) {
  const [values, setValues] = useState(SEED);
  useEffect(() => {
    if (reduceMotion) return;
    let phase = 0;
    const id = window.setInterval(() => {
      phase = (phase + 1 / 8) % 1;
      setValues(opacities(variant, phase));
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [variant, reduceMotion]);

  return (
    <span
      aria-hidden
      className="grid shrink-0 text-muted-foreground"
      style={{ gridTemplateColumns: `repeat(${GRID}, ${DOT}px)`, gap: GAP }}
    >
      {values.map((opacity, i) => (
        <span
          key={i}
          className="rounded-[1px] bg-current transition-[opacity] duration-200"
          style={{ width: DOT, height: DOT, opacity }}
        />
      ))}
    </span>
  );
}

const STAR_LAYOUT = [
  { x: 50, y: 46, scale: 1 },
  { x: 18, y: 22, scale: 0.55 },
  { x: 82, y: 26, scale: 0.45 },
  { x: 78, y: 76, scale: 0.55 },
  { x: 22, y: 78, scale: 0.4 },
];

function Stars({ reduceMotion }: { reduceMotion: boolean | null }) {
  const box = 21;
  return (
    <span aria-hidden className="relative block shrink-0 text-muted-foreground" style={{ width: box, height: box }}>
      {STAR_LAYOUT.map((star, i) => {
        const size = 14 * star.scale;
        return (
          <svg
            key={i}
            viewBox="0 0 24 24"
            className={cn("absolute", !reduceMotion && "wt-chat-thinking-star")}
            style={{
              width: size,
              height: size,
              left: `${star.x}%`,
              top: `${star.y}%`,
              marginLeft: -size / 2,
              marginTop: -size / 2,
              animationDelay: `${(i * 1.4 * 0.7) / STAR_LAYOUT.length}s`,
            }}
          >
            <path
              d="M12 0C13 7 17 11 24 12C17 13 13 17 12 24C11 17 7 13 0 12C7 11 11 7 12 0Z"
              fill="currentColor"
            />
          </svg>
        );
      })}
    </span>
  );
}

/** Compact “agent working” cue above the composer (BoardUI AI Chat pattern). */
export function AgentThinkingIndicator({
  label = "Thinking",
  startedAt = null,
  variant = "wave",
  className,
}: Props) {
  const reduceMotion = useReducedMotion();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!startedAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [startedAt]);

  const elapsed = startedAt ? formatElapsed(Math.max(0, now - startedAt)) : "";

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex items-center gap-2 px-1 py-1 text-[13px]", className)}
      data-testid="agent-thinking-indicator"
    >
      {variant === "stars" ? (
        <Stars reduceMotion={reduceMotion} />
      ) : (
        <Dots variant={variant} reduceMotion={reduceMotion} />
      )}
      <span className={cn("tracking-tight", reduceMotion ? "text-muted-foreground" : "wt-chat-thinking-label")}>
        {label}
      </span>
      {elapsed ? (
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground/55">{elapsed}</span>
      ) : null}
    </div>
  );
}
