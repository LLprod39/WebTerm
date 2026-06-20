import { useMemo, useState } from "react";
import { timeline } from "@/data/mockReport";
import { severityMeta, type Severity } from "@/lib/severity";
import { SeverityBadge } from "../SeverityBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Search, Copy } from "lucide-react";
import { toast } from "sonner";

const filters: { key: Severity | "all"; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "fatal", label: "Критич." },
  { key: "high", label: "Высокие" },
  { key: "info", label: "Инфо" },
];

export function EventsTab() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Severity | "all">("all");

  const rows = useMemo(() => {
    return timeline.filter((e) => {
      const matchSev =
        filter === "all" ||
        e.severity === filter ||
        (filter === "fatal" && e.severity === "critical") ||
        (filter === "high" && e.severity === "warning");
      const q = query.trim().toLowerCase();
      const matchQ =
        !q ||
        [e.source, e.message, e.object, e.raw, e.time].some((v) =>
          v.toLowerCase().includes(q),
        );
      return matchSev && matchQ;
    });
  }, [query, filter]);

  return (
    <div className="report-card overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск по источнику, событию, объекту…"
            className="h-10 pl-9"
          />
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1">
          {filters.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
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

      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-3 font-medium">Время</th>
              <th className="px-4 py-3 font-medium">Источник</th>
              <th className="px-4 py-3 font-medium">Событие</th>
              <th className="px-4 py-3 font-medium">Важность</th>
              <th className="px-4 py-3 font-medium">Объект</th>
              <th className="px-4 py-3 text-right font-medium">Действия</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr
                key={e.id}
                className="border-b border-border/60 transition-colors last:border-0 hover:bg-surface/60"
              >
                <td className="whitespace-nowrap px-4 py-3 font-mono text-foreground">{e.time}</td>
                <td className="px-4 py-3">
                  <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                    {e.source}
                  </span>
                </td>
                <td className="px-4 py-3 text-foreground">{e.message}</td>
                <td className="px-4 py-3">
                  <SeverityBadge severity={e.severity} />
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground">
                  {e.object}
                </td>
                <td className="px-4 py-3 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    aria-label="Скопировать строку"
                    onClick={() => {
                      navigator.clipboard?.writeText(`${e.time} [${e.source}] ${e.raw}`);
                      toast.success("Строка скопирована");
                    }}
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  Ничего не найдено
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
        Показано {rows.length} из {timeline.length} событий
      </div>
    </div>
  );
}
