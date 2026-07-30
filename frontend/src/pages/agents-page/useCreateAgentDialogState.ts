import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layers, Server, Shield, Tag } from "lucide-react";
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
  type AgentTemplate,
  type StudioSkill,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import {
  AGENT_WIZARD_STEPS,
  type AgentSudoPolicy,
  type AgentTaskDraft,
  type AgentWizardStep,
  buildAgentWizardReadiness,
  buildDefaultToolsConfig,
  defaultScheduleConfig,
  deriveScheduleMinutes,
  finalizeScheduleConfig,
  firstFailedCheckForStep,
  HIDDEN_AGENT_TEMPLATE_TYPES,
  agentModeLabel,
  normalizeArtifactDraft,
  prepareArtifactForSave,
  readinessPercent,
  scheduleConfigFromMinutes,
  stepHasBlockingFailure,
  sudoAgentOption,
  validateAgentWizardSchema,
} from "./agentPageUtils";
import type { CreateAgentSavedPayload } from "./createAgentDialogTypes";

type UseCreateAgentDialogStateArgs = {
  open: boolean;
  initialAgent?: AgentItem | null;
  onSaved: (saved: CreateAgentSavedPayload) => Promise<void> | void;
};

export function useCreateAgentDialogState({
  open,
  initialAgent = null,
  onSaved,
}: UseCreateAgentDialogStateArgs) {
  const { t, lang } = useI18n();
  const isEditing = Boolean(initialAgent);
  const [step, setStep] = useState<AgentWizardStep>("template");
  // Pilot default: full agent (autonomous goal + tools). Mini stays one click away.
  // Custom ("manual") scenario is pre-selected so Next works immediately.
  const [mode, setMode] = useState<"mini" | "full" | "multi">("full");
  const [selectedType, setSelectedType] = useState("custom");
  const [name, setName] = useState("");
  const [commands, setCommands] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [goal, setGoal] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  // Keep in sync with servers.agents.agent_budgets FULL_DEFAULT_* (complex-task defaults).
  const [maxIter, setMaxIter] = useState(40);
  const [toolsConfig, setToolsConfig] = useState<Record<string, boolean>>(() => buildDefaultToolsConfig());
  const [sudoPolicy, setSudoPolicy] = useState<AgentSudoPolicy>("disabled");
  const [stopConditionsText, setStopConditionsText] = useState("");
  const [sessionTimeoutSeconds, setSessionTimeoutSeconds] = useState(1200);
  const [maxConnections, setMaxConnections] = useState(5);
  const [selectedServers, setSelectedServers] = useState<number[]>([]);
  const [schedule, setSchedule] = useState(0);
  const [scheduleConfig, setScheduleConfig] = useState<AgentScheduleConfig>(() => defaultScheduleConfig());
  const [selectedSkillSlugs, setSelectedSkillSlugs] = useState<string[]>([]);
  const [inputArtifacts, setInputArtifacts] = useState<AgentInputArtifact[]>([]);
  const [activeArtifactIndex, setActiveArtifactIndex] = useState<number | null>(null);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramChatId, setTelegramChatId] = useState("");
  const [sudoRiskAcknowledged, setSudoRiskAcknowledged] = useState(false);
  const [serverSearch, setServerSearch] = useState("");
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const [skillsExpanded, setSkillsExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runAfterSave, setRunAfterSave] = useState(true);
  const { data: tplData } = useQuery({ queryKey: ["agents", "templates"], queryFn: fetchAgentTemplates, enabled: open });
  const { data: bootstrapData } = useQuery({ queryKey: ["frontend", "bootstrap"], queryFn: fetchFrontendBootstrap, staleTime: 30_000 });
  const { data: availableSkillsData } = useQuery<unknown>({ queryKey: ["studio", "skills", "agent-picker"], queryFn: studioSkills.list, enabled: open });
  const templates = (tplData?.templates || [])
    .filter((template) => !HIDDEN_AGENT_TEMPLATE_TYPES.has(template.type))
    .filter((template) => template.mode === mode || (mode === "multi" && template.mode === "full"));
  const servers = useMemo(() => bootstrapData?.servers ?? [], [bootstrapData?.servers]);
  const availableSkills = Array.isArray(availableSkillsData) ? (availableSkillsData as StudioSkill[]) : [];
  const visibleServers = useMemo(() => {
    const query = serverSearch.trim().toLowerCase();
    if (!query) return servers;
    return servers.filter((server) =>
      server.name.toLowerCase().includes(query) ||
      server.host.toLowerCase().includes(query) ||
      server.group_name.toLowerCase().includes(query),
    );
  }, [serverSearch, servers]);
  const allServerIds = servers.map((server) => server.id);
  const activeArtifact = activeArtifactIndex !== null ? inputArtifacts[activeArtifactIndex] : null;
  const currentStepIndex = Math.max(0, AGENT_WIZARD_STEPS.findIndex((item) => item.key === step));
  const commandCount = commands.split("\n").map((item) => item.trim()).filter(Boolean).length;
  const readinessChecks = useMemo(() => buildAgentWizardReadiness({
    selectedType,
    mode,
    name,
    commands,
    goal,
    selectedServers,
    sudoPolicy,
    sudoRiskAcknowledged,
    scheduleConfig,
    schedule,
    telegramEnabled,
    telegramChatId,
  }), [
    commands,
    goal,
    mode,
    name,
    schedule,
    scheduleConfig,
    selectedServers,
    selectedType,
    sudoPolicy,
    sudoRiskAcknowledged,
    telegramChatId,
    telegramEnabled,
  ]);
  const readiness = readinessPercent(readinessChecks);
  const currentStepBlockingCheck = firstFailedCheckForStep(readinessChecks, step);
  const schemaValidation = useMemo(() => validateAgentWizardSchema({
    selectedType,
    mode,
    name,
    commands,
    goal,
    selectedServers,
    sudoPolicy,
    sudoRiskAcknowledged,
    scheduleConfig,
    schedule,
    telegramEnabled,
    telegramChatId,
  }), [
    commands,
    goal,
    mode,
    name,
    schedule,
    scheduleConfig,
    selectedServers,
    selectedType,
    sudoPolicy,
    sudoRiskAcknowledged,
    telegramChatId,
    telegramEnabled,
  ]);
  const canSave = readiness === 100 && schemaValidation.isValid;
  const resetForm = () => {
    setSchedule(0);
    setScheduleConfig(defaultScheduleConfig());
    setSelectedSkillSlugs([]);
    setInputArtifacts([]);
    setActiveArtifactIndex(null);
    setTelegramEnabled(false);
    setTelegramChatId("");
    setSudoRiskAcknowledged(false);
    setServerSearch("");
    setToolsExpanded(false);
    setSkillsExpanded(false);
    setMaxIter(40);
    setToolsConfig(buildDefaultToolsConfig());
    setSudoPolicy("disabled");
    setStopConditionsText("");
    setSessionTimeoutSeconds(1200);
    setMaxConnections(5);
    setSelectedServers([]);
    setAiPrompt("");
    setCommands("");
    setRunAfterSave(true);
    setMode("full");
    setSelectedType("custom");
    setName("");
    setGoal("");
    setSystemPrompt("");
    setStep("template");
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
    setMaxIter(initialAgent.max_iterations || 40);
    setToolsConfig({ ...buildDefaultToolsConfig(), ...(initialAgent.tools_config || {}) });
    setSudoPolicy(sudoAgentOption(initialAgent.sudo_policy).value);
    setStopConditionsText((initialAgent.stop_conditions || []).join("\n"));
    setSessionTimeoutSeconds(initialAgent.session_timeout_seconds || 1200);
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
    setSudoRiskAcknowledged(sudoAgentOption(initialAgent.sudo_policy).value !== "approved");
    setServerSearch("");
    setToolsExpanded(false);
    setSkillsExpanded(false);
    setRunAfterSave(false);
  }, [open, initialAgent]);
  const onSelectTemplate = (tpl: AgentTemplate) => {
    setSelectedType(tpl.type);
    setName(tpl.name);
    setCommands(tpl.commands.join("\n"));
    setAiPrompt(tpl.ai_prompt);
    setGoal(tpl.goal || "");
    setSystemPrompt(tpl.system_prompt || "");
    setStopConditionsText((tpl.stop_conditions || []).join("\n"));
    if (tpl.mode === "mini" || tpl.mode === "full" || tpl.mode === "multi") {
      setMode(tpl.mode === "full" && mode === "multi" ? "multi" : tpl.mode);
    }
    setStep("basics");
  };
  const onSave = async () => {
    if (!schemaValidation.isValid) {
      setStep(schemaValidation.issues[0]?.step || "basics");
      return;
    }
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
        await onSaved({ id: initialAgent.id, mode, action: "update", runAfterSave });
      } else {
        const created = await createAgent(payload);
        await onSaved({ id: created.id, mode, action: "create", runAfterSave });
        resetForm();
      }
    } finally {
      setSaving(false);
    }
  };
  const canVisitStep = (targetStep: AgentWizardStep) => {
    const targetIndex = AGENT_WIZARD_STEPS.findIndex((item) => item.key === targetStep);
    if (targetIndex <= currentStepIndex) return true;
    return AGENT_WIZARD_STEPS.slice(0, targetIndex).every((item) => !stepHasBlockingFailure(readinessChecks, item.key));
  };
  const goNext = () => {
    if (currentStepBlockingCheck) return;
    setStep(AGENT_WIZARD_STEPS[Math.min(currentStepIndex + 1, AGENT_WIZARD_STEPS.length - 1)].key);
  };
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

  return {
    t,
    lang,
    isEditing,
    step,
    setStep,
    mode,
    setMode,
    selectedType,
    setSelectedType,
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
    toolsConfig,
    setToolsConfig,
    sudoPolicy,
    setSudoPolicy,
    stopConditionsText,
    setStopConditionsText,
    sessionTimeoutSeconds,
    setSessionTimeoutSeconds,
    maxConnections,
    setMaxConnections,
    selectedServers,
    schedule,
    setSchedule,
    scheduleConfig,
    setScheduleConfig,
    selectedSkillSlugs,
    inputArtifacts,
    activeArtifactIndex,
    setActiveArtifactIndex,
    telegramEnabled,
    setTelegramEnabled,
    telegramChatId,
    setTelegramChatId,
    sudoRiskAcknowledged,
    setSudoRiskAcknowledged,
    serverSearch,
    setServerSearch,
    toolsExpanded,
    setToolsExpanded,
    skillsExpanded,
    setSkillsExpanded,
    saving,
    runAfterSave,
    setRunAfterSave,
    templates,
    visibleServers,
    serversCount: servers.length,
    availableSkills,
    activeArtifact,
    currentStepIndex,
    commandCount,
    readinessChecks,
    readiness,
    currentStepBlockingCheck,
    canSave,
    onSelectTemplate,
    onSave,
    canVisitStep,
    goNext,
    goBack,
    toggleServer,
    hasAllServersSelected,
    selectAll,
    setScheduleMode,
    updateSchedule,
    toggleWeekday,
    toggleSkill,
    updateArtifact,
    addArtifact,
    removeArtifact,
    updateArtifactTask,
    addArtifactTask,
    removeArtifactTask,
    onMaterialFiles,
    summaryRows,
    enabledToolCount,
    visibleSkills,
  };
}
