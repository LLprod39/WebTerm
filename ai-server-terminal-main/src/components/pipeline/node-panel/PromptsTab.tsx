import type { AgentConfig } from "@/lib/api";

import { t, type NodePanelLang } from "./shared";
import { VariableHighlighter } from "./VariableHighlighter";

type PromptsTabProps = {
  lang: NodePanelLang;
  goal: string;
  systemPrompt: string;
  selectedAgent: AgentConfig | null;
  onGoalChange: (value: string) => void;
  onSystemPromptChange: (value: string) => void;
};

export function PromptsTab({
  lang,
  goal,
  systemPrompt,
  selectedAgent,
  onGoalChange,
  onSystemPromptChange,
}: PromptsTabProps) {
  const systemPromptValue = selectedAgent?.system_prompt || systemPrompt;

  return (
    <div className="space-y-6">
      <VariableHighlighter
        id="node-goal"
        lang={lang}
        label={t(lang, "Goal", "Goal")}
        description={t(
          lang,
          "Опишите, чего агент должен добиться. Runtime подставляет значения контекста через {variable}.",
          "Describe what the agent must accomplish. Runtime substitutes context values with {variable}.",
        )}
        value={goal}
        placeholder={t(
          lang,
          "Например: Проверь staging, собери риски и дай короткий технический вывод.",
          "Example: Inspect staging, collect risks, and produce a concise technical conclusion.",
        )}
        minRows={5}
        onChange={onGoalChange}
      />

      <div className="rounded-2xl border border-border/60 bg-muted/20 px-4 py-3">
        <VariableHighlighter
          id="node-system-prompt"
          lang={lang}
          label={t(lang, "System Prompt", "System Prompt")}
          description={
            selectedAgent
              ? t(
                  lang,
                  "Для этой ноды выбран сохранённый Agent Config, поэтому system prompt берётся из него и доступен здесь только для просмотра.",
                  "This node uses a saved Agent Config, so the system prompt is inherited from it and is shown here as read-only.",
                )
              : t(
                  lang,
                  "Задайте постоянные правила поведения агента, ограничения и формат ответа.",
                  "Define the agent's standing behavior, guardrails, and response format.",
                )
          }
          value={systemPromptValue}
          placeholder={t(
            lang,
            "Например: Ты senior SRE. Действуй осторожно, верифицируй вывод и не скрывай неопределённость.",
            "Example: You are a senior SRE. Act cautiously, verify outputs, and do not hide uncertainty.",
          )}
          minRows={6}
          readOnly={Boolean(selectedAgent)}
          onChange={onSystemPromptChange}
        />
      </div>
    </div>
  );
}
