import { useState } from "react";
import { timeline } from "@/data/mockReport";
import { severityMeta, type Severity } from "@/lib/severity";
import { SeverityBadge } from "./SeverityBadge";
import { cn } from "@/lib/utils";
import { Copy, Check, ListFilter } from "lucide-react";
import { toast } from "sonner";

const filters: { key: Severity | "all"; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "fatal", label: "Критич." },
  { key: "high", label: "Высокие" },
  { key: "info", label: "Инфо" },
];

export function Timeline() {
  const [filter, setFilter] = useState<Severity | "all">("all");
  const [copied, setCopied] = useState<string | null>(null);

  const matches = (s: Severity) =>
    filter === "all" ||
    s === filter ||
    (filter === "fatal" && s === "critical") ||
    (filter === "high" && s === "warning");

  const visible = timeline.filter((e) => matches(e.severity));

  const copy = (e: (typeof timeline)[number]) => {
    navigator.clipboard?.writeText(`${e.time} [${e.source}] ${e.raw}`);
    setCopied(e.id);
    toast.success("Строка скопирована");
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <div className="report-card p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-foreground">Хронология событий</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">Последовательность инцидента</p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1">
          <ListFilter className="ml-1.5 h-3.5 w-3.5 text-muted-foreground" />
          {filters.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                filter === f.key
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <ol className="mt-5 space-y-0">
        {visible.map((e, i) => {
          const meta = severityMeta[e.severity];
          const Icon = meta.icon;
          return (
            <li key={e.id} className="group relative flex gap-4 pb-5 last:pb-0">
              {/* line */}
              {i < visible.length - 1 && (
                <span className="absolute left-[15px] top-8 h-[calc(100%-1rem)] w-px bg-border" />
              )}
              <div
                className={cn(
                  "z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
                  meta.chip,
                )}
              >
                <Icon className="h-4 w-4" />
              </div>

              <div className="min-w-0 flex-1 rounded-lg border border-transparent px-3 py-1.5 transition-colors group-hover:border-border group-hover:bg-surface/60">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-medium text-foreground">{e.time}</span>
                  <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                    {e.source}
                  </span>
                  <SeverityBadge severity={e.severity} />
                  <button
                    onClick={() => copy(e)}
                    className="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted-foreground opacity-0 transition hover:bg-secondary hover:text-foreground focus:opacity-100 group-hover:opacity-100"
                    aria-label="Скопировать строку"
                  >
                    {copied === e.id ? (
                      <Check className="h-3.5 w-3.5 text-success" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
                <p className="mt-1 text-sm text-foreground">{e.message}</p>
                <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">{e.object}</p>
              </div>
            </li>
          );
        })}
        {visible.length === 0 && (
          <li className="py-6 text-center text-sm text-muted-foreground">Нет событий выбранной важности</li>
        )}
      </ol>
    </div>
  );
}
