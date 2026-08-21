import type { Dispatch, SetStateAction } from "react";
import type { LucideIcon } from "lucide-react";
import { Play } from "lucide-react";

import { InlineAlert } from "@/components/system/InlineAlert";
import type { AgentInputArtifact } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { AgentWizardCheck } from "./agentPageUtils";

export type SummaryRow = { icon: LucideIcon; label: string; value: string };

type AgentWizardReviewStepProps = {
  lang: string;
  summaryRows: SummaryRow[];
  commandCount: number;
  selectedSkillSlugs: string[];
  inputArtifacts: AgentInputArtifact[];
  telegramEnabled: boolean;
  readiness: number;
  readinessChecks: AgentWizardCheck[];
  runAfterSave?: boolean;
  setRunAfterSave?: Dispatch<SetStateAction<boolean>>;
  isEditing?: boolean;
};

export function AgentWizardReviewStep({
  lang,
  summaryRows,
  commandCount,
  selectedSkillSlugs,
  inputArtifacts,
  telegramEnabled,
  readiness,
  readinessChecks,
  runAfterSave = false,
  setRunAfterSave,
  isEditing = false,
}: AgentWizardReviewStepProps) {
  const extras: string[] = [];
  if (commandCount) extras.push(localize(lang, `${commandCount} команд`, `${commandCount} commands`));
  if (selectedSkillSlugs.length) extras.push(localize(lang, `${selectedSkillSlugs.length} скиллов`, `${selectedSkillSlugs.length} skills`));
  if (inputArtifacts.length) extras.push(localize(lang, `${inputArtifacts.length} материалов контекста`, `${inputArtifacts.length} context materials`));
  if (telegramEnabled) extras.push("Telegram");

  const failed = readinessChecks.filter((check) => !check.passed);

  return (
    <section className="space-y-5">
      <div>
        <h3 className="font-display text-sm font-bold tracking-tight text-foreground">
          {localize(lang, "Как будет работать цифровой сотрудник", "How this digital employee will work")}
        </h3>
        <p className="mt-1 text-sm leading-5 text-muted-foreground">
          {localize(
            lang,
            "Проверьте задачу, системы, границы, запуск и канал результата. Безопасный вариант — сначала сохранить профиль.",
            "Review the task, systems, boundaries, trigger, and result channel. The safe option is to save the profile first.",
          )}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
        <dl className="divide-y divide-border overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
          {summaryRows.map((row) => {
            const Icon = row.icon;
            return (
              <div key={row.label} className="flex items-center gap-3 px-4 py-3.5">
                <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <dt className="w-32 shrink-0 text-sm text-muted-foreground sm:w-36">{row.label}</dt>
                <dd className="min-w-0 truncate text-sm font-medium text-foreground">{row.value}</dd>
              </div>
            );
          })}
          {extras.length ? (
            <div className="flex items-center gap-3 px-4 py-3.5">
              <span className="h-4 w-4 shrink-0" aria-hidden />
              <dt className="w-32 shrink-0 text-sm text-muted-foreground sm:w-36">
                {localize(lang, "Дополнительно", "Extras")}
              </dt>
              <dd className="min-w-0 truncate text-sm text-foreground">{extras.join(" · ")}</dd>
            </div>
          ) : null}
        </dl>

        <aside className="flex flex-col justify-between gap-3 rounded-sm border border-border bg-surface-0 p-4">
          <div>
            <p className="type-label text-muted-foreground">{localize(lang, "Конфигурация", "Configuration")}</p>
            <p
              className={cn(
                "mt-2 font-display text-3xl font-bold tracking-tight",
                readiness === 100 ? "text-success" : readiness >= 70 ? "text-warning" : "text-destructive",
              )}
            >
              {readiness}%
            </p>
            <div className="mt-3 h-1.5 overflow-hidden rounded-sm bg-surface-2">
              <div
                className={cn(
                  "h-full transition-[width] duration-500",
                  readiness === 100 ? "bg-success" : readiness >= 70 ? "bg-warning" : "bg-destructive",
                )}
                style={{ width: `${readiness}%` }}
              />
            </div>
          </div>
          {failed.length ? (
            <ul className="space-y-1.5 text-xs leading-5 text-muted-foreground">
              {failed.slice(0, 4).map((check) => (
                <li key={check.key}>· {localize(lang, check.labelRu, check.labelEn)}</li>
              ))}
            </ul>
          ) : (
            <p className="text-xs leading-5 text-success">
              {localize(lang, "Все обязательные поля заполнены.", "All required fields are set.")}
            </p>
          )}
        </aside>
      </div>

      {!isEditing && setRunAfterSave ? (
        <label
          className={cn(
            "flex cursor-pointer items-start gap-3 rounded-sm border p-4 transition-colors",
            runAfterSave
              ? "border-primary/45 bg-primary/10"
              : "border-border bg-card hover:border-primary/35",
          )}
        >
          <input
            type="checkbox"
            className="mt-1"
            checked={runAfterSave}
            onChange={(event) => setRunAfterSave(event.target.checked)}
          />
          <span className="min-w-0">
            <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Play className="h-4 w-4 text-primary" />
              {localize(lang, "Запустить после создания", "Run after create")}
            </span>
            <span className="mt-1 block text-xs leading-5 text-muted-foreground">
              {localize(
                lang,
                "Явное действие: после сохранения агент сразу начнёт работу в выбранных системах.",
                "Explicit action: after saving, the agent immediately starts work in the selected systems.",
              )}
            </span>
          </span>
        </label>
      ) : null}

      {readiness < 100 ? (
        <InlineAlert
          tone="warning"
          title={localize(lang, "Ещё не всё готово", "Not everything is ready yet")}
          description={localize(
            lang,
            failed.map((check) => check.labelRu).join(" · "),
            failed.map((check) => check.labelEn).join(" · "),
          )}
        />
      ) : (
        <InlineAlert
          tone="success"
          title={
            runAfterSave && !isEditing
              ? localize(lang, "Готово к созданию и запуску", "Ready to create and run")
              : localize(lang, "Готово к сохранению", "Ready to save")
          }
          description={
            runAfterSave && !isEditing
              ? localize(lang, "Агент будет создан и сразу запущен на выбранных серверах.", "The agent will be created and started on the selected servers.")
              : localize(lang, "Профиль будет сохранён. Запустить его можно из списка цифровых сотрудников.", "The profile will be saved. You can start it from the digital employees list.")
          }
        />
      )}
    </section>
  );
}
