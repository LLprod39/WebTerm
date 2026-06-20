import { SeverityBadge } from "./SeverityBadge";
import { report } from "@/data/mockReport";
import { Sparkles, Server, Box, Clock, Timer, CalendarCheck } from "lucide-react";

const metaItems = [
  { icon: Server, label: "Сервер", value: report.meta.server },
  { icon: Box, label: "Контейнер", value: report.meta.container },
  { icon: Clock, label: "Окно", value: report.meta.window },
  { icon: Timer, label: "Длительность анализа", value: report.meta.analysisDuration },
  { icon: CalendarCheck, label: "Завершено", value: report.meta.finishedAt },
];

export function Hero() {
  return (
    <section className="report-card overflow-hidden p-6 sm:p-7">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={report.severity} variant="solid" size="md" />
        <span className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-1.5 text-sm font-medium text-primary">
          <Sparkles className="h-4 w-4" />
          Уверенность AI {report.confidence}%
        </span>
      </div>

      <h1 className="mt-4 text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-3xl">
        {report.title}
      </h1>
      <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-muted-foreground">
        {report.subtitle}
      </p>

      {/* Confidence meter */}
      <div className="mt-5 max-w-xs">
        <div className="mb-1.5 flex items-center justify-between text-xs text-muted-foreground">
          <span>Уверенность модели</span>
          <span className="font-medium text-foreground">{report.confidence}%</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full rounded-full bg-primary"
            style={{ width: `${report.confidence}%` }}
          />
        </div>
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-border pt-5 sm:grid-cols-3 lg:grid-cols-5">
        {metaItems.map((m) => {
          const Icon = m.icon;
          return (
            <div key={m.label} className="min-w-0">
              <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Icon className="h-3.5 w-3.5" />
                {m.label}
              </dt>
              <dd className="mt-1 truncate font-mono text-sm font-medium text-foreground">
                {m.value}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
