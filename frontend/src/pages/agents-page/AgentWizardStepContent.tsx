import type { Dispatch, SetStateAction } from "react";
import { BookOpen, Brain, CalendarDays, CheckCircle2, Layers, Server, Settings2, Shield, Search, Terminal, type LucideIcon } from "lucide-react";
import { InlineAlert } from "@/components/system/InlineAlert";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { AgentInputArtifact, AgentScheduleConfig, AgentScheduleMode, AgentTemplate, FrontendServer, StudioSkill } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  AGENT_BUDGET_PROFILES,
  AGENT_ICONS,
  type AgentBudgetProfileId,
  type AgentSudoPolicy,
  type AgentTaskDraft,
  type AgentWizardCheck,
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
  resolveBudgetProfileId,
  sudoAgentOption,
} from "./agentPageUtils";
import { AgentMaterialsSection } from "./AgentMaterialsSection";
import { AgentWizardReviewStep } from "./AgentWizardReviewStep";
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
  sudoRiskAcknowledged: boolean;
  setSudoRiskAcknowledged: StateSetter<boolean>;
  summaryRows: SummaryRow[];
  commandCount: number;
  readiness: number;
  readinessChecks: AgentWizardCheck[];
  runAfterSave?: boolean;
  setRunAfterSave?: StateSetter<boolean>;
  isEditing?: boolean;
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
    sudoRiskAcknowledged,
    setSudoRiskAcknowledged,
    summaryRows,
    commandCount,
    readiness,
    readinessChecks,
    runAfterSave = true,
    setRunAfterSave,
    isEditing = false,
  } = props;

  return (
    <div className="space-y-6">
      <div className="space-y-6">
        {step === "template" && (
          <>
            <section className="space-y-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  {localize(lang, "Тип агента", "Agent type")}
                </h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {localize(
                    lang,
                    "Выберите, как агент будет работать. От этого зависят доступные поля и поведение.",
                    "Choose how the agent works. This determines the available fields and its behaviour.",
                  )}
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {[
                  {
                    key: "mini" as const,
                    icon: Terminal,
                    label: localize(lang, "Mini-агент", "Mini Agent"),
                    text: localize(lang, "Выполняет заданный список команд и делает краткий разбор результата.", "Runs a fixed list of commands and briefly analyses the result."),
                    when: localize(lang, "Быстрый старт · без worker", "Quick start · no worker"),
                    accent: "text-primary border-primary/30 bg-primary/10",
                  },
                  {
                    key: "full" as const,
                    icon: Brain,
                    label: localize(lang, "Полный агент", "Full Agent"),
                    text: localize(lang, "Сам решает шаги к цели, используя инструменты и проверки.", "Decides the steps toward a goal on its own, using tools and checks."),
                    when: localize(lang, "Когда нужна автономность", "When autonomy is needed"),
                    accent: "text-ai border-ai/30 bg-ai/10",
                  },
                  {
                    key: "multi" as const,
                    icon: Layers,
                    label: localize(lang, "Мульти-агент", "Multi-agent"),
                    text: localize(lang, "Координирует несколько агентов и серверов в одном сценарии.", "Coordinates several agents and servers in one scenario."),
                    when: localize(lang, "Когда задача многошаговая", "When the task is multi-step"),
                    accent: "text-info border-info/30 bg-info/10",
                  },
                ].map((item) => {
                  const Icon = item.icon;
                  const active = mode === item.key;
                  return (
                    <button
                      key={item.key}
                      type="button"
                      aria-pressed={active}
                      onClick={() => setMode(item.key)}
                      className={cn(
                        "flex min-h-[120px] flex-col rounded-sm border p-4 text-left transition-colors",
                        active
                          ? "border-primary bg-primary/10 text-foreground shadow-elev-1"
                          : "border-border bg-surface-1 text-muted-foreground hover:border-primary/45 hover:text-foreground",
                      )}
                    >
                      <span className={cn("mb-3 flex h-9 w-9 items-center justify-center rounded-sm border", item.accent)}>
                        <Icon className="h-4 w-4" />
                      </span>
                      <span className="block text-sm font-semibold text-foreground">{item.label}</span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">{item.text}</span>
                      <span className="mt-auto pt-2 text-2xs font-medium uppercase tracking-wide text-primary/80">{item.when}</span>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="space-y-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  {localize(lang, "Шаблон", "Template")}
                </h3>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedType("custom");
                    setStep("basics");
                  }}
                  className="min-h-[104px] rounded-sm border border-dashed border-primary/40 bg-primary/5 p-4 text-left transition-colors hover:border-primary hover:bg-primary/10"
                >
                  <div className="mb-3 flex items-center gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-primary/30 bg-primary/10 text-primary">
                      <Settings2 className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 truncate text-sm font-semibold text-foreground">
                      {localize(lang, "Вручную", "Custom")}
                    </span>
                  </div>
                  <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                    {localize(lang, "Создать агента без шаблона", "Create an agent without a template")}
                  </p>
                </button>
                {templates.map((tpl) => {
                  const TemplateIcon = AGENT_ICONS[tpl.type] || Settings2;
                  return (
                    <button
                      key={tpl.type}
                      type="button"
                      onClick={() => onSelectTemplate(tpl)}
                      className="min-h-[104px] rounded-sm border border-border bg-surface-1 p-4 text-left transition-colors hover:border-primary/50 hover:bg-primary/5"
                    >
                      <div className="mb-3 flex items-center gap-3">
                        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-2 text-primary">
                          <TemplateIcon className="h-4 w-4" />
                        </span>
                        <span className="min-w-0 truncate text-sm font-semibold text-foreground">{tpl.name}</span>
                      </div>
                      <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                        {tpl.mode === "full" || tpl.mode === "multi"
                          ? (tpl.goal || localize(lang, "Автономная OPS-задача", "Autonomous OPS task"))
                          : localize(lang, `${tpl.command_count} команд`, `${tpl.command_count} commands`)}
                      </p>
                    </button>
                  );
                })}
              </div>
            </section>
          </>
        )}
        {step === "basics" && (
          <section className="space-y-4">
            <h3 className="text-sm font-semibold text-foreground">
              {localize(lang, "Основные настройки", "Basics")}
            </h3>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                {localize(lang, "Название агента", "Agent name")} <span className="text-primary">*</span>
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={localize(lang, "Анализ логов", "Log analysis")}
                className="h-10"
              />
            </div>
            {mode === "mini" ? (
              <div className="space-y-2">
                <div>
                  <label className="text-sm font-medium text-foreground">{t("agent.commands_label")} <span className="text-primary">*</span></label>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Каждая команда — с новой строки. Агент выполнит их по порядку.", "One command per line. The agent runs them in order.")}</p>
                </div>
                <Textarea value={commands} onChange={(e) => setCommands(e.target.value)} rows={7} className="font-mono text-xs" placeholder={"hostname\nuptime\nfree -m"} />
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <div>
                    <label className="text-sm font-medium text-foreground">
                      {localize(lang, "Цель", "Goal")}
                    </label>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {localize(lang, "Что агент должен сделать — желаемый результат.", "What the agent should achieve — the desired outcome.")}
                    </p>
                  </div>
                  <Textarea
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    rows={3}
                    className="text-sm"
                    placeholder={localize(
                      lang,
                      "Например: найти причину высокой нагрузки на web-prod-01",
                      "e.g. find the cause of high load on web-prod-01",
                    )}
                  />
                </div>
                <div className="space-y-2">
                  <div className="pt-2">
                    <label className="text-sm font-medium text-foreground">{localize(lang, "Инструкции (поведение)", "Instructions (behaviour)")}</label>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Как агенту себя вести: роль, стиль, ограничения.", "How the agent should behave: role, style, constraints.")}</p>
                  </div>
                  <Textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={3} className="bg-background/60 text-sm" placeholder={localize(lang, "Например: действуй осторожно, ничего не меняй без подтверждения", "e.g. act carefully, do not change anything without confirmation")} />
                </div>
                <div className="space-y-2">
                  <div className="pt-1">
                    <label className="text-sm font-medium text-foreground">{localize(lang, "Профиль бюджета", "Budget profile")}</label>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {localize(
                        lang,
                        "Для сложных задач выберите «Сложная» (60 шагов / 30 мин). Можно уточнить числа ниже.",
                        "For complex ops pick Complex (60 steps / 30 min). Fine-tune numbers below if needed.",
                      )}
                    </p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3">
                    {(Object.keys(AGENT_BUDGET_PROFILES) as AgentBudgetProfileId[]).map((id) => {
                      const profile = AGENT_BUDGET_PROFILES[id];
                      const active = resolveBudgetProfileId(maxIter, sessionTimeoutSeconds) === id;
                      return (
                        <button
                          key={id}
                          type="button"
                          aria-pressed={active}
                          onClick={() => {
                            setMaxIter(profile.maxIterations);
                            setSessionTimeoutSeconds(profile.sessionTimeoutSeconds);
                            setToolsConfig((prev) => ({
                              ...prev,
                              // Backend also accepts numeric timeout keys via tools_config payload.
                              command_timeout: profile.commandTimeout as unknown as boolean,
                              command_timeout_seconds: profile.commandTimeout as unknown as boolean,
                            }));
                          }}
                          className={`min-h-[72px] rounded-lg border p-3 text-left transition-colors ${
                            active
                              ? "border-primary bg-primary/10 text-foreground"
                              : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"
                          }`}
                        >
                          <div className="text-xs font-semibold">{lang === "ru" ? profile.labelRu : profile.labelEn}</div>
                          <div className="mt-1 text-[11px] leading-snug opacity-90">{lang === "ru" ? profile.descRu : profile.descEn}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="text-xs font-medium text-muted-foreground">
                    {localize(lang, "Максимум итераций", "Max iterations")}
                    <Input type="number" min={1} max={100} value={maxIter} onChange={(e) => setMaxIter(Number(e.target.value))} className="mt-1 h-9 bg-background/60" />
                  </label>
                  <label className="text-xs font-medium text-muted-foreground">
                    {localize(lang, "Таймаут сессии, сек", "Session timeout, sec")}
                    <Input type="number" min={30} max={3600} value={sessionTimeoutSeconds} onChange={(e) => setSessionTimeoutSeconds(Number(e.target.value))} className="mt-1 h-9 bg-background/60" />
                  </label>
                  <label className="text-xs font-medium text-muted-foreground">
                    {localize(lang, "Максимум подключений", "Max connections")}
                    <Input type="number" min={1} max={10} value={maxConnections} onChange={(e) => setMaxConnections(Number(e.target.value))} className="mt-1 h-9 bg-background/60" />
                  </label>
                </div>
                {mode === "multi" ? (
                  <p className="text-xs leading-5 text-muted-foreground">
                    {localize(
                      lang,
                      "Мульти-агент — оркестратор с планом и subagents (не Studio Graph). Для инцидентов/деплоя предпочтительнее Полный или Мульти с профилем «Сложная».",
                      "Multi-agent is an orchestrated plan with subagents (not Studio Graph). Prefer Full or Multi with the Complex budget for incidents/deploys.",
                    )}
                  </p>
                ) : null}
              </>
            )}
            <div className="space-y-2">
              <div className="pt-2">
                <label className="text-sm font-medium text-foreground">{localize(lang, "Инструкции к анализу", "Analysis instructions")}</label>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Как разобрать и оформить результат выполнения.", "How to interpret and format the run's results.")}</p>
              </div>
              <Textarea value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} rows={4} className="bg-background/60 text-sm" />
            </div>
            <div className="space-y-2">
              <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Права запуска", "Run access")}</label>
              <div className="grid gap-3 md:grid-cols-3">
                {SUDO_AGENT_OPTIONS.map((option) => {
                  const active = sudoPolicy === option.value;
                  return (
                    <button key={option.value} type="button" aria-pressed={active} onClick={() => setSudoPolicy(option.value)} className={`min-h-[76px] rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                      <Shield className="mb-2 h-4 w-4 text-primary" />
                      <span className="block text-sm font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                      <span className="mt-1 block text-xs leading-4 text-muted-foreground">{localize(lang, option.hintRu, option.hintEn)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
            {sudoPolicy === "approved" ? (
              <label className="grid gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm leading-5 text-foreground sm:grid-cols-[auto_1fr]">
                <input
                  type="checkbox"
                  checked={sudoRiskAcknowledged}
                  onChange={(event) => setSudoRiskAcknowledged(event.target.checked)}
                  className="mt-1"
                />
                <span>
                  {localize(
                    lang,
                    "Я понимаю, что агент сможет запускать разрешённые команды с sudo в рамках выбранных серверов.",
                    "I understand this agent can run approved sudo commands within the selected server scope.",
                  )}
                </span>
              </label>
            ) : null}
          </section>
        )}
        {step === "servers" && (
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
        )}
        {step === "capabilities" && (
          <section className="space-y-4">
            <h3 className="text-sm font-semibold text-foreground">{localize(lang, "Возможности", "Capabilities")}</h3>
            {(mode === "full" || mode === "multi") && (
              <div className="space-y-3 border-t border-border/50 pt-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <h4 className="text-sm font-semibold text-foreground">{localize(lang, "Доступ к инструментам", "Tool access")}</h4>
                    <p className="mt-1 text-xs leading-4 text-muted-foreground">
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
            <div className="space-y-3 border-t border-border/50 pt-4">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground"><BookOpen className="h-4 w-4 text-primary" /> {localize(lang, "Скиллы агента", "Agent skills")}</h4>
                    <p className="mt-1 text-xs leading-4 text-muted-foreground">
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
                      <button key={skill.slug} type="button" aria-pressed={active} onClick={() => toggleSkill(skill.slug)} className={`min-h-[58px] rounded-lg border px-3 py-2 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                        <span className="block truncate text-xs font-semibold">{skill.name}</span>
                        <span className="mt-0.5 block truncate text-xs leading-4 text-muted-foreground">{skill.service || skill.category || skill.slug}</span>
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
          <AgentWizardReviewStep
            lang={lang}
            summaryRows={summaryRows}
            commandCount={commandCount}
            selectedSkillSlugs={selectedSkillSlugs}
            inputArtifacts={inputArtifacts}
            telegramEnabled={telegramEnabled}
            readiness={readiness}
            readinessChecks={readinessChecks}
            runAfterSave={runAfterSave}
            setRunAfterSave={setRunAfterSave}
            isEditing={isEditing}
          />
        )}
      </div>
    </div>
  );
}
