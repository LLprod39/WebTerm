import type { Dispatch, SetStateAction } from "react";
import {
  BookOpen,
  Brain,
  CalendarDays,
  CheckCircle2,
  Layers,
  Server,
  Settings2,
  Shield,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type {
  AgentInputArtifact,
  AgentScheduleConfig,
  AgentScheduleMode,
  AgentTemplate,
  FrontendServer,
  StudioSkill,
} from "@/lib/api";
import { localize } from "@/lib/i18n";

import {
  AGENT_ICONS,
  type AgentSudoPolicy,
  type AgentTaskDraft,
  type AgentWizardStep,
  FULL_AGENT_TOOL_OPTIONS,
  QUICK_TIMES,
  SCHEDULE_MODES,
  SCHEDULE_PRESETS,
  SUDO_AGENT_OPTIONS,
  WEEKDAYS,
  agentModeLabel,
  buildDefaultToolsConfig,
  finalizeScheduleConfig,
  formatScheduleConfigLabel,
  sudoAgentOption,
} from "./agentPageUtils";
import { AgentMaterialsSection } from "./AgentMaterialsSection";
import { AgentWizardQuickSummary } from "./AgentWizardQuickSummary";

type SummaryRow = { icon: LucideIcon; label: string; value: string };
type AgentMode = "mini" | "full" | "multi";
type StateSetter<T> = Dispatch<SetStateAction<T>>;

type AgentWizardStepContentProps = {
  step: AgentWizardStep;
  lang: string;
  t: (key: string) => string;
  mode: AgentMode;
  setMode: StateSetter<AgentMode>;
  templates: AgentTemplate[];
  onSelectTemplate: (template: AgentTemplate) => void;
  setSelectedType: StateSetter<string>;
  setStep: StateSetter<AgentWizardStep>;
  name: string;
  setName: StateSetter<string>;
  commands: string;
  setCommands: StateSetter<string>;
  aiPrompt: string;
  setAiPrompt: StateSetter<string>;
  goal: string;
  setGoal: StateSetter<string>;
  systemPrompt: string;
  setSystemPrompt: StateSetter<string>;
  maxIter: number;
  setMaxIter: StateSetter<number>;
  sessionTimeoutSeconds: number;
  setSessionTimeoutSeconds: StateSetter<number>;
  maxConnections: number;
  setMaxConnections: StateSetter<number>;
  sudoPolicy: AgentSudoPolicy;
  setSudoPolicy: StateSetter<AgentSudoPolicy>;
  servers: FrontendServer[];
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
  enabledToolCount: number;
  toolsConfig: Record<string, boolean>;
  setToolsConfig: StateSetter<Record<string, boolean>>;
  toolsExpanded: boolean;
  setToolsExpanded: StateSetter<boolean>;
  stopConditionsText: string;
  setStopConditionsText: StateSetter<string>;
  selectedSkillSlugs: string[];
  availableSkills: StudioSkill[];
  visibleSkills: StudioSkill[];
  toggleSkill: (slug: string) => void;
  skillsExpanded: boolean;
  setSkillsExpanded: StateSetter<boolean>;
  inputArtifacts: AgentInputArtifact[];
  activeArtifact: AgentInputArtifact | null;
  activeArtifactIndex: number | null;
  setActiveArtifactIndex: StateSetter<number | null>;
  addArtifact: (kind: AgentInputArtifact["kind"]) => void;
  removeArtifact: (index: number) => void;
  updateArtifact: (index: number, patch: Partial<AgentInputArtifact>) => void;
  updateArtifactTask: (artifactIndex: number, taskIndex: number, patch: Partial<AgentTaskDraft>) => void;
  addArtifactTask: (artifactIndex: number) => void;
  removeArtifactTask: (artifactIndex: number, taskIndex: number) => void;
  onMaterialFiles: (files: FileList | null) => void | Promise<void>;
  telegramEnabled: boolean;
  setTelegramEnabled: StateSetter<boolean>;
  telegramChatId: string;
  setTelegramChatId: StateSetter<string>;
  summaryRows: SummaryRow[];
  commandCount: number;
};

export function AgentWizardStepContent(props: AgentWizardStepContentProps) {
  const {
    step,
    lang,
    t,
    mode,
    setMode,
    templates,
    onSelectTemplate,
    setSelectedType,
    setStep,
    name,
    setName,
    commands,
    setCommands,
    aiPrompt,
    setAiPrompt,
    goal,
    setGoal,
    systemPrompt,
    setSystemPrompt,
    maxIter,
    setMaxIter,
    sessionTimeoutSeconds,
    setSessionTimeoutSeconds,
    maxConnections,
    setMaxConnections,
    sudoPolicy,
    setSudoPolicy,
    servers,
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
    enabledToolCount,
    toolsConfig,
    setToolsConfig,
    toolsExpanded,
    setToolsExpanded,
    stopConditionsText,
    setStopConditionsText,
    selectedSkillSlugs,
    availableSkills,
    visibleSkills,
    toggleSkill,
    skillsExpanded,
    setSkillsExpanded,
    inputArtifacts,
    activeArtifact,
    activeArtifactIndex,
    setActiveArtifactIndex,
    addArtifact,
    removeArtifact,
    updateArtifact,
    updateArtifactTask,
    addArtifactTask,
    removeArtifactTask,
    onMaterialFiles,
    telegramEnabled,
    setTelegramEnabled,
    telegramChatId,
    setTelegramChatId,
    summaryRows,
    commandCount,
  } = props;

  return (
    <div className={step === "template" ? "space-y-4" : "grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]"}>
      <div className="space-y-4">
        {step === "template" && (
          <>
            <section className="rounded-lg border border-border/70 bg-secondary/15 p-4">
              <h3 className="mb-4 text-lg font-semibold text-foreground">{localize(lang, "Тип агента", "Agent type")}</h3>
              <div className="grid gap-3 md:grid-cols-3">
                {[
                  { key: "mini" as const, icon: Zap, label: localize(lang, "Mini-агент", "Mini Agent"), text: localize(lang, "Команды и краткий разбор", "Commands and short analysis") },
                  { key: "full" as const, icon: Brain, label: localize(lang, "Полный агент", "Full Agent"), text: localize(lang, "Цель, инструменты и проверки", "Goal, tools, and checks") },
                  { key: "multi" as const, icon: Layers, label: "Pipeline", text: localize(lang, "Несколько агентов и серверов", "Multiple agents and servers") },
                ].map((item) => {
                  const Icon = item.icon;
                  const active = mode === item.key;
                  return (
                    <button key={item.key} type="button" aria-pressed={active} onClick={() => setMode(item.key)} className={`min-h-[92px] rounded-lg border p-4 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/30 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                      <span className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-primary"><Icon className="h-4 w-4" /></span>
                      <span className="block text-sm font-semibold">{item.label}</span>
                      <span className="mt-1 block text-xs text-muted-foreground">{item.text}</span>
                    </button>
                  );
                })}
              </div>
            </section>
            <section className="rounded-lg border border-border/70 bg-secondary/15 p-4">
              <div className="mb-4">
                <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Шаблон", "Template")}</h3>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                <button
                  type="button"
                  onClick={() => { setSelectedType("custom"); setStep("basics"); }}
                  className="min-h-[104px] rounded-lg border border-dashed border-primary/35 bg-primary/5 p-4 text-left transition-colors hover:border-primary/60 hover:bg-primary/10"
                >
                  <div className="mb-3 flex items-center gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                      <Settings2 className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 truncate text-sm font-semibold text-foreground">{localize(lang, "Вручную", "Custom")}</span>
                  </div>
                  <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                    {localize(lang, "Создать агента без шаблона", "Create an agent without a template")}
                  </p>
                </button>
                {templates.map((tpl) => {
                  const TemplateIcon = AGENT_ICONS[tpl.type] || Settings2;
                  return (
                    <button key={tpl.type} type="button" onClick={() => onSelectTemplate(tpl)} className="min-h-[104px] rounded-lg border border-border/70 bg-background/30 p-4 text-left transition-colors hover:border-primary/50 hover:bg-primary/5">
                      <div className="mb-3 flex items-center gap-3">
                        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-primary"><TemplateIcon className="h-4 w-4" /></span>
                        <span className="min-w-0 truncate text-sm font-semibold text-foreground">{tpl.name}</span>
                      </div>
                      <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{tpl.mode === "full" ? (tpl.goal || localize(lang, "Автономная OPS-задача", "Autonomous OPS task")) : localize(lang, `${tpl.command_count} команд`, `${tpl.command_count} commands`)}</p>
                    </button>
                  );
                })}
              </div>
            </section>
          </>
        )}

        {step === "basics" && (
          <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
            <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Основные настройки", "Basics")}</h3>
            <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
              <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Название агента", "Agent name")} <span className="text-primary">*</span></label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={localize(lang, "Анализ логов", "Log analysis")} className="h-10 bg-background/60" />
            </div>
            {mode === "mini" ? (
              <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                <label className="pt-2 text-sm font-medium text-muted-foreground">{t("agent.commands_label")} <span className="text-primary">*</span></label>
                <Textarea value={commands} onChange={(e) => setCommands(e.target.value)} rows={7} className="bg-background/60 font-mono text-xs" placeholder={"hostname\nuptime\nfree -m"} />
              </div>
            ) : (
              <>
                <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                  <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Цель", "Goal")}</label>
                  <Textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} className="bg-background/60 text-sm" />
                </div>
                <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                  <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Системные инструкции", "System instructions")}</label>
                  <Textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={3} className="bg-background/60 text-sm" />
                </div>
                <div className="grid gap-3 lg:grid-cols-3 lg:pl-[236px]">
                  <Input type="number" min={1} max={100} value={maxIter} onChange={(e) => setMaxIter(Number(e.target.value))} className="h-10 bg-background/60" aria-label={localize(lang, "Максимум итераций", "Max iterations")} />
                  <Input type="number" min={30} max={3600} value={sessionTimeoutSeconds} onChange={(e) => setSessionTimeoutSeconds(Number(e.target.value))} className="h-10 bg-background/60" aria-label={localize(lang, "Таймаут сессии", "Session timeout")} />
                  <Input type="number" min={1} max={10} value={maxConnections} onChange={(e) => setMaxConnections(Number(e.target.value))} className="h-10 bg-background/60" aria-label={localize(lang, "Максимум подключений", "Max connections")} />
                </div>
              </>
            )}
            <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
              <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Инструкции к анализу", "Analysis instructions")}</label>
              <Textarea value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} rows={4} className="bg-background/60 text-sm" />
            </div>
            <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
              <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Права запуска", "Run access")}</label>
              <div className="grid gap-3 md:grid-cols-3">
                {SUDO_AGENT_OPTIONS.map((option) => {
                  const active = sudoPolicy === option.value;
                  return (
                    <button key={option.value} type="button" aria-pressed={active} onClick={() => setSudoPolicy(option.value)} className={`min-h-[76px] rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/30 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                      <Shield className="mb-2 h-4 w-4 text-primary" />
                      <span className="block text-sm font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </section>
        )}

        {step === "servers" && (
          <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Выбор серверов", "Server selection")}</h3>
              <button type="button" onClick={selectAll} className={`min-h-9 rounded-md border px-3 text-sm font-semibold transition-colors ${hasAllServersSelected ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{hasAllServersSelected ? localize(lang, "Снять выбор", "Clear") : localize(lang, "Выбрать все", "Select all")}</button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {servers.map((server) => {
                const active = selectedServers.includes(server.id);
                return (
                  <button key={server.id} type="button" aria-pressed={active} onClick={() => toggleServer(server.id)} className={`flex min-h-[64px] items-center gap-3 rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/30 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-muted-foreground"><Server className="h-4 w-4" /></span>
                    <span className="min-w-0 flex-1 truncate text-sm font-semibold">{server.name}</span>
                    {active && <CheckCircle2 className="h-5 w-5 shrink-0 text-primary" />}
                  </button>
                );
              })}
            </div>
            <div className="space-y-4 rounded-lg border border-border/70 bg-background/25 p-4">
              <div className="flex items-center justify-between gap-3">
                <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground"><CalendarDays className="h-4 w-4 text-primary" /> {t("agent.schedule")}</h4>
                <span className="rounded-md border border-primary/25 bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">{formatScheduleConfigLabel(scheduleConfig, schedule, lang)}</span>
              </div>
              <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                {SCHEDULE_MODES.map((option) => {
                  const active = scheduleConfig.mode === option.mode;
                  return (
                    <button key={option.mode} type="button" aria-pressed={active} onClick={() => setScheduleMode(option.mode)} className={`min-h-[76px] rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/30 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                      <span className="block text-sm font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                      <span className="mt-1 block text-[11px] text-muted-foreground">{localize(lang, option.hintRu, option.hintEn)}</span>
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
        )}

        {step === "capabilities" && (
          <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
            <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Возможности", "Capabilities")}</h3>
            {(mode === "full" || mode === "multi") && (
              <div className="space-y-3 rounded-lg border border-border/70 bg-background/25 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <h4 className="text-sm font-semibold text-foreground">{localize(lang, "Доступ к инструментам", "Tool access")}</h4>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {localize(lang, `${enabledToolCount} из ${FULL_AGENT_TOOL_OPTIONS.length} включено`, `${enabledToolCount} of ${FULL_AGENT_TOOL_OPTIONS.length} enabled`)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button type="button" className="min-h-8 rounded-md px-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/10" onClick={() => setToolsConfig(buildDefaultToolsConfig())}>{localize(lang, "Включить все", "Enable all")}</button>
                    <button type="button" className="min-h-8 rounded-md border border-border/70 px-3 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground" onClick={() => setToolsExpanded((current) => !current)}>
                      {toolsExpanded ? localize(lang, "Свернуть", "Collapse") : localize(lang, "Развернуть", "Expand")}
                    </button>
                  </div>
                </div>
                {toolsExpanded && (
                  <>
                    <div className="grid gap-2 md:grid-cols-2">
                      {FULL_AGENT_TOOL_OPTIONS.map((tool) => (
                        <label key={tool.key} className="flex min-h-10 items-center gap-2 rounded-md border border-border/70 bg-background/35 px-3 text-xs text-muted-foreground">
                          <input type="checkbox" checked={Boolean(toolsConfig[tool.key])} onChange={(event) => setToolsConfig((current) => ({ ...current, [tool.key]: event.target.checked }))} />
                          {tool.label}
                        </label>
                      ))}
                    </div>
                    <Textarea value={stopConditionsText} onChange={(e) => setStopConditionsText(e.target.value)} rows={3} className="bg-background/60 text-xs" placeholder={localize(lang, "Условия остановки", "Stop conditions")} />
                  </>
                )}
              </div>
            )}
            <div className="space-y-3 rounded-lg border border-border/70 bg-background/25 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground"><BookOpen className="h-4 w-4 text-primary" /> {localize(lang, "Скиллы агента", "Agent skills")}</h4>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {localize(lang, `${selectedSkillSlugs.length} выбрано · ${availableSkills.length} доступно`, `${selectedSkillSlugs.length} selected · ${availableSkills.length} available`)}
                  </p>
                </div>
                {availableSkills.length > 4 && (
                  <button type="button" className="min-h-8 shrink-0 rounded-md border border-border/70 px-3 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground" onClick={() => setSkillsExpanded((current) => !current)}>
                    {skillsExpanded ? localize(lang, "Свернуть", "Collapse") : localize(lang, "Показать все", "Show all")}
                  </button>
                )}
              </div>
              {availableSkills.length ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {visibleSkills.map((skill) => {
                    const active = selectedSkillSlugs.includes(skill.slug);
                    return (
                      <button key={skill.slug} type="button" aria-pressed={active} onClick={() => toggleSkill(skill.slug)} className={`min-h-[58px] rounded-lg border px-3 py-2 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/35 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                        <span className="block truncate text-xs font-semibold">{skill.name}</span>
                        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{skill.service || skill.category || skill.slug}</span>
                      </button>
                    );
                  })}
                </div>
              ) : <div className="rounded-lg border border-dashed border-border/70 px-3 py-3 text-xs text-muted-foreground">{localize(lang, "Доступных скиллов пока нет.", "No available skills yet.")}</div>}
            </div>
            <AgentMaterialsSection
              lang={lang}
              inputArtifacts={inputArtifacts}
              activeArtifact={activeArtifact}
              activeArtifactIndex={activeArtifactIndex}
              setActiveArtifactIndex={setActiveArtifactIndex}
              addArtifact={addArtifact}
              removeArtifact={removeArtifact}
              updateArtifact={updateArtifact}
              updateArtifactTask={updateArtifactTask}
              addArtifactTask={addArtifactTask}
              removeArtifactTask={removeArtifactTask}
              onMaterialFiles={onMaterialFiles}
              telegramEnabled={telegramEnabled}
              setTelegramEnabled={setTelegramEnabled}
              telegramChatId={telegramChatId}
              setTelegramChatId={setTelegramChatId}
            />
          </section>
        )}

        {step === "review" && (
          <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
            <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Обзор", "Review")}</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {summaryRows.map((row) => {
                const Icon = row.icon;
                return (
                  <div key={row.label} className="rounded-lg border border-border/70 bg-background/30 p-4">
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-primary"><Icon className="h-4 w-4" /></div>
                    <div className="text-xs text-muted-foreground">{row.label}</div>
                    <div className="mt-1 text-sm font-semibold text-foreground">{row.value}</div>
                  </div>
                );
              })}
            </div>
            <div className="rounded-lg border border-border/70 bg-background/30 p-4">
              <div className="grid gap-3 text-sm md:grid-cols-4">
                <div><span className="block text-xs text-muted-foreground">{localize(lang, "Команды", "Commands")}</span><strong>{commandCount}</strong></div>
                <div><span className="block text-xs text-muted-foreground">{localize(lang, "Скиллы", "Skills")}</span><strong>{selectedSkillSlugs.length}</strong></div>
                <div><span className="block text-xs text-muted-foreground">{localize(lang, "Материалы", "Materials")}</span><strong>{inputArtifacts.length}</strong></div>
                <div><span className="block text-xs text-muted-foreground">Telegram</span><strong>{telegramEnabled ? localize(lang, "Да", "Yes") : localize(lang, "Нет", "No")}</strong></div>
              </div>
            </div>
          </section>
        )}
      </div>

      {step !== "template" && (
        <AgentWizardQuickSummary lang={lang} summaryRows={summaryRows} />
      )}
    </div>
  );
}
