import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
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
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { QueryStateBlock, StatusBadge } from "@/components/ui/page-shell";
import { Progress } from "@/components/ui/progress";
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
    <div className="rounded-xl border border-[#26313a] bg-[#101720]/88 p-2 shadow-[0_18px_60px_rgba(0,0,0,0.35)]">
      <div className="grid gap-2 xl:grid-cols-5">
        {steps.map((step, index) => {
          const StepIcon = step.icon;
          const active = step.id === activeStep || (step.id === "final" && activeStep === "run");
          return (
            <button
              key={`${step.id}-${index}`}
              type="button"
              onClick={() => step.available && onStepChange(step.id === "final" ? "run" : step.id)}
              disabled={!step.available}
              className={cn(
                "group relative flex min-h-[82px] items-center gap-3 rounded-lg border px-3 py-3 text-left transition-all",
                active
                  ? "border-emerald-400/55 bg-[linear-gradient(135deg,rgba(22,163,127,0.22),rgba(12,31,36,0.94))] shadow-[0_0_0_1px_rgba(52,211,153,0.08),0_18px_42px_rgba(5,150,105,0.12)]"
                  : "border-transparent bg-transparent hover:border-[#2c3842] hover:bg-[#151d26]",
                !step.available && "cursor-not-allowed opacity-45 hover:border-transparent hover:bg-transparent",
              )}
            >
              <span
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border text-xs font-semibold",
                  step.done
                    ? "border-emerald-400/45 bg-emerald-400/15 text-emerald-300"
                    : active
                      ? "border-emerald-400/40 bg-emerald-400/15 text-emerald-300"
                      : "border-[#303942] bg-[#171f28] text-slate-400",
                )}
              >
                {step.done ? <Check className="h-4 w-4" /> : <StepIcon className="h-4 w-4" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2 text-[13px] font-semibold text-slate-100">
                  <span className="font-mono text-[11px] text-emerald-300">{stepIndexLabel(index)}</span>
                  <span className="truncate">{step.label}</span>
                </span>
                <span className="mt-1 block line-clamp-2 text-[12px] leading-5 text-slate-400">{step.description}</span>
              </span>
              {index < steps.length - 1 ? <ChevronRight className="hidden h-4 w-4 shrink-0 text-slate-500 xl:block" /> : null}
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
  statusRail: ReactNode;
};

export function MarsPageLayout({ children, projectHistory, statusRail }: PageLayoutProps) {
  return (
    <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_380px]">
      <main className="min-w-0 space-y-5">
        {children}
        {projectHistory}
      </main>
      <aside className="min-w-0 space-y-4 2xl:sticky 2xl:top-5 2xl:self-start">{statusRail}</aside>
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
  return (
    <section className="overflow-hidden rounded-xl border border-[#27323b] bg-[#111922]/88 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
      <div className="flex flex-col gap-3 border-b border-[#26313a] px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">{localize(lang, "История проектов", "Project history")}</h2>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            {localize(lang, "Все scripts, automation и проекты, которые вы создавали через MARS.", "All scripts, automations, and projects created through MARS.")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {projects.length > 6 ? (
            <div className="relative hidden w-56 sm:block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
              <Input
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder={localize(lang, "Поиск", "Search")}
                className="h-8 border-[#2b3640] bg-[#0c1218] pl-8 text-xs"
              />
            </div>
          ) : null}
          <Button size="sm" variant="outline" onClick={onNewProject} className="h-8 border-[#2b3640] bg-[#151d26] text-xs">
            <Plus className="h-3.5 w-3.5" />
            {localize(lang, "Новый", "New")}
          </Button>
          <Button size="sm" variant="ghost" className="h-8 text-xs text-slate-300">
            {localize(lang, "Все проекты", "All projects")}
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <QueryStateBlock loading={loading} error={error}>
        <div className="divide-y divide-[#26313a] px-4 py-3">
          {projects.map((project) => {
            const selected = project.session.id === selectedSessionId;
            const status = projectStatus(project);
            return (
              <div
                key={project.session.id}
                className={cn(
                  "group grid min-h-[62px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-2 py-2 transition-colors sm:grid-cols-[minmax(0,1fr)_170px_88px_28px]",
                  selected ? "bg-emerald-400/8" : "hover:bg-[#151d26]",
                )}
              >
                <button type="button" onClick={() => onSelectProject(project)} className="flex min-w-0 items-center gap-3 text-left">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-400/12 text-emerald-300">
                    <FileText className="h-4 w-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-semibold text-slate-100">{project.session.task_brief}</span>
                      <span className="rounded bg-slate-600/35 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-300">
                        {projectKindLabel(lang, project.session.task_brief)}
                      </span>
                    </span>
                    <span className="mt-1 block truncate text-xs text-slate-400">
                      {localize(lang, `${project.run_count} запусков`, `${project.run_count} runs`)}
                    </span>
                  </span>
                </button>
                <div className="hidden text-right text-xs text-slate-400 sm:block">{projectUpdatedAt(project)}</div>
                <div className="flex justify-end">
                  <StatusBadge label={status.replaceAll("_", " ")} tone={statusTone(status)} />
                </div>
                <button
                  type="button"
                  onClick={() => (project.latest_run ? onOpenRun(project.latest_run.id) : onSelectProject(project))}
                  aria-label={localize(lang, "Открыть проект", "Open project")}
                  className="hidden h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-[#202a34] hover:text-slate-200 sm:flex"
                >
                  <MoreVertical className="h-4 w-4" />
                </button>
              </div>
            );
          })}
          {!projects.length ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-[#2b3640] bg-[#0e151d] px-4 py-10 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-400/10 text-emerald-300">
                <FolderKanban className="h-5 w-5" />
              </div>
              <div className="mt-3 text-sm font-semibold text-slate-100">{localize(lang, "Проектов пока нет", "No projects yet")}</div>
              <div className="mt-1 max-w-sm text-xs leading-5 text-slate-400">
                {localize(lang, "Создайте первый скрипт, автоматизацию или проект через guided brief.", "Create the first script, automation, or project through the guided brief.")}
              </div>
            </div>
          ) : null}
        </div>
      </QueryStateBlock>
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
    localize(lang, "ТЗ согласовано", "Spec approved"),
    localize(lang, "Код написан", "Code created"),
    localize(lang, "Тестирование", "Testing"),
    localize(lang, "Документация", "Documentation"),
    localize(lang, "Готов к запуску", "Launch ready"),
  ];

  return (
    <>
      <section className="rounded-xl border border-[#27323b] bg-[#111922]/88 p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
        <h2 className="text-sm font-semibold text-slate-100">{localize(lang, "Статус проекта", "Project status")}</h2>
        <div className="mt-4 grid grid-cols-[86px_minmax(0,1fr)] items-center gap-4">
          <div
            className="flex h-[82px] w-[82px] items-center justify-center rounded-full p-[4px]"
            style={{
              background: `conic-gradient(rgb(52 211 153) ${Math.max(0, Math.min(100, totalProgress)) * 3.6}deg, rgba(45,55,66,0.85) 0deg)`,
            }}
          >
            <div className="flex h-full w-full items-center justify-center rounded-full bg-[#111922] text-2xl font-semibold text-slate-100">
              {totalProgress}%
            </div>
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium text-slate-200">{localize(lang, "Готовность к запуску", "Launch readiness")}</div>
            <div className="mt-3 space-y-1.5">
              {checklist.map((item, index) => {
                const done = totalProgress >= (index + 1) * 20 || runStatus === "completed";
                return (
                  <div key={item} className="grid grid-cols-[minmax(0,1fr)_32px] gap-2 text-[11px] leading-4">
                    <span className={cn("truncate", done ? "text-emerald-300" : "text-slate-400")}>- {item}</span>
                    <span className="text-right text-slate-400">{done ? "1/1" : "0/1"}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-[#27323b] bg-[#111922]/88 p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-100">{localize(lang, "Планируемые задачи", "Planned tasks")}</h2>
          <span className="rounded-md border border-[#303b45] bg-[#1a232d] px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-300">
            {localize(lang, "Авто", "Auto")}
          </span>
        </div>
        <div className="mt-4 space-y-2">
          {ORCHESTRATOR_PHASES.map((phase, index) => {
            const done = index < completedIndex || runStatus === "completed";
            return (
              <div key={phase.id} className="rounded-lg border border-[#26313a] bg-[#0f171f] px-3 py-3">
                <div className="grid grid-cols-[24px_minmax(0,1fr)_20px] items-start gap-3">
                  <span className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-400/12 text-[11px] font-semibold text-emerald-300">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                      <span className="text-emerald-300">{phaseIcons[phase.id]}</span>
                      <span className="truncate">{localize(lang, phase.ru, phase.en)}</span>
                    </div>
                    <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-400">
                      {localize(lang, phase.descriptionRu, phase.descriptionEn)}
                    </div>
                  </div>
                  <span
                    className={cn(
                      "mt-0.5 flex h-5 w-5 items-center justify-center rounded-full border",
                      done ? "border-emerald-400 bg-emerald-400 text-[#07110f]" : "border-[#3a4652] text-transparent",
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

      <section className="rounded-xl border border-[#27323b] bg-[#111922]/88 p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-400/12 text-emerald-300">
            <CircleHelp className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-slate-100">{localize(lang, "Нужна помощь?", "Need help?")}</h2>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              {localize(lang, "Откройте документацию или напишите в поддержку.", "Open documentation or contact support.")}
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <Button variant="outline" size="sm" className="h-8 border-[#2b3640] bg-[#0f171f] text-xs">
            <CircleHelp className="h-3.5 w-3.5" />
            {localize(lang, "Поддержка", "Support")}
          </Button>
          <Button variant="outline" size="sm" className="h-8 border-[#2b3640] bg-[#0f171f] text-xs">
            <Clock3 className="h-3.5 w-3.5" />
            {localize(lang, "Документация", "Docs")}
          </Button>
        </div>
      </section>
    </>
  );
}
