import { BookOpen, ChevronDown, PlugZap, Settings2 } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import type { AgentInputArtifact, StudioSkill } from "@/lib/api";
import { localize } from "@/lib/i18n";
import {
  FULL_AGENT_TOOL_OPTIONS,
  READ_ONLY_AGENT_TOOL_KEYS,
  type AgentTaskDraft,
  buildDefaultToolsConfig,
} from "./agentPageUtils";
import { AgentMaterialsSection } from "./AgentMaterialsSection";
import type { AgentMode, StateSetter } from "./agentWizardStepTypes";

type AgentWizardCapabilitiesStepProps = {
  lang: string;
  mode: AgentMode;
  enabledToolCount: number;
  toolsConfig: Record<string, boolean>;
  setToolsConfig: StateSetter<Record<string, boolean>>;
  canConfigureMutatingTools: boolean;
  mutatingToolsAcknowledged: boolean;
  setMutatingToolsAcknowledged: StateSetter<boolean>;
  mutatingToolsEnabled: boolean;
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
};

export function AgentWizardCapabilitiesStep({
  lang,
  mode,
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
}: AgentWizardCapabilitiesStepProps) {
  return (
    <section className="space-y-4">
      <div>
        <p className="type-label text-primary">{localize(lang, "Контекст и возможности", "Context and capabilities")}</p>
        <h3 className="mt-1 font-display text-lg font-bold tracking-tight text-foreground">{localize(lang, "Что агент знает и чем может пользоваться", "What the agent knows and can use")}</h3>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {localize(lang, "Добавьте навыки, материалы и способ получить результат. Агент сохранит выбранные ограничения доступа.", "Add skills, materials, and result delivery. The agent will keep the selected access limits.")}
        </p>
      </div>
      <div className="flex items-start gap-3 rounded-sm border border-info/25 bg-info/5 px-3 py-3">
        <PlugZap className="mt-0.5 h-4 w-4 shrink-0 text-info" />
        <p className="text-xs leading-5 text-muted-foreground">
          {localize(
            lang,
            "Навыки добавляют инструкции и подключённые инструменты, включая MCP. Здесь можно выбрать только уже доступные навыки.",
            "Skills add instructions and connected tools, including MCP. Only skills already available to you can be selected here.",
          )}
        </p>
      </div>
      {(mode === "full" || mode === "multi") && (
        <details className="group rounded-sm border border-border bg-surface-0/35">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-foreground">
            <span className="flex items-center gap-2"><Settings2 className="h-4 w-4 text-primary" /> {localize(lang, "Дополнительные настройки", "Additional settings")}</span>
            <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
        <div className="space-y-3 border-t border-border px-4 py-4">
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
                    <input
                      type="checkbox"
                      checked={Boolean(toolsConfig[tool.key])}
                      disabled={!READ_ONLY_AGENT_TOOL_KEYS.has(tool.key) && !canConfigureMutatingTools}
                      onChange={(event) => {
                        if (!READ_ONLY_AGENT_TOOL_KEYS.has(tool.key)) setMutatingToolsAcknowledged(false);
                        setToolsConfig((current) => ({ ...current, [tool.key]: event.target.checked }));
                      }}
                    />
                    <span>
                      {tool.label}
                      {!READ_ONLY_AGENT_TOOL_KEYS.has(tool.key) ? (
                        <span className="ml-2 text-warning">
                          {localize(lang, "может изменять", "can modify")}
                        </span>
                      ) : null}
                    </span>
                  </label>
                ))}
              </div>
              {!canConfigureMutatingTools ? (
                <p role="note" className="rounded-md border border-primary/25 bg-primary/5 px-3 py-2 text-xs leading-5 text-muted-foreground">
                  {localize(
                    lang,
                    "Инструменты, которые могут вносить изменения, недоступны для вашей роли.",
                    "Tools that can make changes are unavailable for your role.",
                  )}
                </p>
              ) : mutatingToolsEnabled ? (
                <label className="flex items-start gap-3 rounded-md border border-warning/35 bg-warning/10 px-3 py-3 text-xs leading-5 text-foreground">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={mutatingToolsAcknowledged}
                    onChange={(event) => setMutatingToolsAcknowledged(event.target.checked)}
                  />
                  <span>
                    {localize(
                      lang,
                      "Я понимаю, что выбранные инструменты могут изменить тестовый сервер, и подтверждаю изолированную среду.",
                      "I understand the selected tools may change a test server and confirm this is an isolated environment.",
                    )}
                  </span>
                </label>
              ) : null}
              <Textarea value={stopConditionsText} onChange={(e) => setStopConditionsText(e.target.value)} rows={3} className="bg-background/60 text-xs" placeholder={localize(lang, "Условия остановки", "Stop conditions")} />
            </>
          )}
        </div>
        </details>
      )}
      <div className="space-y-3 border-t border-border/50 pt-4">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground"><BookOpen className="h-4 w-4 text-primary" /> {localize(lang, "Навыки и подключённые инструменты", "Skills and connected tools")}</h4>
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
        ) : <div className="rounded-lg border border-dashed border-border/70 px-3 py-3 text-xs leading-5 text-muted-foreground">{localize(lang, "Доступных skills пока нет. Подключите нужную интеграцию или skill, затем вернитесь в мастер.", "No skills are available yet. Connect the required integration or skill, then return to the wizard.")}</div>}
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
  );
}
