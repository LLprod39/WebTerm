import { Shield } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { localize } from "@/lib/i18n";
import { type AgentSudoPolicy, SUDO_AGENT_OPTIONS } from "./agentPageUtils";
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
  sudoPolicy: AgentSudoPolicy;
  setSudoPolicy: StateSetter<AgentSudoPolicy>;
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
  sudoPolicy,
  setSudoPolicy,
  sudoRiskAcknowledged,
  setSudoRiskAcknowledged,
}: AgentWizardBasicsStepProps) {
  return (
    <section className="space-y-4">
      <div>
        <p className="type-label text-primary">{localize(lang, "Задача и правила", "Task and rules")}</p>
        <h3 className="mt-1 font-display text-lg font-bold tracking-tight text-foreground">
          {localize(lang, "Объясните работу как новому сотруднику", "Brief the agent like a new employee")}
        </h3>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {localize(lang, "Назовите профиль, опишите ожидаемый результат и правила, которые нельзя нарушать.", "Name the profile, describe the expected outcome, and state the rules it must not break.")}
        </p>
      </div>
      <div className="space-y-2">
        <label htmlFor="agent-name" className="text-sm font-medium text-foreground">
          {localize(lang, "Имя цифрового сотрудника", "Digital employee name")} <span className="text-primary">*</span>
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
                {localize(lang, "Что нужно сделать", "What should be done")}
              </label>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {localize(lang, "Сформулируйте задачу и критерий готового результата простыми словами.", "Describe the task and what a finished result looks like in plain language.")}
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
              <label htmlFor="agent-system-prompt" className="text-sm font-medium text-foreground">{localize(lang, "Рабочие инструкции и ограничения", "Working instructions and boundaries")}</label>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Укажите порядок работы, источники истины, запреты и когда нужно остановиться и спросить.", "State the process, sources of truth, prohibitions, and when the agent must stop and ask.")}</p>
            </div>
            <Textarea id="agent-system-prompt" value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={3} className="bg-background/60 text-sm" placeholder={localize(lang, "Например: действуй осторожно, ничего не меняй без подтверждения", "e.g. act carefully, do not change anything without confirmation")} />
          </div>
        </>
      )}
      <div className="space-y-2">
        <div className="pt-2">
          <label htmlFor="agent-analysis-prompt" className="text-sm font-medium text-foreground">{localize(lang, "Что должно быть в результате", "What the result should contain")}</label>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Например: краткий вывод, найденная причина, выполненные действия, доказательства и следующий шаг.", "For example: a short conclusion, root cause, actions taken, evidence, and the next step.")}</p>
        </div>
        <Textarea id="agent-analysis-prompt" value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} rows={4} className="bg-background/60 text-sm" />
      </div>
      <div className="space-y-2">
        <div className="pt-2">
          <p className="text-sm font-semibold text-foreground">{localize(lang, "Границы автономности и подтверждения", "Autonomy boundaries and approvals")}</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Безопасный профиль работает без sudo. При необходимости агент может остановиться и запросить разрешение.", "The safe profile works without sudo. When needed, the agent can stop and request permission.")}</p>
        </div>
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
