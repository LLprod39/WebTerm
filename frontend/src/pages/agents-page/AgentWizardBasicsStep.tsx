import { Shield } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ProviderBindingSelect } from "@/components/settings/ProviderBindingSelect";
import type { ProviderBinding } from "@/api/aiProviders";
import { localize } from "@/lib/i18n";
import {
  AGENT_BUDGET_PROFILES,
  type AgentBudgetProfileId,
  type AgentSudoPolicy,
  SUDO_AGENT_OPTIONS,
  resolveBudgetProfileId,
} from "./agentPageUtils";
import type { AgentMode, StateSetter } from "./agentWizardStepTypes";

type AgentWizardBasicsStepProps = {
  lang: string;
  t: (key: string) => string;
  mode: AgentMode;
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
  providerBinding: ProviderBinding | null;
  setProviderBinding: StateSetter<ProviderBinding | null>;
  providerMode: "interactive" | "unattended";
  sudoPolicy: AgentSudoPolicy;
  setSudoPolicy: StateSetter<AgentSudoPolicy>;
  setToolsConfig: StateSetter<Record<string, boolean>>;
  sudoRiskAcknowledged: boolean;
  setSudoRiskAcknowledged: StateSetter<boolean>;
};

export function AgentWizardBasicsStep({
  lang,
  t,
  mode,
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
  setToolsConfig,
  sudoRiskAcknowledged,
  setSudoRiskAcknowledged,
}: AgentWizardBasicsStepProps) {
  return (
    <section className="space-y-4">
      <h3 className="text-sm font-semibold text-foreground">
        {localize(lang, "Основные настройки", "Basics")}
      </h3>
      <div className="space-y-2">
        <label htmlFor="agent-name" className="text-sm font-medium text-foreground">
          {localize(lang, "Название агента", "Agent name")} <span className="text-primary">*</span>
        </label>
        <Input
          id="agent-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={localize(lang, "Анализ логов", "Log analysis")}
          className="h-10"
        />
      </div>
      {mode === "mini" ? (
        <div className="space-y-2">
          <div>
            <label htmlFor="agent-commands" className="text-sm font-medium text-foreground">{t("agent.commands_label")} <span className="text-primary">*</span></label>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Каждая команда — с новой строки. Агент выполнит их по порядку.", "One command per line. The agent runs them in order.")}</p>
          </div>
          <Textarea id="agent-commands" value={commands} onChange={(e) => setCommands(e.target.value)} rows={7} className="font-mono text-xs" placeholder={"hostname\nuptime\nfree -m"} />
        </div>
      ) : (
        <>
          <div className="space-y-2">
            <div>
              <label htmlFor="agent-goal" className="text-sm font-medium text-foreground">
                {localize(lang, "Цель", "Goal")}
              </label>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {localize(lang, "Что агент должен сделать — желаемый результат.", "What the agent should achieve — the desired outcome.")}
              </p>
            </div>
            <Textarea
              id="agent-goal"
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
              <label htmlFor="agent-system-prompt" className="text-sm font-medium text-foreground">{localize(lang, "Инструкции (поведение)", "Instructions (behaviour)")}</label>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Как агенту себя вести: роль, стиль, ограничения.", "How the agent should behave: role, style, constraints.")}</p>
            </div>
            <Textarea id="agent-system-prompt" value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={3} className="bg-background/60 text-sm" placeholder={localize(lang, "Например: действуй осторожно, ничего не меняй без подтверждения", "e.g. act carefully, do not change anything without confirmation")} />
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
          <label id="agent-provider-label" className="text-sm font-medium text-foreground">
            {localize(lang, "AI-провайдер задачи", "Task AI provider")}
          </label>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {localize(
              lang,
              providerMode === "unattended"
                ? "Для расписания показаны только подключения с правом фонового запуска. Привязка закрепляется за запуском."
                : "Можно закрепить Codex CLI или Grok CLI за агентом; без выбора действует настройка по умолчанию.",
              providerMode === "unattended"
                ? "Only connections allowed for background runs are shown. The binding is pinned to each run."
                : "Pin Codex CLI or Grok CLI to this agent, or use the configured task default.",
            )}
          </p>
        </div>
        <ProviderBindingSelect
          value={providerBinding}
          onChange={setProviderBinding}
          mode={providerMode}
          lang={lang === "ru" ? "ru" : "en"}
          ariaLabel={localize(lang, "AI-провайдер задачи", "Task AI provider")}
        />
      </div>
      <div className="space-y-2">
        <div className="pt-2">
          <label htmlFor="agent-analysis-prompt" className="text-sm font-medium text-foreground">{localize(lang, "Инструкции к анализу", "Analysis instructions")}</label>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Как разобрать и оформить результат выполнения.", "How to interpret and format the run's results.")}</p>
        </div>
        <Textarea id="agent-analysis-prompt" value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} rows={4} className="bg-background/60 text-sm" />
      </div>
      <div className="space-y-2">
        <p className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Права запуска", "Run access")}</p>
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
  );
}
