/** Tiny SVG sparkline for metrics strips. */
export function Sparkline({
  points,
  width = 120,
  height = 36,
  stroke = "hsl(var(--primary))",
  fill = "hsl(var(--primary) / 0.12)",
}: {
  points: number[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: string;
}) {
  const data = points.length ? points : [0, 0];
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = Math.max(1e-6, max - min);
  const coords = data.map((v, i) => {
    const x = (i / Math.max(1, data.length - 1)) * width;
    const y = height - ((v - min) / span) * (height - 4) - 2;
    return [x, y] as const;
  });
  const line = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <path d={area} fill={fill} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** Deterministic pseudo-series from a seed for empty/live-missing states. */
export function seededSeries(seed: number, length = 16, base = 40, swing = 25): number[] {
  let s = Math.abs(seed) || 1;
  const out: number[] = [];
  for (let i = 0; i < length; i += 1) {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    const noise = (s % 1000) / 1000;
    out.push(base + Math.sin(i / 2.2) * swing + noise * swing * 0.4);
  }
  return out;
}
