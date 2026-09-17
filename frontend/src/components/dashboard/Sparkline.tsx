import { useId } from "react";

import { cn } from "@/lib/utils";

/**
 * Tiny dependency-free SVG sparkline: stroke polyline + soft area fill.
 * Colors come from currentColor, so tone is controlled via text-* classes.
 */
export function Sparkline({
  data,
  className,
  strokeWidth = 1.5,
  width = 120,
  height = 32,
}: {
  data: number[];
  className?: string;
  strokeWidth?: number;
  width?: number;
  height?: number;
}) {
  const gradientId = useId();

  if (data.length < 2) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className={cn("block w-full", className)} aria-hidden>
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="currentColor"
          strokeWidth={strokeWidth}
          strokeDasharray="3 3"
          opacity={0.35}
        />
      </svg>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pad = strokeWidth;
  const innerHeight = height - pad * 2;

  const points = data.map((value, index) => {
    const x = (index / (data.length - 1)) * width;
    const y = pad + innerHeight - ((value - min) / span) * innerHeight;
    return [x, y] as const;
  });
  const polyline = points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `0,${height} ${polyline} ${width},${height}`;
  const last = points[points.length - 1];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={cn("block w-full", className)} preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity={0.25} />
          <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#${gradientId})`} />
      <polyline points={polyline} fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r={strokeWidth + 0.5} fill="currentColor" />
    </svg>
  );
}
