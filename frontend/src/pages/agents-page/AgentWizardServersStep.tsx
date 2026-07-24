import { CalendarDays, CheckCircle2, Search, Server } from "lucide-react";
import { InlineAlert } from "@/components/system/inlineAlert";
import { Input } from "@/components/ui/input";
import type { AgentScheduleConfig, AgentScheduleMode, FrontendServer } from "@/lib/api";
import { localize } from "@/lib/i18n";
import {
  QUICK_TIMES,
  SCHEDULE_MODES,
  SCHEDULE_PRESETS,
  WEEKDAYS,
  finalizeScheduleConfig,
  formatScheduleConfigLabel,
} from "./agentPageUtils";
import type { StateSetter } from "./agentWizardStepTypes";

type AgentWizardServersStepProps = {
  lang: string;
  t: (key: string) => string;
  servers: FrontendServer[];
  totalServerCount: number;
  serverSearch: string;
  setServerSearch: StateSetter<string>;
  selectedServers: number[];
  toggleServer: (id: number) => void;
  selectAll: () => void;
  hasAllServersSelected: boolean;
  schedule: number;
  setSchedule: StateSetter<number>;
  scheduleConfig: AgentScheduleConfig;
  setScheduleConfig: StateSetter<AgentScheduleConfig>;
  setScheduleMode: (mode: AgentScheduleMode) => void;
  updateSchedule: (patch: Partial<AgentScheduleConfig>) => void;
  toggleWeekday: (day: number) => void;
};

export function AgentWizardServersStep({
  lang,
  t,
  servers,
  totalServerCount,
  serverSearch,
  setServerSearch,
  selectedServers,
  toggleServer,
  selectAll,
  hasAllServersSelected,
  schedule,
  setSchedule,
  scheduleConfig,
  setScheduleConfig,
  setScheduleMode,
  updateSchedule,
  toggleWeekday,
}: AgentWizardServersStepProps) {
  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{localize(lang, "Выбор серверов", "Server selection")}</h3>
          <p className="mt-1 text-sm leading-5 text-muted-foreground">
            {localize(lang, `${selectedServers.length} выбрано из ${totalServerCount}`, `${selectedServers.length} selected of ${totalServerCount}`)}
          </p>
        </div>
        <button type="button" onClick={selectAll} className={`min-h-9 rounded-md border px-3 text-sm font-semibold transition-colors ${hasAllServersSelected ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{hasAllServersSelected ? localize(lang, "Снять выбор", "Clear") : localize(lang, "Выбрать все", "Select all")}</button>
      </div>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={serverSearch}
          onChange={(event) => setServerSearch(event.target.value)}
          placeholder={localize(lang, "Поиск по имени, хосту или группе", "Search by name, host, or group")}
          className="h-10 bg-background/60 pl-9"
        />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {servers.map((server) => {
          const active = selectedServers.includes(server.id);
          return (
            <button key={server.id} type="button" aria-pressed={active} onClick={() => toggleServer(server.id)} className={`flex min-h-[64px] items-center gap-3 rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-muted-foreground"><Server className="h-4 w-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">{server.name}</span>
                <span className="mt-0.5 block truncate text-xs leading-4 text-muted-foreground">{server.host} · {server.group_name}</span>
              </span>
              {active && <CheckCircle2 className="h-5 w-5 shrink-0 text-primary" />}
            </button>
          );
        })}
      </div>
      {!servers.length ? (
        <InlineAlert
          tone="warning"
          description={localize(lang, "Под текущий поиск серверы не найдены.", "No servers match the current search.")}
        />
      ) : null}
      <div className="space-y-4 border-t border-border/50 pt-4">
        <div className="flex items-center justify-between gap-3">
          <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground"><CalendarDays className="h-4 w-4 text-primary" /> {t("agent.schedule")}</h4>
          <span className="rounded-md border border-primary/25 bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">{formatScheduleConfigLabel(scheduleConfig, schedule, lang)}</span>
        </div>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          {SCHEDULE_MODES.map((option) => {
            const active = scheduleConfig.mode === option.mode;
            return (
              <button key={option.mode} type="button" aria-pressed={active} onClick={() => setScheduleMode(option.mode)} className={`min-h-[76px] rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                <span className="block text-sm font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                <span className="mt-1 block text-xs leading-4 text-muted-foreground">{localize(lang, option.hintRu, option.hintEn)}</span>
              </button>
            );
          })}
        </div>
        {scheduleConfig.mode === "interval" && (
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_150px]">
            <div className="grid gap-2 sm:grid-cols-4">
              {SCHEDULE_PRESETS.filter((option) => option.minutes > 0).map((option) => (
                <button key={option.minutes} type="button" aria-pressed={schedule === option.minutes} onClick={() => { setSchedule(option.minutes); setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: "interval", interval_minutes: option.minutes }, option.minutes)); }} className={`min-h-10 rounded-md border px-3 text-sm font-semibold transition-colors ${schedule === option.minutes ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                  {localize(lang, option.labelRu, option.labelEn)}
                </button>
              ))}
            </div>
            <Input type="number" min={1} max={10080} step={5} value={schedule || scheduleConfig.interval_minutes || 60} onChange={(e) => { const value = Math.max(1, Number(e.target.value) || 1); setSchedule(value); setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: "interval", interval_minutes: value }, value)); }} className="h-10 bg-background/60" aria-label={localize(lang, "Интервал запуска в минутах", "Run interval in minutes")} />
          </div>
        )}
        {(["daily", "weekly", "monthly"] as AgentScheduleMode[]).includes(scheduleConfig.mode) && (
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
            <div className="flex flex-wrap gap-2">
              {QUICK_TIMES.map((timeValue) => (
                <button key={timeValue} type="button" onClick={() => updateSchedule({ time: timeValue })} className={`min-h-9 rounded-md border px-3 text-xs font-semibold transition-colors ${scheduleConfig.time === timeValue ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{timeValue}</button>
              ))}
            </div>
            <Input type="time" value={scheduleConfig.time || "09:00"} onChange={(e) => updateSchedule({ time: e.target.value })} className="h-9 bg-background/60" />
          </div>
        )}
        {scheduleConfig.mode === "weekly" && (
          <div className="flex flex-wrap gap-2">
            {WEEKDAYS.map((day) => {
              const active = (scheduleConfig.weekdays || []).includes(day.value);
              return <button key={day.value} type="button" aria-pressed={active} onClick={() => toggleWeekday(day.value)} className={`min-h-9 rounded-md border px-3 text-xs font-semibold transition-colors ${active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{localize(lang, day.ru, day.en)}</button>;
            })}
          </div>
        )}
        {scheduleConfig.mode === "monthly" && <Input type="number" min={1} max={31} value={scheduleConfig.day_of_month || 1} onChange={(e) => updateSchedule({ day_of_month: Math.min(31, Math.max(1, Number(e.target.value) || 1)) })} className="h-9 max-w-32 bg-background/60" />}
        {scheduleConfig.mode === "once" && <Input type="datetime-local" value={scheduleConfig.run_at || ""} onChange={(e) => updateSchedule({ run_at: e.target.value })} className="h-9 max-w-64 bg-background/60" />}
      </div>
    </section>
  );
}
