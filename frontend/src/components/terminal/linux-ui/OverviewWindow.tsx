import { Button } from "@/components/ui/button";
import type { LinuxUiCapabilities, LinuxUiOverview } from "@/lib/api";
import { capabilityPills, formatMetric, formatUptime } from "@/components/terminal/linux-ui/linuxUiFormat";

export function OverviewWindow({
  overview,
  capabilities,
  onOpenFiles,
  onOpenServices,
  onOpenDisk,
  onOpenLogs,
}: {
  overview: LinuxUiOverview | undefined;
  capabilities: LinuxUiCapabilities | undefined;
  onOpenFiles: () => void;
  onOpenServices: () => void;
  onOpenDisk: () => void;
  onOpenLogs: () => void;
}) {
  const pills = capabilityPills(capabilities);
  const cards = [
    { label: "Сервер", value: overview?.hostname || "Нет данных", hint: overview?.os_name || "Linux server" },
    { label: "Аптайм", value: formatUptime(overview?.uptime_seconds ?? null), hint: overview?.kernel || "Kernel unknown" },
    {
      label: "Нагрузка",
      value: overview ? `${formatMetric(overview.load.one, "", 2)} / ${formatMetric(overview.load.five, "", 2)}` : "Нет данных",
      hint: "1 мин / 5 мин",
    },
    {
      label: "Память",
      value: overview?.memory.percent != null ? `${overview.memory.percent.toFixed(1)}%` : "Нет данных",
      hint: overview?.memory.used_mb != null && overview.memory.total_mb != null ? `${overview.memory.used_mb} / ${overview.memory.total_mb} MB` : "Использование недоступно",
    },
    {
      label: "Диск",
      value: overview?.disk.percent != null ? `${overview.disk.percent.toFixed(1)}%` : "Нет данных",
      hint: overview?.disk.used_gb != null && overview.disk.total_gb != null ? `${overview.disk.used_gb} / ${overview.disk.total_gb} GB` : "Корневая файловая система",
    },
    { label: "Процессы", value: overview?.process_count != null ? String(overview.process_count) : "Нет данных", hint: overview?.cwd || "Рабочий каталог" },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-wrap gap-1.5">
          {pills.length > 0 ? (
            pills.map((pill) => (
              <span key={pill} className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                {pill}
              </span>
            ))
          ) : (
            <span className="text-xs text-muted-foreground">Collecting environment markers...</span>
          )}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="grid gap-3">
          {cards.map((card) => (
            <div key={card.label} className="rounded-2xl border border-border/70 bg-background/90 p-3">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">{card.label}</div>
              <div className="mt-2 text-base font-semibold text-foreground">{card.value}</div>
              <div className="mt-1 text-xs text-muted-foreground">{card.hint}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="border-t border-border/60 bg-secondary/25 px-4 py-3">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <Button type="button" size="sm" variant="outline" className="h-9 text-xs" onClick={onOpenFiles}>
            Файлы
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-9 text-xs" onClick={onOpenServices}>
            Сервисы
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-9 text-xs" onClick={onOpenDisk}>
            Диск
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-9 text-xs" onClick={onOpenLogs}>
            Логи
          </Button>
        </div>
      </div>
    </div>
  );
}
