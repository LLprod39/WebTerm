import {
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  FileText,
  FolderKanban,
  ListChecks,
  MoreVertical,
  Plus,
  Search,
  Sparkles,
  Target,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { QueryStateBlock, StatusBadge } from "@/components/ui/page-shell";
import type { MarsProject, MarsRun } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  ORCHESTRATOR_PHASES,
  statusTone,
  stepIndexLabel,
  type MarsPhaseId,
  type WizardStepId,
  type WizardStepMeta,
} from "./MarsPageUtils";

type WizardNavProps = {
  activeStep: WizardStepId;
  steps: WizardStepMeta[];
  onStepChange: (step: WizardStepId) => void;
};

export function MarsWizardNav({ activeStep, steps, onStepChange }: WizardNavProps) {
  return (
    <div className="rounded-lg border border-border/80 bg-card/95 p-2 shadow-[0_14px_42px_hsl(var(--background)_/_0.2)]">
      <div className="grid gap-2 xl:grid-cols-4">
        {steps.map((step, index) => {
          const StepIcon = step.icon;
          const active = step.id === activeStep;
          return (
            <button
              key={step.id}
              type="button"
              onClick={() => step.available && onStepChange(step.id)}
              disabled={!step.available}
              aria-current={active ? "step" : undefined}
              className={cn(
                "group relative flex min-h-[82px] items-center gap-3 rounded-lg border px-3 py-3 text-left transition-colors",
                active ? "border-primary/45 bg-primary/10 shadow-sm" : "border-transparent bg-transparent hover:border-border hover:bg-secondary/40",
                !step.available && "cursor-not-allowed opacity-45 hover:border-transparent hover:bg-transparent",
              )}
            >
              <span
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border text-xs font-semibold",
                  step.done || active
                    ? "border-primary/35 bg-primary/10 text-primary"
                    : "border-border/70 bg-secondary/60 text-muted-foreground",
                )}
              >
                {step.done ? <Check className="h-4 w-4" /> : <StepIcon className="h-4 w-4" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <span className="font-mono text-xs text-primary">{stepIndexLabel(index)}</span>
                  <span className="truncate">{step.label}</span>
                </span>
                <span className="mt-1 block line-clamp-2 text-xs leading-5 text-muted-foreground">{step.description}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

type PageLayoutProps = {
  children: ReactNode;
  projectHistory: ReactNode;
  statusRail?: ReactNode;
};

export function MarsPageLayout({ children, projectHistory, statusRail }: PageLayoutProps) {
  return (
    <div className={cn("grid gap-5", statusRail && "2xl:grid-cols-[minmax(0,1fr)_380px]")}>
      <main className="min-w-0 space-y-5">
        {children}
        {projectHistory}
      </main>
      {statusRail ? <aside className="min-w-0 space-y-4 2xl:sticky 2xl:top-5 2xl:self-start">{statusRail}</aside> : null}
    </div>
  );
}

function projectStatus(project: MarsProject): string {
  return project.latest_run?.status || project.session.status;
}

function projectUpdatedAt(project: MarsProject): string {
  const value = project.latest_run?.completed_at || project.latest_run?.started_at || project.session.updated_at || project.session.created_at;
  return value ? new Date(value).toLocaleString() : "";
}

function projectKindLabel(lang: string, brief: string): string {
  const text = brief.toLowerCase();
  if (/(web|сайт|веб|frontend|панель|dashboard)/i.test(text)) return localize(lang, "ВЕБ-ПРИЛОЖЕНИЕ", "WEB APP");
  if (/(bot|бот|telegram|tg)/i.test(text)) return localize(lang, "БОТ", "BOT");
  if (/(game|игр|змейк)/i.test(text)) return localize(lang, "МИНИ-ИГРА", "MINI GAME");
  if (/(script|скрипт|python|automation|автоматизац)/i.test(text)) return localize(lang, "СКРИПТ", "SCRIPT");
  return localize(lang, "ПРОЕКТ", "PROJECT");
}

type ProjectRailProps = {
  lang: string;
  projects: MarsProject[];
  loading: boolean;
  error: unknown;
  search: string;
  selectedSessionId: number | null;
  onSearchChange: (value: string) => void;
  onNewProject: () => void;
  onSelectProject: (project: MarsProject) => void;
  onOpenRun: (runId: number) => void;
};

export function MarsProjectRail({
  lang,
  projects,
  loading,
  error,
  search,
  selectedSessionId,
  onSearchChange,
  onNewProject,
  onSelectProject,
  onOpenRun,
}: ProjectRailProps) {
  const [open, setOpen] = useState(true);

  return (
    <section className="overflow-hidden rounded-lg border border-border/80 bg-card/95 shadow-[0_14px_42px_hsl(var(--background)_/_0.2)]">
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex flex-col gap-3 border-b border-border/70 bg-secondary/25 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">{localize(lang, "История проектов", "Project history")}</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {localize(lang, "Все проекты MARS, созданные через пошаговый мастер.", "All MARS projects created through the step-by-step wizard.")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {projects.length > 6 ? (
              <div className="relative hidden w-56 sm:block">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(event) => onSearchChange(event.target.value)}
                  placeholder={localize(lang, "Поиск", "Search")}
                  className="h-8 bg-background pl-8 text-xs"
                />
              </div>
            ) : null}
            <Button size="sm" variant="outline" onClick={onNewProject} className="h-8 text-xs">
              <Plus className="h-3.5 w-3.5" />
              {localize(lang, "Новый", "New")}
            </Button>
            <CollapsibleTrigger asChild>
              <Button size="sm" variant="ghost" className="h-8 text-xs">
                {open ? localize(lang, "Свернуть", "Collapse") : localize(lang, "Все проекты", "All projects")}
                <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
              </Button>
            </CollapsibleTrigger>
          </div>
        </div>

        <CollapsibleContent>
          <QueryStateBlock loading={loading} error={error}>
            <div className="divide-y divide-border/70 px-4 py-3">
              {projects.map((project) => {
                const selected = project.session.id === selectedSessionId;
                const status = projectStatus(project);
                return (
                  <div
                    key={project.session.id}
                    className={cn(
                      "group grid min-h-[62px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-2 py-2 transition-colors sm:grid-cols-[minmax(0,1fr)_170px_88px_28px]",
                      selected ? "bg-primary/10" : "hover:bg-secondary/40",
                    )}
                  >
                    <button type="button" onClick={() => onSelectProject(project)} className="flex min-w-0 items-center gap-3 text-left">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
                        <FileText className="h-4 w-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="flex min-w-0 flex-wrap items-center gap-2">
                          <span className="truncate text-sm font-semibold text-foreground">{project.session.task_brief}</span>
                          <span className="rounded-md border border-border/70 bg-secondary/60 px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            {projectKindLabel(lang, project.session.task_brief)}
                          </span>
                        </span>
                        <span className="mt-1 block truncate text-xs text-muted-foreground">
                          {localize(lang, `${project.run_count} запусков`, `${project.run_count} runs`)}
                        </span>
                      </span>
                    </button>
                    <div className="hidden text-right text-xs text-muted-foreground sm:block">{projectUpdatedAt(project)}</div>
                    <div className="flex justify-end">
                      <StatusBadge label={status.replaceAll("_", " ")} tone={statusTone(status)} />
                    </div>
                    <button
                      type="button"
                      onClick={() => (project.latest_run ? onOpenRun(project.latest_run.id) : onSelectProject(project))}
                      aria-label={localize(lang, "Открыть проект", "Open project")}
                      className="hidden h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground sm:flex"
                    >
                      <MoreVertical className="h-4 w-4" />
                    </button>
                  </div>
                );
              })}
              {!projects.length ? (
                <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border/70 bg-secondary/20 px-4 py-10 text-center">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
                    <FolderKanban className="h-5 w-5" />
                  </div>
                  <div className="mt-3 text-sm font-semibold text-foreground">{localize(lang, "Проектов пока нет", "No projects yet")}</div>
                  <div className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
                    {localize(lang, "Создайте первый проект через пошаговое описание задачи.", "Create the first project through the step-by-step task flow.")}
                  </div>
                </div>
              ) : null}
            </div>
          </QueryStateBlock>
        </CollapsibleContent>
      </Collapsible>
    </section>
  );
}

const phaseIcons: Record<MarsPhaseId, ReactNode> = {
  architect: <Target className="h-3.5 w-3.5" />,
  executor: <Sparkles className="h-3.5 w-3.5" />,
  verifier: <FileText className="h-3.5 w-3.5" />,
  repair: <CheckCircle2 className="h-3.5 w-3.5" />,
  reviewer: <ListChecks className="h-3.5 w-3.5" />,
};

type OrchestratorRailProps = {
  lang: string;
  latestRun: MarsRun | undefined;
  totalProgress: number;
};

export function MarsOrchestratorRail({ lang, latestRun, totalProgress }: OrchestratorRailProps) {
  const completedIndex = Math.max(0, Math.ceil(totalProgress / 20));
  const runStatus = latestRun?.status || "draft";
  const checklist = [
    localize(lang, "План подтвержден", "Plan approved"),
    localize(lang, "Создание начато", "Build started"),
    localize(lang, "Проверки выполнены", "Checks run"),
    localize(lang, "Отчет собран", "Report collected"),
    localize(lang, "Готов к запуску", "Launch ready"),
  ];

  return (
    <>
      <section className="rounded-lg border border-border/80 bg-card/95 p-4 shadow-[0_14px_42px_hsl(var(--background)_/_0.2)]">
        <h2 className="text-sm font-semibold text-foreground">{localize(lang, "Статус выполнения", "Run status")}</h2>
        <div className="mt-4 grid grid-cols-[86px_minmax(0,1fr)] items-center gap-4">
          <div
            className="flex h-[82px] w-[82px] items-center justify-center rounded-full p-[4px]"
            style={{
              background: `conic-gradient(hsl(var(--primary)) ${Math.max(0, Math.min(100, totalProgress)) * 3.6}deg, hsl(var(--border) / 0.65) 0deg)`,
            }}
          >
            <div className="flex h-full w-full items-center justify-center rounded-full bg-card text-2xl font-semibold text-foreground">
              {totalProgress}%
            </div>
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium text-foreground">{localize(lang, "Готовность к запуску", "Launch readiness")}</div>
            <div className="mt-3 space-y-1.5">
              {checklist.map((item, index) => {
                const done = totalProgress >= (index + 1) * 20 || runStatus === "completed";
                return (
                  <div key={item} className="grid grid-cols-[minmax(0,1fr)_32px] gap-2 text-xs leading-4">
                    <span className={cn("truncate", done ? "text-primary" : "text-muted-foreground")}>{item}</span>
                    <span className="text-right text-muted-foreground">{done ? "1/1" : "0/1"}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-border/80 bg-card/95 p-4 shadow-[0_14px_42px_hsl(var(--background)_/_0.2)]">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-foreground">{localize(lang, "План выполнения", "Run plan")}</h2>
          <span className="rounded-md border border-border/70 bg-secondary/60 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {localize(lang, "Авто", "Auto")}
          </span>
        </div>
        <div className="mt-4 space-y-2">
          {ORCHESTRATOR_PHASES.map((phase, index) => {
            const done = index < completedIndex || runStatus === "completed";
            return (
              <div key={phase.id} className="rounded-lg border border-border/80 bg-secondary/20 px-3 py-3">
                <div className="grid grid-cols-[24px_minmax(0,1fr)_20px] items-start gap-3">
                  <span className="flex h-6 w-6 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-xs font-semibold text-primary">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <span className="text-primary">{phaseIcons[phase.id]}</span>
                      <span className="truncate">{localize(lang, phase.ru, phase.en)}</span>
                    </div>
                    <div className="mt-1 line-clamp-2 text-xs leading-4 text-muted-foreground">
                      {localize(lang, phase.descriptionRu, phase.descriptionEn)}
                    </div>
                  </div>
                  <span
                    className={cn(
                      "mt-0.5 flex h-5 w-5 items-center justify-center rounded-full border",
                      done ? "border-primary bg-primary text-primary-foreground" : "border-border text-transparent",
                    )}
                  >
                    <Check className="h-3 w-3" />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-lg border border-border/80 bg-card/95 p-4 shadow-[0_14px_42px_hsl(var(--background)_/_0.2)]">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/60 text-muted-foreground">
            <CircleHelp className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-foreground">{localize(lang, "Нужна помощь?", "Need help?")}</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {localize(lang, "Откройте документацию или напишите в поддержку.", "Open documentation or contact support.")}
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <Button variant="outline" size="sm" className="h-8 text-xs">
            <CircleHelp className="h-3.5 w-3.5" />
            {localize(lang, "Поддержка", "Support")}
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs">
            <Clock3 className="h-3.5 w-3.5" />
            {localize(lang, "Документация", "Docs")}
          </Button>
        </div>
      </section>
    </>
  );
}
