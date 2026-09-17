import { BellRing, BrainCircuit, Cable, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { localize } from "@/lib/i18n";

type AgentExperienceIntroProps = {
  lang: string;
  onCreate: () => void;
};

export function AgentExperienceIntro({ lang, onCreate }: AgentExperienceIntroProps) {
  const capabilities = [
    {
      icon: BrainCircuit,
      titleRu: "Получает IT-задачу",
      titleEn: "Takes an IT task",
      textRu: "Диагностика, доступы, сопровождение, проверки, развёртывание или свой процесс.",
      textEn: "Diagnostics, access, operations, checks, deployment, or your own process.",
    },
    {
      icon: Cable,
      titleRu: "Работает в ваших системах",
      titleEn: "Works in your systems",
      textRu: "Серверы, инструкции, материалы, доступные навыки и подключённые через них инструменты.",
      textEn: "Servers, instructions, materials, available skills, and their connected tools.",
    },
    {
      icon: ShieldCheck,
      titleRu: "Действует в границах",
      titleEn: "Stays within boundaries",
      textRu: "Read-only по умолчанию; опасные действия и sudo требуют явного разрешения.",
      textEn: "Read-only by default; risky actions and sudo require explicit permission.",
    },
    {
      icon: BellRing,
      titleRu: "Запускается и отчитывается",
      titleEn: "Runs and reports",
      textRu: "Вручную или по расписанию, с понятным результатом и уведомлением.",
      textEn: "Manually or on a schedule, with a clear result and notification.",
    },
  ];

  return (
    <section className="overflow-hidden rounded-sm border border-primary/25 bg-card shadow-elev-1">
      <div className="grid gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1.1fr)_auto] lg:items-center lg:px-6">
        <div>
          <p className="type-label text-primary">{localize(lang, "Агенты", "Agents")}</p>
          <h2 className="mt-2 font-display text-xl font-bold tracking-tight text-foreground">
            {localize(lang, "Настройте агента под IT-задачу", "Configure an agent for an IT task")}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {localize(
              lang,
              "Опишите результат, задайте контекст и доступы, ограничьте права — агент выполнит работу и соберёт отчёт.",
              "Describe the outcome, set context and access, define limits — the agent runs the work and produces a report.",
            )}
          </p>
        </div>
        <Button className="gap-2 shadow-elev-1" onClick={onCreate}>
          <BrainCircuit className="h-4 w-4" />
          {localize(lang, "Создать агента", "Create agent")}
        </Button>
      </div>
      <div className="grid border-t border-border bg-surface-0/40 sm:grid-cols-2 xl:grid-cols-4">
        {capabilities.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.titleEn} className="border-b border-border px-4 py-4 last:border-b-0 sm:border-r xl:border-b-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Icon className="h-4 w-4 text-primary" />
                {localize(lang, item.titleRu, item.titleEn)}
              </div>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                {localize(lang, item.textRu, item.textEn)}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
