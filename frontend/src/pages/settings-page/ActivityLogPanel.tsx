import { format, subDays } from "date-fns";
import { Activity, CalendarIcon, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ActivityLogEvent } from "@/lib/api";
import { CATEGORY_ICONS, DATE_PRESETS, relativeTime } from "./constants";
import { SectionCard } from "./SectionCard";

type ActivityLogPanelProps = {
  activitySearch: string;
  activityDays: number;
  dateFrom: Date | undefined;
  dateTo: Date | undefined;
  filteredActivity: ActivityLogEvent[];
  onSearchChange: (value: string) => void;
  onActivityDaysChange: (value: number) => void;
  onDateFromChange: (date: Date | undefined) => void;
  onDateToChange: (date: Date | undefined) => void;
};

export function ActivityLogPanel({
  activitySearch,
  activityDays,
  dateFrom,
  dateTo,
  filteredActivity,
  onSearchChange,
  onActivityDaysChange,
  onDateFromChange,
  onDateToChange,
}: ActivityLogPanelProps) {
  return (
    <SectionCard title="Журнал действий" icon={Activity} description="Полная история действий пользователей на платформе">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[240px] xl:max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={activitySearch}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Поиск по пользователю, действию..."
              className="pl-9 h-8 text-xs"
            />
          </div>

          <div className="flex items-center gap-1">
            {DATE_PRESETS.map((preset) => (
              <Button
                key={preset.days}
                size="sm"
                variant={activityDays === preset.days ? "default" : "outline"}
                className="h-7 text-[10px] px-2"
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

          <div className="flex items-center gap-1.5">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="h-7 text-[10px] gap-1 px-2">
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
                  className="p-3 pointer-events-auto"
                />
              </PopoverContent>
            </Popover>
            <span className="text-[10px] text-muted-foreground">—</span>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="h-7 text-[10px] gap-1 px-2">
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
                  className="p-3 pointer-events-auto"
                />
              </PopoverContent>
            </Popover>
          </div>

          <Badge variant="outline" className="text-[10px] shrink-0">
            {filteredActivity.length} записей
          </Badge>
        </div>

        <div className="rounded-lg border border-border overflow-hidden">
          <div className="max-h-[500px] overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-card z-10">
                <tr className="text-[10px] text-muted-foreground uppercase border-b border-border">
                  <th className="px-3 py-2 text-left font-medium w-10">Тип</th>
                  <th className="px-3 py-2 text-left font-medium">Пользователь</th>
                  <th className="px-3 py-2 text-left font-medium">Действие</th>
                  <th className="px-3 py-2 text-left font-medium">Описание</th>
                  <th className="px-3 py-2 text-right font-medium w-20">Время</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {filteredActivity.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      Нет записей за выбранный период
                    </td>
                  </tr>
                ) : (
                  filteredActivity.map((event, index) => {
                    const CatIcon = CATEGORY_ICONS[event.category] || Activity;
                    return (
                      <tr key={index} className="hover:bg-muted/20 transition-colors">
                        <td className="px-3 py-2">
                          <div className="h-6 w-6 rounded bg-muted/40 flex items-center justify-center">
                            <CatIcon className="h-3 w-3 text-muted-foreground" />
                          </div>
                        </td>
                        <td className="px-3 py-2 font-medium text-foreground whitespace-nowrap">{event.username}</td>
                        <td className="px-3 py-2">
                          <Badge variant="outline" className="text-[9px] font-normal">{event.action}</Badge>
                        </td>
                        <td className="px-3 py-2 text-muted-foreground max-w-xs truncate">{event.description || "—"}</td>
                        <td className="px-3 py-2 text-right text-muted-foreground whitespace-nowrap">
                          {relativeTime(event.timestamp || event.created_at || "")}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
