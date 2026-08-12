import { ArrowLeft, ArrowRight, Play } from "lucide-react";
import type { AgentItem } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { AsyncButton } from "@/components/system/AsyncButton";
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
import type { CreateAgentSavedPayload } from "./createAgentDialogTypes";
import { useCreateAgentDialogState } from "./useCreateAgentDialogState";

export type { CreateAgentSavedPayload } from "./createAgentDialogTypes";

type CreateAgentDialogProps = {
  open: boolean;
  onClose: () => void;
  initialAgent?: AgentItem | null;
  onSaved: (saved: CreateAgentSavedPayload) => Promise<void> | void;
};

export function CreateAgentDialog({
  open,
  onClose,
  onSaved,
  initialAgent = null,
}: CreateAgentDialogProps) {
  const state = useCreateAgentDialogState({ open, initialAgent, onSaved });
  const {
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
    canConfigureMutatingTools,
    mutatingToolsAcknowledged,
    setMutatingToolsAcknowledged,
    mutatingToolsEnabled,
    sudoPolicy,
    setSudoPolicy,
    stopConditionsText,
    setStopConditionsText,
    sessionTimeoutSeconds,
    setSessionTimeoutSeconds,
    maxConnections,
    setMaxConnections,
    providerBinding,
    setProviderBinding,
    providerMode,
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
    serversCount,
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
  } = state;

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="flex max-h-[calc(100dvh-20px)] max-w-[min(840px,calc(100vw-16px))] flex-col gap-0 overflow-hidden rounded-sm border-border p-0 shadow-elev-3 sm:max-w-[min(840px,calc(100vw-24px))]">
        <DialogHeader className="relative space-y-0 border-b border-border px-5 py-4 sm:px-6">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "linear-gradient(120deg, hsl(var(--ai) / 0.08), transparent 42%), linear-gradient(to bottom, hsl(var(--primary) / 0.05), transparent 60%)",
            }}
          />
          <div aria-hidden className="absolute inset-x-0 top-0 h-0.5 bg-primary" />
          <div className="relative min-w-0 pr-10">
            <DialogTitle className="font-display text-xl font-bold tracking-tight sm:text-2xl">
              {isEditing
                ? localize(lang, "Редактирование агента", "Edit agent")
                : localize(lang, "Создание агента", "Create agent")}
            </DialogTitle>
            <DialogDescription className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">
              {isEditing
                ? localize(lang, "Обновите цель, серверы или права — и сохраните.", "Update goal, servers, or access — then save.")
                : localize(
                  lang,
                  "По умолчанию: диагностика read-only, один сервер и сохранение без запуска.",
                  "Default: read-only diagnostics, one server, and save without running.",
                )}
            </DialogDescription>
          </div>
        </DialogHeader>
        <AgentWizardProgress
          step={step}
          currentStepIndex={currentStepIndex}
          lang={lang}
          onStepChange={setStep}
          canVisitStep={canVisitStep}
        />
        <DialogBody className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          <AgentWizardStepContent
            step={step}
            lang={lang}
            t={t}
            mode={mode}
            setMode={setMode}
            templates={templates}
            onSelectTemplate={onSelectTemplate}
            selectedType={selectedType}
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
            providerBinding={providerBinding}
            setProviderBinding={setProviderBinding}
            providerMode={providerMode}
            sudoPolicy={sudoPolicy}
            setSudoPolicy={setSudoPolicy}
            servers={visibleServers}
            totalServerCount={serversCount}
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
            sudoRiskAcknowledged={sudoRiskAcknowledged}
            setSudoRiskAcknowledged={setSudoRiskAcknowledged}
            summaryRows={summaryRows}
            commandCount={commandCount}
            readiness={readiness}
            readinessChecks={readinessChecks}
            runAfterSave={runAfterSave}
            setRunAfterSave={setRunAfterSave}
            isEditing={isEditing}
          />
        </DialogBody>
        <DialogFooter className="shrink-0 items-stretch justify-between gap-3 border-t border-border bg-surface-0/50 px-4 py-3.5 sm:flex-row sm:items-center sm:px-6">
          <Button variant="ghost" className="gap-2" onClick={currentStepIndex === 0 ? onClose : goBack}>
            <ArrowLeft className="h-4 w-4" /> {currentStepIndex === 0 ? localize(lang, "Отмена", "Cancel") : t("agent.back")}
          </Button>
          {currentStepBlockingCheck ? (
            <p className="flex-1 self-center text-xs leading-5 text-warning sm:px-2">
              {localize(lang, currentStepBlockingCheck.detailRu, currentStepBlockingCheck.detailEn)}
            </p>
          ) : (
            <div className="hidden flex-1 sm:block" />
          )}
          {step === "review" ? (
            <AsyncButton
              className="min-w-44 gap-2 shadow-elev-1"
              onClick={onSave}
              loading={saving}
              loadingLabel={localize(lang, "Сохраняем…", "Saving…")}
              disabled={!canSave}
            >
              {runAfterSave && !isEditing ? (
                <>
                  <Play className="h-4 w-4" />
                  {localize(lang, "Создать и запустить", "Create & run")}
                </>
              ) : isEditing ? (
                localize(lang, "Сохранить", "Save")
              ) : (
                t("agent.create")
              )}
            </AsyncButton>
          ) : (
            <Button className="min-w-32 gap-2 shadow-elev-1" onClick={goNext} disabled={Boolean(currentStepBlockingCheck)}>
              {localize(lang, "Далее", "Next")} <ArrowRight className="h-4 w-4" />
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
