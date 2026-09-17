import type { LucideIcon } from "lucide-react";
import type { MarsInterviewQuestion } from "@/lib/api";
import { localize } from "@/lib/i18n";

export type WizardStepId = "brief" | "interview" | "plan" | "run";

export type WizardStepMeta = {
  id: WizardStepId;
  label: string;
  title: string;
  description: string;
  done: boolean;
  available: boolean;
  icon: LucideIcon;
};

export type MarsPhaseId = "architect" | "executor" | "verifier" | "repair" | "reviewer";

export const ORCHESTRATOR_PHASES: Array<{
  id: MarsPhaseId;
  ru: string;
  en: string;
  descriptionRu: string;
  descriptionEn: string;
  mode: string;
}> = [
  {
    id: "architect",
    ru: "Понимание задачи",
    en: "Task understanding",
    descriptionRu: "Уточняет цель, ограничения и критерии готовности.",
    descriptionEn: "Clarifies the goal, constraints, and completion criteria.",
    mode: "auto",
  },
  {
    id: "executor",
    ru: "Проработка",
    en: "Project shaping",
    descriptionRu: "Готовит структуру, выбирает подход и собирает основу решения.",
    descriptionEn: "Prepares the structure, approach, and solution base.",
    mode: "auto",
  },
  {
    id: "verifier",
    ru: "Кодирование",
    en: "Creation",
    descriptionRu: "Создает файлы, меняет код и собирает рабочий результат.",
    descriptionEn: "Creates files, changes code, and assembles the result.",
    mode: "auto",
  },
  {
    id: "repair",
    ru: "Тестирование",
    en: "Testing",
    descriptionRu: "Запускает проверки и исправляет найденные ошибки.",
    descriptionEn: "Runs checks and fixes discovered issues.",
    mode: "auto",
  },
  {
    id: "reviewer",
    ru: "Итог",
    en: "Result",
    descriptionRu: "Собирает результат, проверки и готовность к запуску.",
    descriptionEn: "Summarizes the result, checks, and launch readiness.",
    mode: "auto",
  },
];

export const TASK_STARTERS = [
  {
    ru: "Создать Python-скрипт, который собирает данные, чистит их и сохраняет отчет.",
    en: "Create a Python script that collects data, cleans it, and saves a report.",
  },
  {
    ru: "Сделать небольшой web-проект с формой, таблицей и сохранением результата.",
    en: "Build a small web project with a form, table, and saved result.",
  },
  {
    ru: "Написать автоматизацию, которая запускается одной командой и проверяет результат.",
    en: "Write an automation that runs with one command and verifies the result.",
  },
];

export function mutationMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

export function statusTone(status?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (!status) return "neutral";
  if (status === "approved" || status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "running" || status === "queued") return "info";
  if (status === "plan_ready") return "warning";
  return "neutral";
}

export function statusLabel(status: string | undefined, lang: string): string {
  if (status === "draft") return localize(lang, "Черновик", "Draft");
  if (status === "interview") return localize(lang, "Уточнение", "Clarifying");
  if (status === "plan_ready") return localize(lang, "План готов", "Plan ready");
  if (status === "approved") return localize(lang, "Готов к запуску", "Ready to run");
  if (status === "queued") return localize(lang, "В очереди", "Queued");
  if (status === "running") return localize(lang, "Выполняется", "Running");
  if (status === "completed") return localize(lang, "Завершено", "Completed");
  if (status === "failed") return localize(lang, "Ошибка", "Failed");
  if (status === "stopped") return localize(lang, "Остановлено", "Stopped");
  return status ? status.replaceAll("_", " ") : localize(lang, "Не начато", "Not started");
}

export function isMultiQuestion(question: MarsInterviewQuestion): boolean {
  return question.kind.includes("multi");
}

export function splitAnswer(value: string): string[] {
  return value
    .split(/[;\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function joinAnswer(items: string[]): string {
  return items.join("; ");
}

export function stepIndexLabel(index: number): string {
  return String(index + 1).padStart(2, "0");
}
