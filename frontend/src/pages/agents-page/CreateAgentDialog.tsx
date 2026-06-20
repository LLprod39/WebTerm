import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Bot, Layers, Save, Server, Shield, Tag } from "lucide-react";
import {
  createAgent,
  fetchAgentTemplates,
  fetchFrontendBootstrap,
  studioSkills,
  updateAgent,
  type AgentInputArtifact,
  type AgentItem,
  type AgentScheduleConfig,
  type AgentScheduleMode,
  type AgentTaskDraft,
  type AgentTemplate,
  type StudioSkill,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AgentWizardProgress } from "./AgentWizardProgress";
import { AgentWizardStepContent } from "./AgentWizardStepContent";
import {
  AGENT_WIZARD_STEPS,
  type AgentSudoPolicy,
  type AgentWizardStep,
  buildDefaultToolsConfig,
  defaultScheduleConfig,
  deriveScheduleMinutes,
  finalizeScheduleConfig,
  HIDDEN_AGENT_TEMPLATE_TYPES,
  agentModeLabel,
  normalizeArtifactDraft,
  prepareArtifactForSave,
  scheduleConfigFromMinutes,
  sudoAgentOption,
} from "./agentPageUtils";

type CreateAgentDialogProps = {
  open: boolean;
  onClose: () => void;
  initialAgent?: AgentItem | null;
  onSaved: (saved: { id: number; mode: "mini" | "full" | "multi"; action: "create" | "update" }) => Promise<void> | void;
};

export function CreateAgentDialog({
  open,
  onClose,
  onSaved,
  initialAgent = null,
}: CreateAgentDialogProps) {
  const { t, lang } = useI18n();
  const isEditing = Boolean(initialAgent);
  const [step, setStep] = useState<AgentWizardStep>("template");
  const [mode, setMode] = useState<"mini" | "full" | "multi">("mini");
  const [selectedType, setSelectedType] = useState("");
  const [name, setName] = useState("");
  const [commands, setCommands] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [goal, setGoal] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [maxIter, setMaxIter] = useState(20);
  const [toolsConfig, setToolsConfig] = useState<Record<string, boolean>>(() => buildDefaultToolsConfig());
  const [sudoPolicy, setSudoPolicy] = useState<AgentSudoPolicy>("disabled");
  const [stopConditionsText, setStopConditionsText] = useState("");
  const [sessionTimeoutSeconds, setSessionTimeoutSeconds] = useState(600);
  const [maxConnections, setMaxConnections] = useState(5);
  const [selectedServers, setSelectedServers] = useState<number[]>([]);
  const [schedule, setSchedule] = useState(0);
  const [scheduleConfig, setScheduleConfig] = useState<AgentScheduleConfig>(() => defaultScheduleConfig());
  const [selectedSkillSlugs, setSelectedSkillSlugs] = useState<string[]>([]);
  const [inputArtifacts, setInputArtifacts] = useState<AgentInputArtifact[]>([]);
  const [activeArtifactIndex, setActiveArtifactIndex] = useState<number | null>(null);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramChatId, setTelegramChatId] = useState("");
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const [skillsExpanded, setSkillsExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  const { data: tplData } = useQuery({ queryKey: ["agents", "templates"], queryFn: fetchAgentTemplates, enabled: open });
  const { data: bootstrapData } = useQuery({ queryKey: ["frontend", "bootstrap"], queryFn: fetchFrontendBootstrap, staleTime: 30_000 });
  const { data: availableSkills = [] } = useQuery<StudioSkill[]>({ queryKey: ["studio", "skills", "agent-picker"], queryFn: studioSkills.list, enabled: open });

  const templates = (tplData?.templates || [])
    .filter((template) => !HIDDEN_AGENT_TEMPLATE_TYPES.has(template.type))
    .filter((template) => template.mode === mode || (mode === "multi" && template.mode === "full"));
  const servers = bootstrapData?.servers || [];
  const allServerIds = servers.map((server) => server.id);
  const activeArtifact = activeArtifactIndex !== null ? inputArtifacts[activeArtifactIndex] : null;
  const currentStepIndex = Math.max(0, AGENT_WIZARD_STEPS.findIndex((item) => item.key === step));
  const commandCount = commands.split("\n").map((item) => item.trim()).filter(Boolean).length;
  const canSave = Boolean((name || selectedType).trim()) && selectedServers.length > 0;

  const resetForm = () => {
    setStep("template");
    setMode("mini");
    setSelectedType("");
    setName("");
    setCommands("");
    setAiPrompt("");
    setGoal("");
    setSystemPrompt("");
    setMaxIter(20);
    setToolsConfig(buildDefaultToolsConfig());
    setSudoPolicy("disabled");
    setStopConditionsText("");
    setSessionTimeoutSeconds(600);
    setMaxConnections(5);
    setSelectedServers([]);
    setSchedule(0);
    setScheduleConfig(defaultScheduleConfig());
    setSelectedSkillSlugs([]);
    setInputArtifacts([]);
    setActiveArtifactIndex(null);
    setTelegramEnabled(false);
    setTelegramChatId("");
    setToolsExpanded(false);
    setSkillsExpanded(false);
  };

  useEffect(() => {
    if (!open) return;
    if (!initialAgent) {
      resetForm();
      return;
    }
    setStep("basics");
    setMode(initialAgent.mode);
    setSelectedType(initialAgent.agent_type || "custom");
    setName(initialAgent.name || "");
    setCommands((initialAgent.commands || []).join("\n"));
    setAiPrompt(initialAgent.ai_prompt || "");
    setGoal(initialAgent.goal || "");
    setSystemPrompt(initialAgent.system_prompt || "");
    setMaxIter(initialAgent.max_iterations || 20);
    setToolsConfig({ ...buildDefaultToolsConfig(), ...(initialAgent.tools_config || {}) });
    setSudoPolicy(sudoAgentOption(initialAgent.sudo_policy).value);
    setStopConditionsText((initialAgent.stop_conditions || []).join("\n"));
    setSessionTimeoutSeconds(initialAgent.session_timeout_seconds || 600);
    setMaxConnections(initialAgent.max_connections || 5);
    setSelectedServers(initialAgent.server_ids || []);
    setSchedule(initialAgent.schedule_minutes || 0);
    setScheduleConfig(initialAgent.schedule_config || scheduleConfigFromMinutes(initialAgent.schedule_minutes || 0));
    setSelectedSkillSlugs(initialAgent.skill_slugs || []);
    setInputArtifacts((initialAgent.input_artifacts || []).map(normalizeArtifactDraft));
    setActiveArtifactIndex(null);
    const telegram = initialAgent.report_delivery?.telegram;
    setTelegramEnabled(Boolean(telegram?.enabled));
    setTelegramChatId(telegram?.chat_id || "");
    setToolsExpanded(false);
    setSkillsExpanded(false);
  }, [open, initialAgent]);

  const onSelectTemplate = (tpl: AgentTemplate) => {
    setSelectedType(tpl.type);
    setName(tpl.name);
    setCommands(tpl.commands.join("\n"));
    setAiPrompt(tpl.ai_prompt);
    setGoal(tpl.goal || "");
    setSystemPrompt(tpl.system_prompt || "");
    setStopConditionsText((tpl.stop_conditions || []).join("\n"));
    setStep("basics");
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const normalizedSchedule = finalizeScheduleConfig(scheduleConfig, schedule);
      const payload = {
        name: name || localize(lang, "Новый агент", "Custom Agent"),
        mode,
        agent_type: selectedType || "custom",
        server_ids: selectedServers,
        commands: commands.split("\n").map((command) => command.trim()).filter(Boolean),
        ai_prompt: aiPrompt,
        schedule_minutes: deriveScheduleMinutes(normalizedSchedule),
        schedule_config: normalizedSchedule,
        goal,
        system_prompt: systemPrompt,
        max_iterations: maxIter,
        allow_multi_server: selectedServers.length > 1,
        tools_config: mode === "mini" ? {} : toolsConfig,
        sudo_policy: sudoPolicy,
        stop_conditions: stopConditionsText.split("\n").map((item) => item.trim()).filter(Boolean),
        skill_slugs: selectedSkillSlugs,
        input_artifacts: inputArtifacts.map(prepareArtifactForSave).filter((item) => item.name && (item.content || item.tasks?.length)),
        report_delivery: { telegram: { enabled: telegramEnabled, chat_id: telegramChatId.trim(), format: "brief", include_link: true } },
        session_timeout_seconds: sessionTimeoutSeconds,
        max_connections: maxConnections,
      };
      if (initialAgent) {
        await updateAgent(initialAgent.id, payload);
        await onSaved({ id: initialAgent.id, mode, action: "update" });
      } else {
        const created = await createAgent(payload);
        await onSaved({ id: created.id, mode, action: "create" });
        resetForm();
      }
    } finally {
      setSaving(false);
    }
  };

  const goNext = () => setStep(AGENT_WIZARD_STEPS[Math.min(currentStepIndex + 1, AGENT_WIZARD_STEPS.length - 1)].key);
  const goBack = () => setStep(AGENT_WIZARD_STEPS[Math.max(currentStepIndex - 1, 0)].key);
  const toggleServer = (id: number) => setSelectedServers((prev) => prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]);
  const hasAllServersSelected = allServerIds.length > 0 && allServerIds.every((id) => selectedServers.includes(id));
  const selectAll = () => setSelectedServers(hasAllServersSelected ? [] : allServerIds);
  const setScheduleMode = (modeValue: AgentScheduleMode) => {
    const nextInterval = modeValue === "interval" ? (schedule || scheduleConfig.interval_minutes || 60) : 0;
    setSchedule(nextInterval);
    setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: modeValue, interval_minutes: nextInterval }, nextInterval));
  };
  const updateSchedule = (patch: Partial<AgentScheduleConfig>) => setScheduleConfig((current) => finalizeScheduleConfig({ ...current, ...patch }, schedule));
  const toggleWeekday = (day: number) => {
    setScheduleConfig((current) => {
      const currentDays = current.weekdays || [];
      const weekdays = currentDays.includes(day) ? currentDays.filter((item) => item !== day) : [...currentDays, day].sort();
      return finalizeScheduleConfig({ ...current, weekdays: weekdays.length ? weekdays : [day] }, schedule);
    });
  };
  const toggleSkill = (slug: string) => setSelectedSkillSlugs((current) => current.includes(slug) ? current.filter((item) => item !== slug) : [...current, slug]);
  const updateArtifact = (index: number, patch: Partial<AgentInputArtifact>) => setInputArtifacts((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  const addArtifact = (kind: AgentInputArtifact["kind"]) => {
    const labels = { document: localize(lang, "Документ", "Document"), task_list: localize(lang, "Список задач", "Task list"), script: localize(lang, "Скрипт", "Script") };
    const artifact: AgentInputArtifact = kind === "task_list"
      ? { kind, name: labels[kind], content: "", run_hint: "", tasks: [{ title: "", details: "", done: false }] }
      : { kind, name: labels[kind], content: "", run_hint: "" };
    const next = [...inputArtifacts, artifact].slice(0, 10);
    setInputArtifacts(next);
    setActiveArtifactIndex(next.length - 1);
  };
  const removeArtifact = (index: number) => {
    setInputArtifacts((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setActiveArtifactIndex((current) => current === index ? null : current !== null && current > index ? current - 1 : current);
  };
  const updateArtifactTask = (artifactIndex: number, taskIndex: number, patch: Partial<AgentTaskDraft>) => {
    setInputArtifacts((current) => current.map((artifact, index) => {
      if (index !== artifactIndex) return artifact;
      const tasks = artifact.tasks?.length ? artifact.tasks : [{ title: "", details: "", done: false }];
      return { ...artifact, tasks: tasks.map((task, itemIndex) => itemIndex === taskIndex ? { ...task, ...patch } : task) };
    }));
  };
  const addArtifactTask = (artifactIndex: number) => setInputArtifacts((current) => current.map((artifact, index) => index === artifactIndex ? { ...artifact, tasks: [...(artifact.tasks || []), { title: "", details: "", done: false }] } : artifact));
  const removeArtifactTask = (artifactIndex: number, taskIndex: number) => {
    setInputArtifacts((current) => current.map((artifact, index) => {
      if (index !== artifactIndex) return artifact;
      const tasks = (artifact.tasks || []).filter((_, itemIndex) => itemIndex !== taskIndex);
      return { ...artifact, tasks: tasks.length ? tasks : [{ title: "", details: "", done: false }] };
    }));
  };
  const onMaterialFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const added: AgentInputArtifact[] = [];
    for (const file of Array.from(files).slice(0, Math.max(0, 10 - inputArtifacts.length))) {
      const content = await file.text();
      const kind: AgentInputArtifact["kind"] = file.name.toLowerCase().match(/\.(sh|py|js|ts|sql|ps1)$/) ? "script" : "document";
      added.push({ kind, name: file.name, source_name: file.name, size_bytes: file.size, content: content.slice(0, 12_000), run_hint: "" });
    }
    const next = [...inputArtifacts, ...added].slice(0, 10);
    setInputArtifacts(next);
    if (added.length) setActiveArtifactIndex(Math.min(inputArtifacts.length, next.length - 1));
  };

  const summaryRows = [
    { icon: Tag, label: localize(lang, "Название", "Name"), value: name || localize(lang, "Новый агент", "New agent") },
    { icon: Layers, label: localize(lang, "Тип", "Type"), value: agentModeLabel(mode, lang) },
    { icon: Server, label: localize(lang, "Серверы", "Servers"), value: selectedServers.length ? localize(lang, `${selectedServers.length} выбрано`, `${selectedServers.length} selected`) : localize(lang, "Не выбраны", "Not selected") },
    { icon: Shield, label: localize(lang, "Права запуска", "Run access"), value: localize(lang, sudoAgentOption(sudoPolicy).labelRu, sudoAgentOption(sudoPolicy).labelEn) },
  ];
  const enabledToolCount = Object.values(toolsConfig).filter(Boolean).length;
  const visibleSkills = skillsExpanded ? availableSkills : availableSkills.slice(0, 4);

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="max-h-[calc(100vh-32px)] max-w-[min(1420px,calc(100vw-32px))] rounded-lg border-primary/10 bg-card/95 p-0 shadow-[0_24px_90px_hsl(var(--background)_/_0.72)]">
        <DialogHeader className="px-6 py-5">
          <div className="flex items-start gap-4 pr-12">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/15 text-primary shadow-[0_0_28px_hsl(var(--primary)_/_0.16)]">
              <Bot className="h-6 w-6" />
            </span>
            <div className="min-w-0">
              <DialogTitle className="text-xl">{isEditing ? localize(lang, "Редактирование агента", "Edit agent") : localize(lang, "Создание агента", "Create agent")}</DialogTitle>
              <DialogDescription>{localize(lang, "Настройте поведение, окружения, возможности и запуск.", "Configure behavior, targets, capabilities, and launch.")}</DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <AgentWizardProgress
          step={step}
          currentStepIndex={currentStepIndex}
          lang={lang}
          onStepChange={setStep}
        />

        <DialogBody className="max-h-[calc(100vh-250px)] overflow-y-auto px-6 py-4">
          <AgentWizardStepContent
            step={step}
            lang={lang}
            t={t}
            mode={mode}
            setMode={setMode}
            templates={templates}
            onSelectTemplate={onSelectTemplate}
            setSelectedType={setSelectedType}
            setStep={setStep}
            name={name}
            setName={setName}
            commands={commands}
            setCommands={setCommands}
            aiPrompt={aiPrompt}
            setAiPrompt={setAiPrompt}
            goal={goal}
            setGoal={setGoal}
            systemPrompt={systemPrompt}
            setSystemPrompt={setSystemPrompt}
            maxIter={maxIter}
            setMaxIter={setMaxIter}
            sessionTimeoutSeconds={sessionTimeoutSeconds}
            setSessionTimeoutSeconds={setSessionTimeoutSeconds}
            maxConnections={maxConnections}
            setMaxConnections={setMaxConnections}
            sudoPolicy={sudoPolicy}
            setSudoPolicy={setSudoPolicy}
            servers={servers}
            selectedServers={selectedServers}
            toggleServer={toggleServer}
            selectAll={selectAll}
            hasAllServersSelected={hasAllServersSelected}
            schedule={schedule}
            setSchedule={setSchedule}
            scheduleConfig={scheduleConfig}
            setScheduleConfig={setScheduleConfig}
            setScheduleMode={setScheduleMode}
            updateSchedule={updateSchedule}
            toggleWeekday={toggleWeekday}
            enabledToolCount={enabledToolCount}
            toolsConfig={toolsConfig}
            setToolsConfig={setToolsConfig}
            toolsExpanded={toolsExpanded}
            setToolsExpanded={setToolsExpanded}
            stopConditionsText={stopConditionsText}
            setStopConditionsText={setStopConditionsText}
            selectedSkillSlugs={selectedSkillSlugs}
            availableSkills={availableSkills}
            visibleSkills={visibleSkills}
            toggleSkill={toggleSkill}
            skillsExpanded={skillsExpanded}
            setSkillsExpanded={setSkillsExpanded}
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
            summaryRows={summaryRows}
            commandCount={commandCount}
          />
        </DialogBody>

        <DialogFooter className="items-center justify-between gap-3 px-6 py-4 sm:flex-row">
          <Button size="sm" variant="outline" className="min-w-28 gap-2" onClick={currentStepIndex === 0 ? onClose : goBack}>
            <ArrowLeft className="h-4 w-4" /> {currentStepIndex === 0 ? localize(lang, "Отмена", "Cancel") : t("agent.back")}
          </Button>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="min-w-44 gap-2" onClick={onSave} disabled={saving || !canSave}>
              <Save className="h-4 w-4" /> {saving ? localize(lang, "Сохраняем...", "Saving...") : localize(lang, "Сохранить", "Save")}
            </Button>
            {step === "review" ? (
              <Button size="sm" className="min-w-36 gap-2" onClick={onSave} disabled={saving || !canSave}>
                {saving ? localize(lang, "Сохраняем...", "Saving...") : isEditing ? localize(lang, "Сохранить", "Save") : t("agent.create")}
              </Button>
            ) : (
              <Button size="sm" className="min-w-32 gap-2" onClick={goNext}>
                {localize(lang, "Далее", "Next")} <ArrowRight className="h-4 w-4" />
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
