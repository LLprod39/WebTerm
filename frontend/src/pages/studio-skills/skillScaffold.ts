import type {
  StudioSkillDetail,
  StudioSkillScaffoldPayload,
  StudioSkillTemplate,
  StudioSkillWorkspaceFile,
} from "@/lib/api";

export const SAFETY_LEVELS = ["low", "standard", "medium", "high", "critical"] as const;

export type SkillWizardState = {
  name: string;
  description: string;
  slug: string;
  service: string;
  category: string;
  safety_level: string;
  ui_hint: string;
  tags_text: string;
  guardrail_summary_text: string;
  recommended_tools_text: string;
  runtime_policy_text: string;
  with_scripts: boolean;
  with_references: boolean;
  with_assets: boolean;
  starter_script_enabled: boolean;
  starter_script_content: string;
  starter_reference_enabled: boolean;
  starter_reference_content: string;
  force: boolean;
};

export type SkillSettingsDraft = {
  name: string;
  description: string;
  service: string;
  category: string;
  safety_level: string;
  ui_hint: string;
  tags_text: string;
  guardrail_summary_text: string;
  recommended_tools_text: string;
  runtime_policy_text: string;
};

const DEFAULT_STARTER_SCRIPT_PATH = "scripts/run-checks.sh";
const DEFAULT_STARTER_REFERENCE_PATH = "references/runbook.md";

function defaultStarterScriptContent() {
  return [
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    "",
    "# Read-only starter automation. Replace these checks with the service-specific workflow.",
    'echo "== context =="',
    "date -Is",
    "hostname || true",
    "",
    'echo "== health =="',
    "uptime || true",
    "df -h || true",
    "",
    'echo "== next steps =="',
    'echo "Add preflight checks, exact target discovery, mutation steps, and verification."',
  ].join("\n");
}

function defaultStarterReferenceContent(lang: "ru" | "en" = "en") {
  if (lang === "ru") {
    return [
      "# Рабочая инструкция",
      "",
      "## Когда использовать",
      "",
      "Опишите, для каких задач агент должен применять этот скилл.",
      "",
      "## Что нужно перед запуском",
      "",
      "- Целевой сервис или сервер:",
      "- Нужные доступы или профиль:",
      "- Когда требуется подтверждение:",
      "",
      "## Порядок работы",
      "",
      "1. Проверить контекст и точную цель без изменений.",
      "2. Уточнить опасные или неоднозначные действия.",
      "3. Выполнить минимальное нужное действие.",
      "4. Проверить результат и показать доказательства.",
    ].join("\n");
  }

  return [
    "# Working Runbook",
    "",
    "## When to use",
    "",
    "Describe which tasks should trigger this skill.",
    "",
    "## Before running",
    "",
    "- Target service or server:",
    "- Required access or profile:",
    "- Approval requirements:",
    "",
    "## Workflow",
    "",
    "1. Check context and exact targets without changing anything.",
    "2. Clarify dangerous or ambiguous actions.",
    "3. Execute the minimum required action.",
    "4. Verify the result and report evidence.",
  ].join("\n");
}

function listToCsv(items?: string[]) {
  return (items || []).join(", ");
}

export function parseCsvInput(text: string) {
  return text
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function createSkillSettingsDraft(skill?: StudioSkillDetail | null): SkillSettingsDraft {
  return {
    name: skill?.name || "",
    description: skill?.description || "",
    service: skill?.service || "",
    category: skill?.category || "",
    safety_level: skill?.safety_level || "standard",
    ui_hint: skill?.ui_hint || "",
    tags_text: listToCsv(skill?.tags),
    guardrail_summary_text: (skill?.guardrail_summary || []).join("\n"),
    recommended_tools_text: listToCsv(skill?.recommended_tools),
    runtime_policy_text: JSON.stringify(skill?.runtime_policy || {}, null, 2),
  };
}

export function slugifySkillName(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 64)
    .replace(/-$/g, "");
}

export function createWizardState(
  template?: StudioSkillTemplate | null,
  lang: "ru" | "en" = "en",
): SkillWizardState {
  const defaults = template?.defaults || {};
  const name = defaults.name || "";
  return {
    name,
    description: defaults.description || "",
    slug: slugifySkillName(name),
    service: defaults.service || "",
    category: defaults.category || "",
    safety_level: defaults.safety_level || "standard",
    ui_hint: defaults.ui_hint || "",
    tags_text: listToCsv(defaults.tags),
    guardrail_summary_text: listToCsv(defaults.guardrail_summary),
    recommended_tools_text: listToCsv(defaults.recommended_tools),
    runtime_policy_text: JSON.stringify(defaults.runtime_policy || {}, null, 2),
    with_scripts: false,
    with_references: false,
    with_assets: false,
    starter_script_enabled: false,
    starter_script_content: defaultStarterScriptContent(),
    starter_reference_enabled: false,
    starter_reference_content: defaultStarterReferenceContent(lang),
    force: false,
  };
}

export function parseRuntimePolicy(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("POLICY_OBJECT_REQUIRED");
  }
  return parsed as Record<string, unknown>;
}

type TranslateFn = (ru: string, en: string) => string;

export function runtimePolicyErrorMessage(error: unknown, tr: TranslateFn) {
  return error instanceof Error && error.message === "POLICY_OBJECT_REQUIRED"
    ? tr("Политика выполнения должна быть JSON-объектом.", "Runtime policy must be a JSON object.")
    : tr("Политика выполнения должна быть валидным JSON.", "Runtime policy must be valid JSON.");
}

export function buildSkillSettingsPayload(draft: SkillSettingsDraft): Partial<StudioSkillDetail> {
  return {
    name: draft.name.trim(),
    description: draft.description.trim(),
    service: draft.service.trim(),
    category: draft.category.trim(),
    safety_level: draft.safety_level || "standard",
    ui_hint: draft.ui_hint.trim(),
    tags: parseCsvInput(draft.tags_text),
    guardrail_summary: parseCsvInput(draft.guardrail_summary_text),
    recommended_tools: parseCsvInput(draft.recommended_tools_text),
    runtime_policy: parseRuntimePolicy(draft.runtime_policy_text),
  };
}

export function buildSkillScaffoldPayload(
  wizard: SkillWizardState,
  selectedTemplateSlug: string,
): StudioSkillScaffoldPayload {
  return {
    template_slug: selectedTemplateSlug !== "__none__" ? selectedTemplateSlug : undefined,
    name: wizard.name.trim(),
    description: wizard.description.trim(),
    slug: wizard.slug.trim() || undefined,
    service: wizard.service.trim() || undefined,
    category: wizard.category.trim() || undefined,
    safety_level: wizard.safety_level,
    ui_hint: wizard.ui_hint.trim() || undefined,
    tags: parseCsvInput(wizard.tags_text),
    guardrail_summary: parseCsvInput(wizard.guardrail_summary_text),
    recommended_tools: parseCsvInput(wizard.recommended_tools_text),
    runtime_policy: parseRuntimePolicy(wizard.runtime_policy_text),
    with_scripts: wizard.with_scripts || wizard.starter_script_enabled,
    with_references: wizard.with_references || wizard.starter_reference_enabled,
    with_assets: wizard.with_assets,
    force: wizard.force,
  };
}

export function starterFilesFromWizard(wizard: SkillWizardState) {
  return [
    wizard.starter_script_enabled
      ? {
          path: DEFAULT_STARTER_SCRIPT_PATH,
          content: wizard.starter_script_content,
        }
      : null,
    wizard.starter_reference_enabled
      ? {
          path: DEFAULT_STARTER_REFERENCE_PATH,
          content: wizard.starter_reference_content,
        }
      : null,
  ].filter(Boolean) as Array<{ path: string; content: string }>;
}

export function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function fileKindLabel(kind: StudioSkillWorkspaceFile["kind"], lang: "ru" | "en") {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  switch (kind) {
    case "skill":
      return "SKILL.md";
    case "reference":
      return tr("справка", "reference");
    case "script":
      return tr("скрипт", "script");
    case "asset":
      return tr("ресурс", "asset");
    default:
      return tr("файл", "file");
  }
}

export function safetyLevelLabel(level: string | undefined, lang: "ru" | "en") {
  if (!level) return "";
  if (lang !== "ru") return level;
  const labels: Record<string, string> = {
    low: "низкий риск",
    standard: "стандартный риск",
    medium: "средний риск",
    high: "высокий риск",
    critical: "критичный риск",
  };
  return labels[level] || level;
}
