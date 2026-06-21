import type { Dispatch, SetStateAction } from "react";
import { format, subDays } from "date-fns";
import { Activity, CalendarIcon, Download, Search } from "lucide-react";

import type { ActivityLogEvent } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { useI18n } from "@/lib/i18n";
import { CATEGORY_ICONS, DATE_PRESET_KEYS, relativeTime } from "./auditSettingsModel";

type AuditActivityTabProps = {
  activitySearch: string;
  activityDays: number;
  dateFrom?: Date;
  dateTo?: Date;
  filteredActivity: ActivityLogEvent[];
  onActivitySearchChange: (value: string) => void;
  onActivityDaysChange: (value: number) => void;
  onDateFromChange: Dispatch<SetStateAction<Date | undefined>>;
  onDateToChange: Dispatch<SetStateAction<Date | undefined>>;
};

function csvCell(value: unknown) {
  const text = String(value ?? "").replace(/\r?\n/g, " ");
  return `"${text.replace(/"/g, '""')}"`;
}

function exportActivityCsv(events: ActivityLogEvent[]) {
  const rows = [
    ["time", "user", "category", "action", "description"],
    ...events.map((event) => [
      event.timestamp || event.created_at || "",
      event.username || "",
      event.category || "",
      event.action || "",
      event.description || "",
    ]),
  ];
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `audit-activity-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function ActivityCards({ events }: { events: ActivityLogEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="rounded-lg border border-border px-3 py-8 text-center text-sm text-muted-foreground">
        Нет записей за выбранный период
      </div>
    );
  }

  return (
    <>
      {events.slice(0, 30).map((event, index) => {
        const CategoryIcon = CATEGORY_ICONS[event.category || ""] || Activity;
        return (
          <div key={`${event.id ?? index}`} className="rounded-lg border border-border/70 bg-background/40 px-3 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground">{relativeTime(event.timestamp || event.created_at || "")}</span>
                  <span className="text-xs font-medium text-foreground">{event.username || "—"}</span>
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <CategoryIcon className="h-3 w-3 shrink-0" />
                  <span>{event.category || "—"}</span>
                </div>
              </div>
              <Badge variant="secondary" className="shrink-0 text-xs">{event.action || "—"}</Badge>
            </div>
            <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">
              {event.description || "—"}
            </p>
          </div>
        );
      })}
    </>
  );
}

function ActivityTable({ events }: { events: ActivityLogEvent[] }) {
  return (
    <div className="hidden overflow-hidden rounded-lg border border-border md:block">
      <div className="max-h-[500px] overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b border-border text-xs uppercase text-muted-foreground">
              <th className="px-3 py-2 text-left font-medium">Время</th>
              <th className="px-3 py-2 text-left font-medium">Пользователь</th>
              <th className="px-3 py-2 text-left font-medium">Категория</th>
              <th className="px-3 py-2 text-left font-medium">Действие</th>
              <th className="px-3 py-2 text-left font-medium">Описание</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">
                  Нет записей за выбранный период
                </td>
              </tr>
            ) : (
              events.map((event, index) => {
                const CategoryIcon = CATEGORY_ICONS[event.category || ""] || Activity;
                return (
                  <tr key={`${event.id ?? index}`} className="border-b border-border/50 transition-colors hover:bg-muted/30">
                    <td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground">
                      {relativeTime(event.timestamp || event.created_at || "")}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="font-medium text-foreground">{event.username || "—"}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <CategoryIcon className="h-3 w-3 text-muted-foreground" />
                        <span className="text-muted-foreground">{event.category || "—"}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge variant="secondary" className="text-xs">{event.action || "—"}</Badge>
                    </td>
                    <td className="max-w-[300px] truncate px-3 py-2.5 text-muted-foreground">
                      {event.description || "—"}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AuditActivityTab({
  activitySearch,
  activityDays,
  dateFrom,
  dateTo,
  filteredActivity,
  onActivitySearchChange,
  onActivityDaysChange,
  onDateFromChange,
  onDateToChange,
}: AuditActivityTabProps) {
  const { t } = useI18n();
  const datePresets = DATE_PRESET_KEYS.map((preset) => ({ ...preset, label: t(preset.labelKey) }));

  return (
    <SectionCard title={t("audit.activity_log")} icon={Activity} description={t("audit.activity_desc")}>
      <div className="space-y-4">
        <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
          <div className="relative min-w-0 flex-1 md:min-w-[240px] xl:max-w-md">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={activitySearch}
              onChange={(event) => onActivitySearchChange(event.target.value)}
              placeholder={t("audit.search_placeholder")}
              className="h-10 pl-9"
            />
          </div>

          <div className="flex max-w-full items-center gap-1 overflow-x-auto pb-1 md:pb-0">
            {datePresets.map((preset) => (
              <Button
                key={preset.days}
                size="sm"
                variant={activityDays === preset.days ? "default" : "outline"}
                className="h-10 px-3 text-xs"
                onClick={() => {
                  onActivityDaysChange(preset.days);
                  onDateFromChange(subDays(new Date(), preset.days || 0));
                  onDateToChange(new Date());
                }}
              >
                {preset.label}
              </Button>
            ))}
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="h-10 gap-1 px-3 text-xs">
                  <CalendarIcon className="h-3 w-3" />
                  {dateFrom ? format(dateFrom, "dd.MM.yy") : "От"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="single"
                  selected={dateFrom}
                  onSelect={onDateFromChange}
                  disabled={(date) => date > new Date()}
                  className="pointer-events-auto p-3"
                />
              </PopoverContent>
            </Popover>
            <span className="text-xs text-muted-foreground">—</span>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="h-10 gap-1 px-3 text-xs">
                  <CalendarIcon className="h-3 w-3" />
                  {dateTo ? format(dateTo, "dd.MM.yy") : "До"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="single"
                  selected={dateTo}
                  onSelect={onDateToChange}
                  disabled={(date) => date > new Date()}
                  className="pointer-events-auto p-3"
                />
              </PopoverContent>
            </Popover>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-10 gap-1.5"
            onClick={() => exportActivityCsv(filteredActivity)}
            disabled={!filteredActivity.length}
          >
            <Download className="h-4 w-4" />
            CSV
          </Button>

          <Badge variant="outline" className="shrink-0 text-xs">
            {filteredActivity.length} записей
          </Badge>
        </div>

        <div className="space-y-2 md:hidden">
          <ActivityCards events={filteredActivity} />
        </div>
        <ActivityTable events={filteredActivity} />
      </div>
    </SectionCard>
  );
}
