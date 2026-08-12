import { AgentWizardBasicsStep } from "./AgentWizardBasicsStep";
import { AgentWizardCapabilitiesStep } from "./AgentWizardCapabilitiesStep";
import { AgentWizardReviewStep } from "./AgentWizardReviewStep";
import { AgentWizardServersStep } from "./AgentWizardServersStep";
import { AgentWizardTemplateStep } from "./AgentWizardTemplateStep";
import type { AgentWizardStepContentProps } from "./agentWizardStepTypes";

export type { AgentWizardStepContentProps } from "./agentWizardStepTypes";

export function AgentWizardStepContent(props: AgentWizardStepContentProps) {
  const {
    step,
    lang,
    t,
    mode,
    setMode,
    templates,
    onSelectTemplate,
    selectedType,
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
    providerBinding,
    setProviderBinding,
    providerMode,
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
    canConfigureMutatingTools,
    mutatingToolsAcknowledged,
    setMutatingToolsAcknowledged,
    mutatingToolsEnabled,
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
    runAfterSave = false,
    setRunAfterSave,
    isEditing = false,
  } = props;

  return (
    <div className="space-y-6">
      <div className="space-y-6">
        {step === "template" && (
          <AgentWizardTemplateStep
            lang={lang}
            mode={mode}
            setMode={setMode}
            templates={templates}
            onSelectTemplate={onSelectTemplate}
            selectedType={selectedType}
            setSelectedType={setSelectedType}
            setStep={setStep}
          />
        )}
        {step === "basics" && (
          <AgentWizardBasicsStep
            lang={lang}
            t={t}
            mode={mode}
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
            providerBinding={providerBinding}
            setProviderBinding={setProviderBinding}
            providerMode={providerMode}
            sudoPolicy={sudoPolicy}
            setSudoPolicy={setSudoPolicy}
            setToolsConfig={setToolsConfig}
            sudoRiskAcknowledged={sudoRiskAcknowledged}
            setSudoRiskAcknowledged={setSudoRiskAcknowledged}
          />
        )}
        {step === "servers" && (
          <AgentWizardServersStep
            lang={lang}
            t={t}
            servers={servers}
            totalServerCount={totalServerCount}
            serverSearch={serverSearch}
            setServerSearch={setServerSearch}
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
          />
        )}
        {step === "capabilities" && (
          <AgentWizardCapabilitiesStep
            lang={lang}
            mode={mode}
            enabledToolCount={enabledToolCount}
            toolsConfig={toolsConfig}
            setToolsConfig={setToolsConfig}
            canConfigureMutatingTools={canConfigureMutatingTools}
            mutatingToolsAcknowledged={mutatingToolsAcknowledged}
            setMutatingToolsAcknowledged={setMutatingToolsAcknowledged}
            mutatingToolsEnabled={mutatingToolsEnabled}
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
          />
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
