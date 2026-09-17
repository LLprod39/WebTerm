import { localize } from "@/lib/i18n";

const CHART_WIDTH = 700;
const CHART_HEIGHT = 180;
const PLOT_LEFT = 38;
const PLOT_RIGHT = 10;
const PLOT_TOP = 10;
const PLOT_BOTTOM = 32;
const PLOT_WIDTH = CHART_WIDTH - PLOT_LEFT - PLOT_RIGHT;
const PLOT_HEIGHT = CHART_HEIGHT - PLOT_TOP - PLOT_BOTTOM;

interface DailyRun {
  date: string;
  succeeded: number;
  failed: number;
}

interface HourlyActivity {
  hour: string;
  count: number;
}

interface AgentRunsChartProps {
  data: DailyRun[];
  formatDay: (value: unknown) => string;
  lang: string;
}

interface HourlyActivityChartProps {
  data: HourlyActivity[];
  formatHour: (value: unknown) => string;
  lang: string;
}

function safeNumber(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

export function AgentRunsChart({ data, formatDay, lang }: AgentRunsChartProps) {
  const normalized = data.map((item) => ({
    ...item,
    succeeded: safeNumber(item.succeeded),
    failed: safeNumber(item.failed),
  }));
  const maxTotal = Math.max(1, ...normalized.map((item) => item.succeeded + item.failed));
  const slotWidth = PLOT_WIDTH / Math.max(1, normalized.length);
  const barWidth = Math.min(52, slotWidth * 0.58);
  const succeededLabel = localize(lang, "Успешно", "Succeeded");
  const failedLabel = localize(lang, "Сбой", "Failed");

  return (
    <div className="h-full w-full">
      <div className="mb-2 flex flex-wrap justify-end gap-3 text-xs text-muted-foreground" aria-hidden="true">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-success" /> {succeededLabel}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-destructive" /> {failedLabel}
        </span>
      </div>
      <svg
        className="h-[150px] w-full overflow-visible"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={localize(lang, "Запуски агентов по дням", "Agent runs by day")}
      >
        {[0, 0.5, 1].map((ratio) => {
          const y = PLOT_TOP + PLOT_HEIGHT * ratio;
          const value = Math.round(maxTotal * (1 - ratio));
          return (
            <g key={ratio}>
              <line
                x1={PLOT_LEFT}
                x2={CHART_WIDTH - PLOT_RIGHT}
                y1={y}
                y2={y}
                stroke="hsl(var(--border) / 0.55)"
                strokeDasharray="4 4"
                vectorEffect="non-scaling-stroke"
              />
              <text x={PLOT_LEFT - 7} y={y + 4} textAnchor="end" fontSize="12" fill="hsl(var(--muted-foreground))">
                {value}
              </text>
            </g>
          );
        })}
        {normalized.map((item, index) => {
          const succeededHeight = (item.succeeded / maxTotal) * PLOT_HEIGHT;
          const failedHeight = (item.failed / maxTotal) * PLOT_HEIGHT;
          const x = PLOT_LEFT + index * slotWidth + (slotWidth - barWidth) / 2;
          const bottom = PLOT_TOP + PLOT_HEIGHT;
          return (
            <g key={`${item.date}-${index}`}>
              <title>{`${formatDay(item.date)}: ${succeededLabel} ${item.succeeded}; ${failedLabel} ${item.failed}`}</title>
              <rect
                x={x}
                y={bottom - succeededHeight}
                width={barWidth}
                height={succeededHeight}
                rx="2"
                fill="hsl(var(--success))"
              />
              <rect
                x={x}
                y={bottom - succeededHeight - failedHeight}
                width={barWidth}
                height={failedHeight}
                rx="2"
                fill="hsl(var(--destructive))"
              />
              <text
                x={x + barWidth / 2}
                y={CHART_HEIGHT - 9}
                textAnchor="middle"
                fontSize="12"
                fill="hsl(var(--muted-foreground))"
              >
                {formatDay(item.date)}
              </text>
            </g>
          );
        })}
      </svg>
      <table className="sr-only">
        <caption>{localize(lang, "Данные запусков агентов", "Agent run data")}</caption>
        <thead><tr><th>{localize(lang, "День", "Day")}</th><th>{succeededLabel}</th><th>{failedLabel}</th></tr></thead>
        <tbody>
          {normalized.map((item, index) => (
            <tr key={`${item.date}-row-${index}`}><th>{formatDay(item.date)}</th><td>{item.succeeded}</td><td>{item.failed}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function HourlyActivityChart({ data, formatHour, lang }: HourlyActivityChartProps) {
  const normalized = data.map((item) => ({ ...item, count: safeNumber(item.count) }));
  const maxCount = Math.max(1, ...normalized.map((item) => item.count));
  const denominator = Math.max(1, normalized.length - 1);
  const points = normalized.map((item, index) => ({
    ...item,
    x: PLOT_LEFT + (index / denominator) * PLOT_WIDTH,
    y: PLOT_TOP + PLOT_HEIGHT - (item.count / maxCount) * PLOT_HEIGHT,
  }));
  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
  const plotBottom = PLOT_TOP + PLOT_HEIGHT;
  const areaPath = points.length
    ? `${linePath} L${points.at(-1)?.x ?? PLOT_LEFT},${plotBottom} L${points[0].x},${plotBottom} Z`
    : "";
  const labelStep = Math.max(1, Math.ceil(points.length / 6));
  const actionLabel = localize(lang, "Действия", "Actions");

  return (
    <div className="h-full w-full">
      <svg
        className="h-full min-h-[180px] w-full overflow-visible"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={localize(lang, "Активность системы по часам", "Hourly system activity")}
      >
        {[0, 0.5, 1].map((ratio) => {
          const y = PLOT_TOP + PLOT_HEIGHT * ratio;
          return (
            <line
              key={ratio}
              x1={PLOT_LEFT}
              x2={CHART_WIDTH - PLOT_RIGHT}
              y1={y}
              y2={y}
              stroke="hsl(var(--border) / 0.55)"
              strokeDasharray="4 4"
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
        {areaPath ? <path d={areaPath} fill="hsl(var(--primary) / 0.18)" /> : null}
        {linePath ? (
          <path
            d={linePath}
            fill="none"
            stroke="hsl(var(--primary))"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        ) : null}
        {points.map((point, index) => (
          <g key={`${point.hour}-${index}`}>
            <title>{`${formatHour(point.hour)}: ${point.count} ${actionLabel}`}</title>
            <circle cx={point.x} cy={point.y} r="3" fill="hsl(var(--primary))" />
            {index % labelStep === 0 || index === points.length - 1 ? (
              <text
                x={point.x}
                y={CHART_HEIGHT - 8}
                textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}
                fontSize="12"
                fill="hsl(var(--muted-foreground))"
              >
                {formatHour(point.hour)}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
      <table className="sr-only">
        <caption>{localize(lang, "Почасовые данные активности", "Hourly activity data")}</caption>
        <thead><tr><th>{localize(lang, "Время", "Time")}</th><th>{actionLabel}</th></tr></thead>
        <tbody>
          {normalized.map((item, index) => (
            <tr key={`${item.hour}-row-${index}`}><th>{formatHour(item.hour)}</th><td>{item.count}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
