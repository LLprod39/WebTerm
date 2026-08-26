import { Brain, ChevronDown, KeyRound, Layers, Settings2, Terminal, Workflow } from "lucide-react";
import type { AgentTemplate } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { AGENT_ICONS, type AgentWizardStep } from "./agentPageUtils";
import type { AgentMode, StateSetter } from "./agentWizardStepTypes";

type AgentWizardTemplateStepProps = {
  lang: string;
  mode: AgentMode;
  setMode: StateSetter<AgentMode>;
  templates: AgentTemplate[];
  onSelectTemplate: (template: AgentTemplate) => void;
  selectedType: string;
  setSelectedType: StateSetter<string>;
  setStep: StateSetter<AgentWizardStep>;
};

export function AgentWizardTemplateStep({
  lang,
  mode,
  setMode,
  templates,
  onSelectTemplate,
  selectedType,
  setSelectedType,
  setStep,
}: AgentWizardTemplateStepProps) {
  return (
    <>
      <section className="space-y-3">
        <div>
          <p className="type-label text-primary">{localize(lang, "Шаг 1", "Step 1")}</p>
          <h3 className="mt-1 font-display text-lg font-bold tracking-tight text-foreground">
            {localize(lang, "Какую работу поручить?", "What work should this agent own?")}
          </h3>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {localize(
              lang,
              "Начните с чистого профиля или возьмите пример. Это не узкий бот: дальше вы зададите цель, системы, инструменты, права и способ запуска.",
              "Start with a blank profile or an example. This is not a single-purpose bot: next you will set the goal, systems, tools, permissions, and trigger.",
            )}
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-sm border border-border bg-surface-0/50 p-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground"><Workflow className="h-4 w-4 text-primary" /> {localize(lang, "Любой IT-процесс", "Any IT process")}</div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Логи, доступы, релизы, проверки, сопровождение и собственные регламенты.", "Logs, access, releases, checks, operations, and your own procedures.")}</p>
          </div>
          <div className="rounded-sm border border-border bg-surface-0/50 p-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground"><KeyRound className="h-4 w-4 text-primary" /> {localize(lang, "Ваши системы и правила", "Your systems and rules")}</div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{localize(lang, "Агент использует только выбранные серверы, навыки, материалы и разрешения.", "The agent uses only the selected servers, skills, materials, and permissions.")}</p>
          </div>
        </div>
      </section>

      <details className="group rounded-sm border border-border bg-surface-0/35">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-foreground">
          <span>
            {localize(lang, "Как выполняется агент", "How the agent runs")}
            <span className="ml-2 font-normal text-muted-foreground">· {mode === "full" ? localize(lang, "универсальный", "general") : mode === "mini" ? localize(lang, "командный", "command") : localize(lang, "оркестратор", "orchestrator")}</span>
          </span>
          <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <div className="space-y-3 border-t border-border px-4 py-4">
          <p className="text-xs leading-5 text-muted-foreground">
            {localize(lang, "Для большинства задач подходит универсальный режим.", "The general mode fits most tasks.")}
          </p>
        <div className="grid gap-3 md:grid-cols-3">
          {[
            {
              key: "full" as const,
              icon: Brain,
              label: localize(lang, "Универсальный", "General agent"),
              text: localize(lang, "Сам решает шаги к цели, используя инструменты и проверки.", "Decides the steps toward a goal on its own, using tools and checks."),
              when: localize(lang, "Рекомендуется", "Recommended"),
              accent: "text-ai border-ai/30 bg-ai/10",
            },
            {
              key: "mini" as const,
              icon: Terminal,
              label: localize(lang, "Командный", "Command agent"),
              text: localize(lang, "Выполняет заданный список команд и делает краткий разбор результата.", "Runs a fixed list of commands and briefly analyses the result."),
              when: localize(lang, "Быстрый старт · без фонового обработчика", "Quick start · no background worker"),
              accent: "text-primary border-primary/30 bg-primary/10",
            },
            {
              key: "multi" as const,
              icon: Layers,
              label: localize(lang, "Оркестратор", "Orchestrator"),
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
        </div>
      </details>

      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {localize(lang, "Стартовая точка", "Starting point")}
          </h3>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <button
            type="button"
            aria-pressed={selectedType === "custom"}
            onClick={() => {
              setSelectedType("custom");
              setStep("basics");
            }}
            className={cn(
              "min-h-[104px] rounded-sm border border-dashed p-4 text-left transition-colors",
              selectedType === "custom"
                ? "border-primary bg-primary/10 shadow-elev-1"
                : "border-primary/40 bg-primary/5 hover:border-primary hover:bg-primary/10",
            )}
          >
            <div className="mb-3 flex items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-primary/30 bg-primary/10 text-primary">
                <Settings2 className="h-4 w-4" />
              </span>
              <span className="min-w-0 truncate text-sm font-semibold text-foreground">
                {localize(lang, "Вручную", "Custom")}
              </span>
            </div>
            <p className="line-clamp-2 text-xs leading-5 text-foreground">
              {localize(
                lang,
                "Рекомендуется · настройте сотрудника под свою задачу",
                "Recommended · configure an employee for your task",
              )}
            </p>
          </button>
          {templates.map((tpl) => {
            const TemplateIcon = AGENT_ICONS[tpl.type] || Settings2;
            const templateActive = selectedType === tpl.type;
            return (
              <button
                key={tpl.type}
                type="button"
                aria-pressed={templateActive}
                onClick={() => onSelectTemplate(tpl)}
                className={cn(
                  "min-h-[104px] rounded-sm border p-4 text-left transition-colors",
                  templateActive
                    ? "border-primary bg-primary/10 shadow-elev-1"
                    : "border-border bg-surface-1 hover:border-primary/50 hover:bg-primary/5",
                )}
              >
                <div className="mb-3 flex items-center gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-2 text-primary">
                    <TemplateIcon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 truncate text-sm font-semibold text-foreground">{tpl.name}</span>
                </div>
                <p className="line-clamp-2 text-xs leading-5 text-foreground">
                  {tpl.mode === "full" || tpl.mode === "multi"
                    ? (tpl.goal || localize(lang, "Автономная задача", "Autonomous task"))
                    : localize(lang, `${tpl.command_count} команд`, `${tpl.command_count} commands`)}
                </p>
              </button>
            );
          })}
        </div>
      </section>
    </>
  );
}
