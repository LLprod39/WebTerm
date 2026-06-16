import { useEffect, useMemo, useState } from "react";
import { StudioNav } from "@/components/StudioNav";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Bot,
  CheckCircle2,
  FileCode2,
  FolderPlus,
  Loader2,
  Save,
  Search,
  Server,
  Shield,
  Sparkles,
  Trash2,
  WandSparkles,
  BookMarked,
  Code2,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ShareAccessEditor } from "@/components/studio/ShareAccessEditor";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { StudioHero, HeroStatChip, HeroActionButton } from "@/components/studio/StudioHero";
import {
  fetchAuthSession,
  studioSkills,
  studioShareUsers,
  type StudioSkill,
  type StudioSkillDetail,
  type StudioSkillScaffoldPayload,
  type StudioSkillTemplate,
  type StudioSkillValidationResponse,
  type StudioSkillWorkspaceFile,
} from "@/lib/api";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { useI18n } from "@/lib/i18n";

const SAFETY_LEVELS = ["low", "standard", "medium", "high", "critical"] as const;

type SkillWizardState = {
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

type SkillSettingsDraft = {
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
    "echo \"== context ==\"",
    "date -Is",
    "hostname || true",
    "",
    "echo \"== health ==\"",
    "uptime || true",
    "df -h || true",
    "",
    "echo \"== next steps ==\"",
    "echo \"Add preflight checks, exact target discovery, mutation steps, and verification.\"",
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

function parseCsvInput(text: string) {
  return text
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function createSkillSettingsDraft(skill?: StudioSkillDetail | null): SkillSettingsDraft {
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

function slugifySkillName(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 64)
    .replace(/-$/g, "");
}

function createWizardState(template?: StudioSkillTemplate | null, lang: "ru" | "en" = "en"): SkillWizardState {
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

function parseRuntimePolicy(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("POLICY_OBJECT_REQUIRED");
  }
  return parsed as Record<string, unknown>;
}

function starterFilesFromWizard(wizard: SkillWizardState) {
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

async function upsertSkillWorkspaceFile(slug: string, file: { path: string; content: string }) {
  try {
    return await studioSkills.createFile(slug, file);
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.toLowerCase().includes("already exists") || message.includes("409")) {
      return studioSkills.updateFile(slug, file);
    }
    throw error;
  }
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function fileKindLabel(kind: StudioSkillWorkspaceFile["kind"], lang: "ru" | "en") {
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

function safetyLevelLabel(level: string | undefined, lang: "ru" | "en") {
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

function SkillMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        code: ({ className, children }) => {
          const code = String(children).replace(/\n$/, "");
          if ((className || "").includes("language-") || code.includes("\n")) {
            return (
              <code className="block whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-4 font-mono text-[12.5px] leading-6 text-foreground">
                {code}
              </code>
            );
          }
          return <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px] text-foreground">{children}</code>;
        },
        h1: ({ children }) => <h1 className="mt-2 text-xl font-bold tracking-tight text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="mt-6 text-lg font-semibold text-foreground">{children}</h2>,
        h3: ({ children }) => <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-muted-foreground">{children}</h3>,
        p: ({ children }) => <p className="my-2 text-sm leading-7 text-foreground/85">{children}</p>,
        ul: ({ children }) => <ul className="list-disc space-y-1.5 pl-5 text-sm leading-7 text-foreground/85">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal space-y-1.5 pl-5 text-sm leading-7 text-foreground/85">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
        blockquote: ({ children }) => (
          <blockquote className="my-3 border-l-2 border-primary/40 pl-4 text-sm italic text-muted-foreground">{children}</blockquote>
        ),
        hr: () => <hr className="my-5 border-border" />,
        pre: ({ children }) => <pre className="overflow-auto">{children}</pre>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function SkillCard({
  skill,
  isSelected,
  onSelect,
  lang,
}: {
  skill: StudioSkill;
  isSelected: boolean;
  onSelect: () => void;
  lang: "ru" | "en";
}) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`group relative w-full overflow-hidden rounded-xl border p-4 text-left transition-all duration-300 ${
        isSelected
          ? "border-primary/50 bg-primary/5 shadow-md shadow-primary/5 ring-1 ring-primary/20"
          : "border-border/60 bg-background/40 hover:border-border/90 hover:bg-background/60 hover:shadow-lg"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className={`text-[15px] font-semibold ${isSelected ? "text-primary dark:text-primary/90" : "text-foreground"}`}>{skill.name}</p>
            {skill.runtime_enforced && <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-500">{tr("контроль", "enforced")}</span>}
            {skill.is_owner && <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{tr("Мой", "Mine")}</Badge>}
            {!skill.is_owner && skill.owner_username && <Badge variant="outline" className="px-1.5 py-0 text-[10px]">{tr("Владелец", "Owner")}: {skill.owner_username}</Badge>}
            {skill.is_shared && <Badge variant="outline" className="px-1.5 py-0 text-[10px]">{tr("Общий", "Shared")}</Badge>}
            {skill.can_edit === false && <Badge variant="outline" className="px-1.5 py-0 text-[10px] opacity-70">{tr("Только чтение", "Read only")}</Badge>}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] font-medium text-muted-foreground">
            {skill.service && <span className="flex items-center gap-1"><Server className="h-3 w-3" />{skill.service}</span>}
            {skill.category && <span className="opacity-80">· {skill.category}</span>}
          </div>
        </div>
        {skill.safety_level && <Badge variant="outline" className="shrink-0 bg-background/50 px-1.5 py-0 text-[10px] shadow-sm">{safetyLevelLabel(skill.safety_level, lang)}</Badge>}
      </div>
      {skill.description && <p className="mt-3 line-clamp-2 text-[12px] leading-relaxed text-muted-foreground group-hover:text-muted-foreground/90 transition-colors">{skill.description}</p>}
      {skill.guardrail_summary?.length > 0 && (
        <div className="mt-3 flex items-start gap-1.5 text-[11px] leading-snug text-emerald-600/80 dark:text-emerald-400/80">
          <Shield className="mt-0.5 min-w-[12px] h-3 w-3" />
          <p className="line-clamp-1">{skill.guardrail_summary[0]}</p>
        </div>
      )}
      {skill.tags?.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">
        {skill.tags.slice(0, 3).map((t) => (
          <span key={t} className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${isSelected ? "bg-primary/10 text-primary" : "bg-muted/50 text-muted-foreground"}`}>{t}</span>
        ))}
      </div>}
    </button>
  );
}

function ValidationSummaryCard({ report }: { report: StudioSkillValidationResponse }) {
  const { lang } = useI18n();
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const ok = report.summary.is_valid;
  return (
    <Card className="border-border/70 bg-background/24 shadow-none">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-2">
          {ok ? <CheckCircle2 className="h-4 w-4 text-green-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
          <div>
            <p className="text-sm font-medium">{ok ? tr("Библиотека скиллов прошла валидацию", "Skill library passed validation") : tr("Библиотека скиллов требует проверки", "Skill library needs review")}</p>
            <p className="text-[11px] text-muted-foreground">
              {report.summary.skills} {tr("скиллов", "skill(s)")}, {report.summary.errors} {tr("ошибок", "error(s)")}, {report.summary.warnings} {tr("предупреждений", "warning(s)")}
            </p>
          </div>
        </div>
        <Badge variant="outline" className="text-[10px]">
          {report.summary.strict ? tr("строгий режим", "strict mode") : tr("стандартный режим", "standard mode")}
        </Badge>
      </CardContent>
    </Card>
  );
}

export default function StudioSkillsPage() {
  const { lang } = useI18n();
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [search, setSearch] = useState("");
  const [serviceFilter, setServiceFilter] = useState("__all__");
  const [selectedSlug, setSelectedSlug] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [validateOpen, setValidateOpen] = useState(false);
  const [createFileOpen, setCreateFileOpen] = useState(false);
  const [selectedTemplateSlug, setSelectedTemplateSlug] = useState("__none__");
  const [selectedFilePath, setSelectedFilePath] = useState("");
  const [createFilePath, setCreateFilePath] = useState("");
  const [createFileContent, setCreateFileContent] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [wizard, setWizard] = useState<SkillWizardState>(() => createWizardState(null, lang));
  const [slugTouched, setSlugTouched] = useState(false);
  const [validationReport, setValidationReport] = useState<StudioSkillValidationResponse | null>(null);
  const [strictValidation, setStrictValidation] = useState(false);
  const [skillSettingsDraft, setSkillSettingsDraft] = useState<SkillSettingsDraft>(() => createSkillSettingsDraft(null));
  const [skillAccessDraft, setSkillAccessDraft] = useState({
    is_shared: false,
    shared_user_ids: [] as number[],
  });

  const { data: session } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const user = session?.user ?? null;
  const isAdmin = Boolean(user?.is_staff);
  const canOpenAgents = hasFeatureAccess(user, "studio_agents");
  const canOpenMcp = hasFeatureAccess(user, "studio_mcp");

  const { data: skills = [], isLoading } = useQuery({
    queryKey: ["studio", "skills"],
    queryFn: studioSkills.list,
  });

  const { data: shareUsers = [] } = useQuery({
    queryKey: ["studio", "share-users"],
    queryFn: studioShareUsers.list,
    enabled: isAdmin,
  });

  const { data: templates = [] } = useQuery({
    queryKey: ["studio", "skill-templates"],
    queryFn: studioSkills.templates,
  });

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.slug === selectedTemplateSlug) || null,
    [templates, selectedTemplateSlug],
  );

  const services = Array.from(new Set(skills.map((skill) => skill.service).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  const filteredSkills = skills.filter((skill) => {
    const haystack = [skill.name, skill.slug, skill.description, skill.service, skill.category, ...(skill.tags || [])]
      .join(" ")
      .toLowerCase();
    const matchesSearch = !search.trim() || haystack.includes(search.trim().toLowerCase());
    const matchesService = serviceFilter === "__all__" || skill.service === serviceFilter;
    return matchesSearch && matchesService;
  });

  const filteredSignature = filteredSkills.map((skill) => skill.slug).join("|");
  const runtimeEnforcedCount = skills.filter((skill) => skill.runtime_enforced).length;
  const serviceCount = new Set(skills.map((skill) => skill.service).filter(Boolean)).size;
  const starterFiles = starterFilesFromWizard(wizard);
  const canSubmitWizard =
    Boolean(wizard.name.trim()) &&
    Boolean(wizard.description.trim());

  const invalidateSkillQueries = async (slug?: string) => {
    await queryClient.invalidateQueries({ queryKey: ["studio", "skills"] });
    if (!slug) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["studio", "skills", slug] }),
      queryClient.invalidateQueries({ queryKey: ["studio", "skills", "workspace", slug] }),
      queryClient.invalidateQueries({ queryKey: ["studio", "skills", "workspace", "file", slug] }),
    ]);
  };

  const scaffoldMutation = useMutation({
    mutationFn: (payload: StudioSkillScaffoldPayload) => studioSkills.scaffold(payload),
    onSuccess: async (response) => {
      const filesToCreate = starterFilesFromWizard(wizard);
      const fileResults = filesToCreate.length
        ? await Promise.allSettled(filesToCreate.map((file) => upsertSkillWorkspaceFile(response.skill.slug, file)))
        : [];
      const failedFiles = fileResults.filter((result) => result.status === "rejected").length;
      await invalidateSkillQueries(response.skill.slug);
      setSelectedSlug(response.skill.slug);
      setSelectedFilePath(filesToCreate[0]?.path || "SKILL.md");
      setCreateOpen(false);
      const description =
        failedFiles > 0
          ? tr(`Скилл создан, но файлов не создано: ${failedFiles}`, `Skill created, but ${failedFiles} file(s) failed`)
          : filesToCreate.length > 0
            ? tr(`Скилл создан. Добавлено файлов: ${filesToCreate.length}`, `Skill created with ${filesToCreate.length} starter file(s)`)
            : response.validation.warnings.length > 0
              ? tr(`Скилл создан с предупреждениями: ${response.validation.warnings.length}`, `Skill created with ${response.validation.warnings.length} warning(s)`)
              : tr("Скилл создан", "Skill created");
      toast({
        description,
      });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const validateMutation = useMutation({
    mutationFn: () => studioSkills.validate(undefined, strictValidation),
    onSuccess: (response) => {
      setValidationReport(response);
      setValidateOpen(true);
      toast({
        description:
          response.summary.errors > 0
            ? tr(`Валидация нашла ошибок: ${response.summary.errors}`, `Validation found ${response.summary.errors} error(s)`)
            : response.summary.warnings > 0
              ? tr(`Валидация нашла предупреждений: ${response.summary.warnings}`, `Validation found ${response.summary.warnings} warning(s)`)
              : tr("Библиотека скиллов прошла валидацию", "Skill library passed validation"),
      });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  useEffect(() => {
    if (selectedSlug && !filteredSkills.some((skill) => skill.slug === selectedSlug)) {
      setSelectedSlug("");
    }
  }, [filteredSignature, selectedSlug, filteredSkills]);

  const { data: selectedSkill, isFetching: isFetchingSkill } = useQuery({
    queryKey: ["studio", "skills", selectedSlug],
    queryFn: () => studioSkills.get(selectedSlug),
    enabled: !!selectedSlug,
  });

  useEffect(() => {
    if (!selectedSkill) return;
    setSkillSettingsDraft(createSkillSettingsDraft(selectedSkill));
    setSkillAccessDraft({
      is_shared: Boolean(selectedSkill.is_shared),
      shared_user_ids: selectedSkill.shared_user_ids || [],
    });
  }, [selectedSkill]);

  const { data: workspace, isFetching: isFetchingWorkspace } = useQuery({
    queryKey: ["studio", "skills", "workspace", selectedSlug],
    queryFn: () => studioSkills.workspace(selectedSlug),
    enabled: !!selectedSlug,
  });

  const workspaceSignature = (workspace?.files || []).map((file) => file.path).join("|");

  useEffect(() => {
    if (!workspace?.files.length) {
      if (selectedFilePath) setSelectedFilePath("");
      return;
    }
    if (!selectedFilePath || !workspace.files.some((file) => file.path === selectedFilePath)) {
      const preferred = workspace.files.find((file) => file.path === "SKILL.md")?.path || workspace.files[0].path;
      setSelectedFilePath(preferred);
    }
  }, [workspace, workspaceSignature, selectedFilePath]);

  const selectedWorkspaceFile = useMemo(
    () => workspace?.files.find((file) => file.path === selectedFilePath) || null,
    [workspace, selectedFilePath],
  );

  const { data: selectedFileDetail, isFetching: isFetchingFile } = useQuery({
    queryKey: ["studio", "skills", "workspace", "file", selectedSlug, selectedFilePath],
    queryFn: () => studioSkills.readFile(selectedSlug, selectedFilePath),
    enabled: !!selectedSlug && !!selectedFilePath,
  });

  useEffect(() => {
    if (selectedFileDetail) {
      setEditorValue(selectedFileDetail.content);
    }
  }, [selectedFileDetail]);

  const createFileMutation = useMutation({
    mutationFn: (payload: { path: string; content: string }) => {
      if (!selectedSlug) throw new Error(tr("Скилл не выбран", "Skill is not selected"));
      return studioSkills.createFile(selectedSlug, payload);
    },
    onSuccess: async (response, variables) => {
      await invalidateSkillQueries(selectedSlug);
      setCreateFileOpen(false);
      setCreateFilePath("");
      setCreateFileContent("");
      setSelectedFilePath(response.file?.path || variables.path);
      toast({ description: tr("Файл создан", "File created") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const updateFileMutation = useMutation({
    mutationFn: (payload: { path: string; content: string }) => {
      if (!selectedSlug) throw new Error(tr("Скилл не выбран", "Skill is not selected"));
      return studioSkills.updateFile(selectedSlug, payload);
    },
    onSuccess: async () => {
      await invalidateSkillQueries(selectedSlug);
      toast({ description: tr("Файл сохранён", "File saved") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const deleteFileMutation = useMutation({
    mutationFn: (path: string) => {
      if (!selectedSlug) throw new Error(tr("Скилл не выбран", "Skill is not selected"));
      return studioSkills.deleteFile(selectedSlug, path);
    },
    onSuccess: async () => {
      await invalidateSkillQueries(selectedSlug);
      setSelectedFilePath("SKILL.md");
      toast({ description: tr("Файл удалён", "File deleted") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const updateSkillAccessMutation = useMutation({
    mutationFn: () => {
      if (!selectedSkill) throw new Error(tr("Скилл не выбран", "Skill is not selected"));
      return studioSkills.update(selectedSkill.slug, {
        is_shared: skillAccessDraft.is_shared,
        shared_user_ids: skillAccessDraft.shared_user_ids,
      });
    },
    onSuccess: async (response) => {
      await invalidateSkillQueries(response.slug);
      toast({ description: tr("Доступ к скиллу обновлён", "Skill access updated") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const updateSkillSettingsMutation = useMutation({
    mutationFn: (payload: Partial<StudioSkillDetail>) => {
      if (!selectedSkill) throw new Error(tr("Скилл не выбран", "Skill is not selected"));
      return studioSkills.update(selectedSkill.slug, payload);
    },
    onSuccess: async (response) => {
      await invalidateSkillQueries(response.slug);
      toast({ description: tr("Настройки скилла сохранены", "Skill settings saved") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const saveSkillSettings = () => {
    if (!selectedSkill || !canEditSkill) return;
    const name = skillSettingsDraft.name.trim();
    const description = skillSettingsDraft.description.trim();
    if (!name) {
      toast({ variant: "destructive", description: tr("Название скилла обязательно.", "Skill name is required.") });
      return;
    }
    if (!description) {
      toast({ variant: "destructive", description: tr("Описание скилла обязательно.", "Skill description is required.") });
      return;
    }

    let runtimePolicy: Record<string, unknown>;
    try {
      runtimePolicy = parseRuntimePolicy(skillSettingsDraft.runtime_policy_text);
    } catch (error) {
      toast({
        variant: "destructive",
        description:
          error instanceof Error && error.message === "POLICY_OBJECT_REQUIRED"
            ? tr("Политика выполнения должна быть JSON-объектом.", "Runtime policy must be a JSON object.")
            : tr("Политика выполнения должна быть валидным JSON.", "Runtime policy must be valid JSON."),
      });
      return;
    }

    updateSkillSettingsMutation.mutate({
      name,
      description,
      service: skillSettingsDraft.service.trim(),
      category: skillSettingsDraft.category.trim(),
      safety_level: skillSettingsDraft.safety_level || "standard",
      ui_hint: skillSettingsDraft.ui_hint.trim(),
      tags: parseCsvInput(skillSettingsDraft.tags_text),
      guardrail_summary: parseCsvInput(skillSettingsDraft.guardrail_summary_text),
      recommended_tools: parseCsvInput(skillSettingsDraft.recommended_tools_text),
      runtime_policy: runtimePolicy,
    });
  };

  const openCreateDialog = (template?: StudioSkillTemplate | null) => {
    setSelectedTemplateSlug(template?.slug || "__none__");
    setWizard(createWizardState(template || null, lang));
    setSlugTouched(false);
    setCreateOpen(true);
  };

  const submitWizard = () => {
    let runtimePolicy: Record<string, unknown>;
    try {
      runtimePolicy = parseRuntimePolicy(wizard.runtime_policy_text);
    } catch (error) {
      toast({
        variant: "destructive",
        description:
          error instanceof Error && error.message === "POLICY_OBJECT_REQUIRED"
            ? tr("Политика выполнения должна быть JSON-объектом.", "Runtime policy must be a JSON object.")
            : tr("Политика выполнения должна быть валидным JSON.", "Runtime policy must be valid JSON."),
      });
      return;
    }

    const payload: StudioSkillScaffoldPayload = {
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
      runtime_policy: runtimePolicy,
      with_scripts: wizard.with_scripts || wizard.starter_script_enabled,
      with_references: wizard.with_references || wizard.starter_reference_enabled,
      with_assets: wizard.with_assets,
      force: wizard.force,
    };
    scaffoldMutation.mutate(payload);
  };

  const saveCurrentFile = () => {
    if (!selectedFilePath || !canEditSelectedFile) return;
    updateFileMutation.mutate({ path: selectedFilePath, content: editorValue });
  };

  const removeCurrentFile = () => {
    if (!selectedFilePath || selectedFilePath === "SKILL.md" || !canEditSelectedFile) return;
    const confirmed = window.confirm(
      tr(`Удалить файл ${selectedFilePath}? Это действие нельзя отменить.`, `Delete ${selectedFilePath}? This cannot be undone.`),
    );
    if (!confirmed) return;
    deleteFileMutation.mutate(selectedFilePath);
  };

  const isEditorDirty = Boolean(selectedFileDetail && editorValue !== selectedFileDetail.content);
  const workspaceErrors = workspace?.validation.errors || [];
  const workspaceWarnings = workspace?.validation.warnings || [];
  const canEditSkill = Boolean(selectedSkill?.can_edit);
  const canShareSkill = Boolean(selectedSkill?.can_share && isAdmin);
  const canEditSelectedFile = Boolean(selectedWorkspaceFile?.editable && canEditSkill);

  return (
    <div className="flex h-full flex-col">
      <StudioNav />
      {validationReport && (
        <div className="px-6 py-2">
          <ValidationSummaryCard report={validationReport} />
        </div>
      )}

      {!selectedSlug ? (
        <div className="flex-1 overflow-auto flex flex-col">
          <StudioHero
            kicker={tr("Библиотека Studio", "Studio library")}
            title={tr("Каталог скиллов", "Skill Catalog")}
            titleIcon={<BookOpen className="h-7 w-7 text-primary" />}
            description={tr(
              "Скилл здесь это рабочий плейбук. Выберите сервис, проверьте ограничения и политику выполнения, а затем правьте рабочие файлы прямо из Studio.",
              "A skill here is an operating playbook. Pick the service, review guardrails and runtime policy, then edit the workspace directly from Studio.",
            )}
            stats={
              <>
                <HeroStatChip icon={<BookOpen className="h-3.5 w-3.5" />} label={tr(`${skills.length} скиллов`, `${skills.length} skills`)} />
                <HeroStatChip icon={<ShieldCheck className="h-3.5 w-3.5 text-amber-500/80" />} label={tr(`${runtimeEnforcedCount} под контролем`, `${runtimeEnforcedCount} enforced`)} />
                <HeroStatChip icon={<Server className="h-3.5 w-3.5" />} label={tr(`${serviceCount} сервисов`, `${serviceCount} services`)} />
              </>
            }
            actions={
              <>
                {canOpenMcp ? (
                  <HeroActionButton onClick={() => navigate("/studio/mcp")} icon={<Server className="h-4 w-4 text-primary/80" />} label={tr("MCP Реестр", "MCP Registry")} />
                ) : null}
                <Button variant="outline" size="sm" onClick={() => validateMutation.mutate()} className="h-10 gap-2 rounded-full px-4 font-medium shadow-sm border-border/50 hover:bg-background/80">
                  {validateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shield className="h-4 w-4 text-primary/80" />}
                  {tr("Проверить", "Validate")}
                </Button>
                <HeroActionButton onClick={() => openCreateDialog()} icon={<WandSparkles className="h-4 w-4" />} label={tr("Новый скилл", "New Skill")} primary />
                {canOpenAgents ? (
                  <HeroActionButton onClick={() => navigate("/studio/agents")} icon={<Bot className="h-4 w-4 text-primary/80" />} label={tr("Агенты", "Agents")} />
                ) : null}
              </>
            }
          />

          {/* Grid section */}
          <div className="px-6 pb-8 flex-1 flex flex-col gap-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-center justify-between rounded-2xl border border-border/70 bg-background/30 p-2 pl-4 pr-3 backdrop-blur-md">
              <div className="flex items-center gap-4 flex-1">
                <Search className="h-4 w-4 text-muted-foreground shrink-0" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={tr("Поиск скиллов по названию, сервису или тегу...", "Search skills by name, service or tag...")}
                  className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0 text-sm px-0"
                />
              </div>
              <div className="flex w-full flex-wrap items-center gap-3 md:w-auto md:justify-end">
                <Select value={serviceFilter} onValueChange={setServiceFilter}>
                  <SelectTrigger className="h-10 w-full rounded-lg border-border/50 bg-background/50 text-xs sm:w-[180px]">
                    <SelectValue placeholder={tr("Все сервисы", "All services")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">{tr("Все сервисы", "All services")}</SelectItem>
                    {services.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="w-px h-6 bg-border/40 mx-1"></div>
                <span className="text-[11px] font-medium text-muted-foreground whitespace-nowrap bg-muted/40 px-2 py-1 rounded-md">
                  {tr(`${filteredSkills.length} найдено`, `${filteredSkills.length} found`)}
                </span>
                <Button size="sm" variant="outline" className="h-10 gap-1.5 rounded-lg px-3" onClick={() => openCreateDialog()}>
                  <Sparkles className="h-3.5 w-3.5" />
                  {tr("Создать", "Create")}
                </Button>
              </div>
            </div>

            {isLoading ? (
              <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-5 w-5 animate-spin opacity-50" />
                {tr("Загрузка скиллов...", "Loading skills...")}
              </div>
            ) : filteredSkills.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/5 min-h-[300px]">
                <div className="h-12 w-12 rounded-full bg-muted/20 flex items-center justify-center mb-3">
                  <Search className="h-5 w-5 text-muted-foreground/60" />
                </div>
                <p className="text-sm font-medium text-foreground">{tr("Скиллы не найдены", "No skills found")}</p>
                <p className="text-xs text-muted-foreground mt-1">{tr("Попробуйте изменить параметры поиска", "Try changing your search filters")}</p>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
                {filteredSkills.map((skill) => (
                  <SkillCard key={skill.slug} skill={skill} isSelected={false} onSelect={() => setSelectedSlug(skill.slug)} lang={lang} />
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col overflow-hidden bg-muted/10 relative">
          {/* MASTER BACK BAR */}
          <div className="px-6 py-3 flex items-center justify-between gap-4 border-b border-border/40 bg-background/70 backdrop-blur-md sticky top-0 z-20 shrink-0 shadow-sm">
            <div className="flex min-w-0 items-center gap-3">
              <Button variant="ghost" size="sm" onClick={() => setSelectedSlug("")} className="h-10 shrink-0 gap-2 rounded-lg text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-4 w-4" />
                {tr("Каталог", "Catalog")}
              </Button>
              {selectedSkill && (
                <div className="hidden min-w-0 items-center gap-2 md:flex">
                  <span className="text-muted-foreground/50">/</span>
                  <BookOpen className="h-3.5 w-3.5 shrink-0 text-primary/70" />
                  <span className="truncate text-sm font-medium text-foreground">{selectedSkill.name}</span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {selectedSkill?.service && <Badge variant="secondary" className="text-[11px]">{selectedSkill.service}</Badge>}
              {selectedSkill && <Badge variant="outline" className="font-mono text-[11px] bg-background/50">{selectedSkill.slug}</Badge>}
            </div>
          </div>

          {/* WORKSPACE AND TABS AREA */}
          <div className="flex-1 overflow-auto px-6 lg:px-10 py-8 pb-16">
            {isFetchingSkill && !selectedSkill ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                {tr("Загрузка рабочего пространства...", "Loading workspace...")}
              </div>
            ) : selectedSkill ? (
              <Tabs defaultValue="overview" className="flex h-full flex-col w-full space-y-5">
                  <div className="rounded-2xl border border-border/50 bg-background/40 backdrop-blur-md px-6 pt-6 shadow-sm">
                    <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-3">
                          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20 shadow-inner">
                            <BookOpen className="h-5 w-5 text-primary" />
                          </div>
                          <h2 className="text-2xl lg:text-3xl font-bold tracking-tight text-foreground">{selectedSkill.name}</h2>
                          <Badge variant="outline" className="font-mono text-[11px] bg-background/50 backdrop-blur text-muted-foreground ring-1 ring-border/50">{selectedSkill.slug}</Badge>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
                          {selectedSkill.service && <span className="inline-flex items-center gap-1.5 rounded-md bg-muted/40 px-2 py-1"><Server className="h-3 w-3" /> {selectedSkill.service}</span>}
                          {selectedSkill.category && <span className="inline-flex items-center rounded-md bg-muted/40 px-2 py-1">{selectedSkill.category}</span>}
                          {selectedSkill.runtime_enforced && <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-500/10 px-2 py-1 text-amber-600 dark:text-amber-400"><ShieldCheck className="h-3 w-3"/> {tr("контроль выполнения", "runtime enforced")}</span>}
                          {selectedSkill.safety_level && <span className="inline-flex items-center rounded-md bg-muted/40 px-2 py-1">{tr("риск", "safety")}: {safetyLevelLabel(selectedSkill.safety_level, lang)}</span>}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {selectedSkill.is_owner ? <Badge variant="secondary" className="shadow-sm">{tr("Мой скилл", "My skill")}</Badge> : null}
                        {!selectedSkill.is_owner && selectedSkill.owner_username ? <Badge variant="outline" className="shadow-sm">{tr(`Владелец: ${selectedSkill.owner_username}`, `Owner: ${selectedSkill.owner_username}`)}</Badge> : null}
                        {selectedSkill.is_shared ? <Badge variant="outline" className="shadow-sm">{tr("Общий", "Shared")}</Badge> : null}
                        {selectedSkill.can_edit === false ? <Badge variant="outline" className="shadow-sm opacity-70">{tr("Только чтение", "Read only")}</Badge> : null}
                      </div>
                    </div>
                    
                    <div className="mt-6">
                      <TabsList className="flex h-auto w-full justify-start gap-1 overflow-x-auto rounded-none border-b border-border/50 bg-transparent p-0">
                        <TabsTrigger value="overview" className="inline-flex min-h-11 items-center gap-1.5 rounded-none border-b-2 border-transparent px-5 text-sm font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"><BookOpen className="h-4 w-4"/> {tr("Обзор", "Overview")}</TabsTrigger>
                        <TabsTrigger value="playbook" className="inline-flex min-h-11 items-center gap-1.5 rounded-none border-b-2 border-transparent px-5 text-sm font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"><BookMarked className="h-4 w-4"/> {tr("Плейбук", "Playbook")}</TabsTrigger>
                        <TabsTrigger value="workspace" className="inline-flex min-h-11 items-center gap-1.5 rounded-none border-b-2 border-transparent px-5 text-sm font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"><FileCode2 className="h-4 w-4"/> {tr("Файлы", "Workspace")}</TabsTrigger>
                        <TabsTrigger value="settings" className="inline-flex min-h-11 items-center gap-1.5 rounded-none border-b-2 border-transparent px-5 text-sm font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"><Settings2 className="h-4 w-4"/> {tr("Настройки", "Settings")}</TabsTrigger>
                      </TabsList>
                    </div>
                  </div>

                  <TabsContent value="overview" className="m-0 space-y-5 outline-none">
                    <div className="grid gap-5 lg:grid-cols-2">
                       <div className="flex flex-col gap-5">
                         <div className="rounded-2xl border border-border/50 bg-background/40 backdrop-blur-md p-6 shadow-sm">
                           <p className="text-base font-semibold">{tr("Описание", "Description")}</p>
                           {selectedSkill.description ? (
                             <p className="mt-3 text-sm leading-7 text-foreground/85">{selectedSkill.description}</p>
                           ) : (
                             <p className="mt-3 text-sm italic text-muted-foreground">{tr("Нет описания", "No description")}</p>
                           )}
                           
                           {selectedSkill.ui_hint && (
                             <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-foreground/90 flex gap-2.5">
                               <Sparkles className="h-4 w-4 shrink-0 text-primary mt-0.5" />
                               <span>{selectedSkill.ui_hint}</span>
                             </div>
                           )}
                         </div>

                       </div>

                       <div className="flex flex-col gap-5">
                         {selectedSkill.guardrail_summary?.length > 0 && (
                           <div className="rounded-2xl border border-border/50 bg-background/40 backdrop-blur-md p-6 shadow-sm">
                             <div className="flex items-center gap-2">
                               <Shield className="h-4 w-4 text-emerald-500" />
                               <p className="text-base font-semibold">{tr("Ограничения", "Guardrails")}</p>
                             </div>
                             <div className="mt-3 space-y-2 border-l-2 border-emerald-500/30 pl-4">
                               {selectedSkill.guardrail_summary.map((item) => (
                                 <p key={item} className="text-sm leading-6 text-foreground/85">{item}</p>
                               ))}
                             </div>
                           </div>
                         )}

                         {selectedSkill.recommended_tools?.length > 0 && (
                           <div className="rounded-2xl border border-border/50 bg-background/40 backdrop-blur-md p-6 shadow-sm">
                             <p className="text-base font-semibold">{tr("Рекомендуемые инструменты агента", "Recommended agent tools")}</p>
                             <div className="mt-3 flex flex-wrap gap-2">
                               {selectedSkill.recommended_tools.map((toolName) => (
                                 <Badge key={toolName} variant="secondary" className="px-2.5 py-1 text-xs bg-secondary/60 hover:bg-secondary/80 font-mono font-normal">
                                   {toolName}
                                 </Badge>
                               ))}
                             </div>
                           </div>
                         )}

                         {selectedSkill.runtime_enforced && (
                           <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-6 shadow-sm backdrop-blur-md">
                             <div className="flex items-center gap-2">
                               <ShieldCheck className="h-4 w-4 text-amber-500/80" />
                               <p className="text-base font-semibold text-amber-600/90 dark:text-amber-400/90">{tr("Политика выполнения", "Runtime policy")}</p>
                             </div>
                             <pre className="mt-3 overflow-auto whitespace-pre-wrap rounded-lg bg-background/50 border border-amber-500/20 p-4 font-mono text-[12px] leading-6 text-foreground/80 shadow-inner">
                               {JSON.stringify(selectedSkill.runtime_policy, null, 2)}
                             </pre>
                           </div>
                         )}
                       </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="playbook" className="m-0 space-y-4 outline-none">
                    <div className="rounded-2xl border border-border/50 bg-background/40 backdrop-blur-md p-8 shadow-sm">
                      <div className="mb-6 flex items-center gap-3 border-b border-border/50 pb-5">
                        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20 shadow-inner">
                          <BookMarked className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <h3 className="text-lg font-semibold text-foreground">{tr("Плейбук скилла (SKILL.md)", "Skill Playbook (SKILL.md)")}</h3>
                          <p className="text-sm text-muted-foreground">{tr("Ниже полный Markdown документации, который читают агенты.", "Below is the full Markdown the agents read at runtime.")}</p>
                        </div>
                      </div>
                      <div className="mx-auto max-w-4xl">
                        <SkillMarkdown content={selectedSkill.content} />
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="workspace" className="m-0 flex flex-col gap-4 outline-none min-h-[650px] h-[calc(100vh-240px)]">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-4 shadow-sm shrink-0">
                      <div className="flex items-center gap-3">
                         <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
                           <FileCode2 className="h-4 w-4 text-primary" />
                         </div>
                         <div>
                           <h3 className="text-sm font-semibold text-foreground">{tr("Редактор файлов", "Workspace Editor")}</h3>
                           <p className="text-[11px] text-muted-foreground">
                             {tr("Правьте SKILL.md и текстовые файлы в references/, scripts/ и assets/.", "Edit SKILL.md and text files under references/, scripts/, and assets/.")}
                           </p>
                         </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button variant="secondary" size="sm" className="h-9 gap-1.5 rounded-md px-3 text-xs" onClick={() => setCreateFileOpen(true)} disabled={!canEditSkill}>
                          <FolderPlus className="h-3.5 w-3.5" />
                          {tr("Новый файл", "New File")}
                        </Button>
                        <Button size="sm" className="h-9 gap-1.5 rounded-md px-3 text-xs shadow-sm bg-primary hover:bg-primary/90 text-primary-foreground transition-all" onClick={saveCurrentFile} disabled={!selectedFilePath || !isEditorDirty || updateFileMutation.isPending || !canEditSelectedFile}>
                          {updateFileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                          {tr("Сохранить", "Save")}
                        </Button>

                        <div className="w-px h-5 bg-border/80 mx-1"></div>

                        <Button variant="ghost" size="sm" className="h-9 gap-1.5 rounded-md px-3 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive transition-colors" onClick={removeCurrentFile} disabled={!selectedFilePath || selectedFilePath === "SKILL.md" || deleteFileMutation.isPending || !canEditSelectedFile}>
                          {deleteFileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                          {tr("Удалить", "Delete")}
                        </Button>
                      </div>
                    </div>
                    
                    {(workspaceErrors.length > 0 || workspaceWarnings.length > 0) && (
                      <div className="border-b border-border/40 p-4 bg-muted/5 flex flex-col gap-3">
                        {workspaceErrors.length > 0 && (
                          <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
                            <p className="text-xs font-medium text-red-200">{tr("Ошибки пакета", "Package errors")}</p>
                            <div className="mt-2 space-y-1">
                              {workspaceErrors.map((item) => (
                                <p key={item} className="text-[11px] text-red-100">• {item}</p>
                              ))}
                            </div>
                          </div>
                        )}
                        {workspaceWarnings.length > 0 && (
                          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
                            <p className="text-xs font-medium text-amber-100">{tr("Предупреждения пакета", "Package warnings")}</p>
                            <div className="mt-2 space-y-1">
                              {workspaceWarnings.map((item) => (
                                <p key={item} className="text-[11px] text-amber-50">• {item}</p>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    <div className="flex flex-1 overflow-hidden gap-4" style={{ minHeight: "600px" }}>
                      <div className="w-[300px] lg:w-[340px] shrink-0 flex flex-col gap-2 rounded-xl border border-border/40 bg-muted/10 p-4 overflow-y-auto">
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-foreground">{tr("Файлы пакета", "Package Files")}</p>
                            <p className="text-[11px] text-muted-foreground">{tr("SKILL.md, references/, scripts/, assets/", "SKILL.md, references/, scripts/, assets/")}</p>
                          </div>
                          {isFetchingWorkspace ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : null}
                        </div>
                        {!workspace?.files.length ? (
                          <div className="rounded-xl border border-dashed border-border/70 px-3 py-6 text-center text-xs text-muted-foreground">
                            {tr("Файлы ещё не найдены.", "No files found yet.")}
                          </div>
                        ) : (
                          <div className="space-y-2">
                            {workspace.files.map((file) => (
                              <button
                                key={file.path}
                                type="button"
                                onClick={() => setSelectedFilePath(file.path)}
                                className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                                  selectedFilePath === file.path ? "border-primary/50 bg-primary/10 ring-1 ring-primary/20" : "border-border/70 bg-background/40 hover:bg-background/60"
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="truncate text-sm font-medium text-foreground">{file.name}</span>
                                  <span className="shrink-0 text-[11px] text-muted-foreground">{formatFileSize(file.size)}</span>
                                </div>
                                <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{file.path}</div>
                                <div className="mt-2 flex flex-wrap gap-1">
                                  <Badge variant="outline" className="text-[10px]">{fileKindLabel(file.kind, lang)}</Badge>
                                  <Badge variant="secondary" className="text-[10px]">{file.language}</Badge>
                                </div>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="flex-1 flex flex-col rounded-xl border border-border/40 bg-muted/5 overflow-hidden">
                        {!selectedWorkspaceFile ? (
                          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
                            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/30">
                              <FileCode2 className="h-5 w-5 text-muted-foreground/70" />
                            </div>
                            <p className="text-sm font-medium text-foreground">{tr("Выберите файл слева", "Select a file on the left")}</p>
                            <p className="text-xs text-muted-foreground max-w-sm">{tr("Откройте SKILL.md, references/, scripts/ или assets/, чтобы править плейбук прямо здесь.", "Open SKILL.md or any file under references/, scripts/, assets/ to edit the playbook here.")}</p>
                          </div>
                        ) : isFetchingFile && !selectedFileDetail ? (
                          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            {tr("Загрузка файла...", "Loading file...")}
                          </div>
                        ) : (
                          <div className="flex flex-col h-full">
                            <div className="border-b border-border/40 px-5 py-4 bg-background/50 shrink-0">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2">
                                    <FileCode2 className="h-4 w-4 text-primary/70" />
                                    <div className="text-sm font-semibold text-foreground">{selectedWorkspaceFile.name}</div>
                                    {isEditorDirty && <Badge variant="outline" className="text-[10px] border-amber-500/50 text-amber-600 dark:text-amber-400">{tr("не сохранено", "unsaved")}</Badge>}
                                  </div>
                                  <div className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{selectedWorkspaceFile.path}</div>
                                </div>
                                <div className="flex flex-wrap gap-1.5">
                                  <Badge variant="outline" className="text-[10px]">{fileKindLabel(selectedWorkspaceFile.kind, lang)}</Badge>
                                  <Badge variant="secondary" className="text-[10px]">{selectedWorkspaceFile.language}</Badge>
                                  <Badge variant="outline" className="text-[10px]">{formatFileSize(selectedWorkspaceFile.size)}</Badge>
                                </div>
                              </div>
                            </div>
                            
                            <div className="p-4 flex-1 flex flex-col min-h-0 bg-background/20">
                              <Textarea 
                                value={editorValue} 
                                onChange={(event) => setEditorValue(event.target.value)} 
                                className="flex-1 font-mono text-[13px] leading-6 resize-none shadow-inner border-border/50 bg-background/60 focus-visible:ring-1 focus-visible:ring-primary/30" 
                                style={{ tabSize: 2 }}
                                spellCheck={false}
                                readOnly={!canEditSelectedFile} 
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="settings" className="m-0 space-y-5 outline-none">
                    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
                      <div className="space-y-5">
                        <section className="rounded-2xl border border-border/50 bg-background/40 p-6 shadow-sm backdrop-blur-md">
                          <div className="mb-5 flex items-start justify-between gap-3 border-b border-border/50 pb-4">
                            <div className="flex items-center gap-3">
                              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20 shadow-inner">
                                <Settings2 className="h-5 w-5 text-primary" />
                              </div>
                              <div>
                                <h3 className="text-base font-semibold text-foreground">{tr("Основные настройки", "General settings")}</h3>
                                <p className="text-[12px] text-muted-foreground">
                                  {tr("Эти поля сохраняются в описании скилла и видны в каталоге.", "These fields are saved to the skill definition and shown in the catalog.")}
                                </p>
                              </div>
                            </div>
                            {!canEditSkill ? <Badge variant="outline">{tr("Только чтение", "Read only")}</Badge> : null}
                          </div>

                          <div className="grid gap-4 md:grid-cols-2">
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">{tr("Название", "Name")}</Label>
                              <Input
                                value={skillSettingsDraft.name}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, name: event.target.value }))}
                                disabled={!canEditSkill}
                              />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">Slug</Label>
                              <Input value={selectedSkill.slug} disabled className="font-mono text-xs" />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">{tr("Сервис", "Service")}</Label>
                              <Input
                                value={skillSettingsDraft.service}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, service: event.target.value }))}
                                placeholder="docker, gitlab, keycloak"
                                disabled={!canEditSkill}
                              />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">{tr("Категория", "Category")}</Label>
                              <Input
                                value={skillSettingsDraft.category}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, category: event.target.value }))}
                                placeholder="server_ops"
                                disabled={!canEditSkill}
                              />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">{tr("Уровень риска", "Safety level")}</Label>
                              <Select
                                value={skillSettingsDraft.safety_level || "standard"}
                                onValueChange={(value) => setSkillSettingsDraft((prev) => ({ ...prev, safety_level: value }))}
                                disabled={!canEditSkill}
                              >
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {SAFETY_LEVELS.map((level) => (
                                    <SelectItem key={level} value={level}>{safetyLevelLabel(level, lang)}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">{tr("Теги", "Tags")}</Label>
                              <Input
                                value={skillSettingsDraft.tags_text}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, tags_text: event.target.value }))}
                                placeholder="docker, ops, recovery"
                                disabled={!canEditSkill}
                              />
                            </div>
                            <div className="space-y-1.5 md:col-span-2">
                              <Label className="text-xs text-muted-foreground">{tr("Описание", "Description")}</Label>
                              <Textarea
                                rows={4}
                                value={skillSettingsDraft.description}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, description: event.target.value }))}
                                className="resize-none text-sm leading-6"
                                disabled={!canEditSkill}
                              />
                            </div>
                            <div className="space-y-1.5 md:col-span-2">
                              <Label className="text-xs text-muted-foreground">UI hint</Label>
                              <Input
                                value={skillSettingsDraft.ui_hint}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, ui_hint: event.target.value }))}
                                placeholder={tr("Короткая подсказка для операторов", "Short operator-facing hint")}
                                disabled={!canEditSkill}
                              />
                            </div>
                          </div>
                        </section>

                        <section className="rounded-2xl border border-border/50 bg-background/40 p-6 shadow-sm backdrop-blur-md">
                          <div className="mb-5 flex items-center gap-3 border-b border-border/50 pb-4">
                            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20 shadow-inner">
                              <Shield className="h-5 w-5 text-primary" />
                            </div>
                            <div>
                              <h3 className="text-base font-semibold text-foreground">{tr("Политика и инструменты", "Policy and tools")}</h3>
                              <p className="text-[12px] text-muted-foreground">
                                {tr("Ограничения, рекомендуемые инструменты и runtime policy для безопасного запуска.", "Guardrails, recommended tools, and runtime policy for safe execution.")}
                              </p>
                            </div>
                          </div>

                          <div className="grid gap-4 md:grid-cols-2">
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">{tr("Ограничения", "Guardrails")}</Label>
                              <Textarea
                                rows={6}
                                value={skillSettingsDraft.guardrail_summary_text}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, guardrail_summary_text: event.target.value }))}
                                placeholder={tr("По одному правилу на строку", "One rule per line")}
                                className="resize-none text-xs leading-5"
                                disabled={!canEditSkill}
                              />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">{tr("Инструменты агента", "Agent tools")}</Label>
                              <Textarea
                                rows={6}
                                value={skillSettingsDraft.recommended_tools_text}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, recommended_tools_text: event.target.value }))}
                                placeholder="read_console, ssh_execute, report"
                                className="resize-none font-mono text-xs leading-5"
                                disabled={!canEditSkill}
                              />
                            </div>
                            <div className="space-y-1.5 md:col-span-2">
                              <Label className="text-xs text-muted-foreground">Runtime policy JSON</Label>
                              <Textarea
                                rows={9}
                                value={skillSettingsDraft.runtime_policy_text}
                                onChange={(event) => setSkillSettingsDraft((prev) => ({ ...prev, runtime_policy_text: event.target.value }))}
                                className="font-mono text-[11px] leading-5"
                                spellCheck={false}
                                disabled={!canEditSkill}
                              />
                            </div>
                          </div>

                          <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
                            <Button
                              variant="outline"
                              onClick={() => setSkillSettingsDraft(createSkillSettingsDraft(selectedSkill))}
                              disabled={updateSkillSettingsMutation.isPending}
                            >
                              {tr("Сбросить", "Reset")}
                            </Button>
                            <Button
                              className="gap-2"
                              onClick={saveSkillSettings}
                              disabled={!canEditSkill || updateSkillSettingsMutation.isPending}
                            >
                              {updateSkillSettingsMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                              {tr("Сохранить настройки", "Save settings")}
                            </Button>
                          </div>
                        </section>
                      </div>

                      <div className="space-y-5">
                        <section className="rounded-2xl border border-border/50 bg-background/40 p-5 shadow-sm backdrop-blur-md">
                          <div className="flex items-center gap-3">
                            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                              <BookOpen className="h-4 w-4 text-primary" />
                            </div>
                            <div>
                              <h3 className="text-sm font-semibold text-foreground">{tr("Состояние", "Status")}</h3>
                              <p className="text-[11px] text-muted-foreground">{tr("Краткая информация без системных путей.", "Short summary without system paths.")}</p>
                            </div>
                          </div>
                          <div className="mt-4 space-y-2 text-xs text-muted-foreground">
                            <div className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-background/40 px-3 py-2">
                              <span>{tr("Владелец", "Owner")}</span>
                              <span className="text-foreground">{selectedSkill.owner_username || tr("не указан", "not set")}</span>
                            </div>
                            <div className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-background/40 px-3 py-2">
                              <span>{tr("Доступ", "Access")}</span>
                              <span className="text-foreground">{selectedSkill.is_shared ? tr("общий", "shared") : tr("личный", "private")}</span>
                            </div>
                            <div className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-background/40 px-3 py-2">
                              <span>{tr("Файлов", "Files")}</span>
                              <span className="text-foreground">{workspace?.files.length || 0}</span>
                            </div>
                            <div className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-background/40 px-3 py-2">
                              <span>{tr("Валидация", "Validation")}</span>
                              <span className={workspaceErrors.length ? "text-red-400" : workspaceWarnings.length ? "text-amber-300" : "text-emerald-300"}>
                                {workspaceErrors.length
                                  ? tr(`${workspaceErrors.length} ошибок`, `${workspaceErrors.length} errors`)
                                  : workspaceWarnings.length
                                    ? tr(`${workspaceWarnings.length} предупреждений`, `${workspaceWarnings.length} warnings`)
                                    : tr("OK", "OK")}
                              </span>
                            </div>
                          </div>
                        </section>

                        {canShareSkill ? (
                          <section className="space-y-3">
                            <ShareAccessEditor
                              title={tr("Доступ к скиллу", "Skill access")}
                              description={tr("Откройте скилл всем пользователям Studio или только выбранным людям.", "Expose this skill to all Studio users or only selected people.")}
                              isShared={skillAccessDraft.is_shared}
                              sharedUserIds={skillAccessDraft.shared_user_ids}
                              users={shareUsers}
                              disabled={updateSkillAccessMutation.isPending}
                              onSharedChange={(value) => setSkillAccessDraft((prev) => ({ ...prev, is_shared: value }))}
                              onToggleUser={(userId) =>
                                setSkillAccessDraft((prev) => ({
                                  ...prev,
                                  shared_user_ids: prev.shared_user_ids.includes(userId)
                                    ? prev.shared_user_ids.filter((id) => id !== userId)
                                    : [...prev.shared_user_ids, userId],
                                }))
                              }
                            />
                            <Button
                              className="w-full gap-2"
                              onClick={() => updateSkillAccessMutation.mutate()}
                              disabled={updateSkillAccessMutation.isPending}
                            >
                              {updateSkillAccessMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                              {tr("Сохранить доступ", "Save access")}
                            </Button>
                          </section>
                        ) : (
                          <section className="rounded-2xl border border-border/50 bg-background/40 p-5 shadow-sm backdrop-blur-md">
                            <h3 className="text-sm font-semibold text-foreground">{tr("Доступ", "Access")}</h3>
                            <p className="mt-2 text-xs leading-5 text-muted-foreground">
                              {tr("Управлять доступом может только администратор.", "Only an administrator can manage sharing.")}
                            </p>
                          </section>
                        )}
                      </div>
                    </div>
                  </TabsContent>
                </Tabs>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-red-500/80">
                {tr("Ошибка загрузки скилла.", "Error loading skill.")}
              </div>
            )}
          </div>
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent closeLabel={tr("Закрыть", "Close")} className="grid max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-3xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-xl border-border bg-background p-0 shadow-2xl">
          <div className="border-b border-border/50 bg-card/70 px-5 py-5 sm:px-6">
            <DialogHeader className="border-0 p-0">
              <DialogTitle className="flex items-center gap-3 text-xl font-semibold">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
                  <WandSparkles className="h-4 w-4 text-primary" />
                </span>
                {tr("Создать скилл", "Create skill")}
              </DialogTitle>
              <DialogDescription className="mt-2 max-w-2xl text-[13px] leading-5">
                {tr("Заполните только то, что агенту нужно понять: как называется скилл и когда его применять. Инструкции и скрипты можно добавить сейчас или позже во вкладке файлов.", "Fill only what the agent needs to understand: the skill name and when to use it. Instructions and scripts can be added now or later in the file workspace.")}
              </DialogDescription>
            </DialogHeader>
          </div>

          <div className="min-h-0 overflow-y-auto px-5 py-5 sm:px-6">
            <div className="space-y-5">
              <section className="space-y-4">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">1</span>
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">{tr("Назначение", "Purpose")}</h3>
                    <p className="mt-0.5 text-xs text-muted-foreground">{tr("Это попадёт в SKILL.md и поможет агенту выбрать скилл в нужный момент.", "This goes into SKILL.md and helps the agent choose the skill at the right time.")}</p>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Шаблон", "Template")}</Label>
                  <Select
                    value={selectedTemplateSlug}
                    onValueChange={(value) => {
                      setSelectedTemplateSlug(value);
                      const template = templates.find((item) => item.slug === value) || null;
                      setWizard(createWizardState(template, lang));
                      setSlugTouched(false);
                    }}
                  >
                    <SelectTrigger className="h-10">
                      <SelectValue placeholder={tr("С чистого листа", "Blank slate")} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">{tr("С чистого листа", "Blank slate")}</SelectItem>
                      {templates.map((template) => (
                        <SelectItem key={template.slug} value={template.slug}>{template.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {selectedTemplate?.summary ? <p className="text-[11px] leading-4 text-muted-foreground">{selectedTemplate.summary}</p> : null}
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Название скилла", "Skill name")}</Label>
                  <Input
                    className="h-10"
                    value={wizard.name}
                    onChange={(e) => {
                      const value = e.target.value;
                      setWizard((prev) => ({ ...prev, name: value, slug: slugTouched ? prev.slug : slugifySkillName(value) }));
                    }}
                    placeholder={tr("Например: Docker health-check", "Example: Docker health-check")}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Когда применять этот скилл", "When to use this skill")}</Label>
                  <Textarea
                    rows={4}
                    className="resize-none text-sm leading-6"
                    value={wizard.description}
                    onChange={(e) => setWizard((prev) => ({ ...prev, description: e.target.value }))}
                    placeholder={tr("Опишите обычным языком: для каких задач, на каких серверах/сервисах и какой результат должен получить агент.", "Describe in plain language: tasks, target servers/services, and the result the agent should produce.")}
                  />
                </div>
              </section>

              <section className="space-y-3">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">2</span>
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">{tr("Материалы к скиллу", "Skill materials")}</h3>
                    <p className="mt-0.5 text-xs text-muted-foreground">{tr("Необязательно. Добавьте инструкцию или готовый скрипт, если они уже есть.", "Optional. Attach a runbook or ready automation script if you already have them.")}</p>
                  </div>
                </div>

                <div className={`rounded-lg border p-4 transition-colors ${wizard.starter_reference_enabled ? "border-primary/30 bg-primary/5" : "border-border/70 bg-card/35"}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 flex-1 gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background/70 text-primary ring-1 ring-border/60">
                        <BookMarked className="h-4 w-4" />
                      </span>
                      <div>
                        <div className="text-sm font-semibold text-foreground">{tr("Рабочая инструкция", "Working runbook")}</div>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">{tr("Markdown-файл с правилами, примерами, входными данными и порядком действий.", "Markdown file with rules, examples, inputs, and workflow steps.")}</p>
                      </div>
                    </div>
                    <div className="ml-auto flex shrink-0 items-center gap-2">
                      <Label htmlFor="starter-reference" className="text-xs text-muted-foreground">{wizard.starter_reference_enabled ? tr("Добавлена", "Added") : tr("Добавить", "Add")}</Label>
                      <Switch
                        id="starter-reference"
                        checked={wizard.starter_reference_enabled}
                        onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, starter_reference_enabled: Boolean(checked), with_references: checked ? true : prev.with_references }))}
                      />
                    </div>
                  </div>
                  {wizard.starter_reference_enabled ? (
                    <div className="mt-4 space-y-2">
                      <Label className="text-[11px] text-muted-foreground">{tr("Текст инструкции", "Runbook content")}</Label>
                      <Textarea
                        rows={7}
                        className="font-mono text-[11px] leading-5"
                        value={wizard.starter_reference_content}
                        onChange={(e) => setWizard((prev) => ({ ...prev, starter_reference_content: e.target.value }))}
                        spellCheck={false}
                      />
                    </div>
                  ) : null}
                </div>

                <div className={`rounded-lg border p-4 transition-colors ${wizard.starter_script_enabled ? "border-primary/30 bg-primary/5" : "border-border/70 bg-card/35"}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 flex-1 gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background/70 text-primary ring-1 ring-border/60">
                        <Code2 className="h-4 w-4" />
                      </span>
                      <div>
                        <div className="text-sm font-semibold text-foreground">{tr("Скрипт автоматизации", "Automation script")}</div>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">{tr("Готовый shell/Python/JS-скрипт, который агент сможет открыть, проверить и использовать.", "A ready shell/Python/JS script the agent can open, inspect, and use.")}</p>
                      </div>
                    </div>
                    <div className="ml-auto flex shrink-0 items-center gap-2">
                      <Label htmlFor="starter-script" className="text-xs text-muted-foreground">{wizard.starter_script_enabled ? tr("Добавлен", "Added") : tr("Добавить", "Add")}</Label>
                      <Switch
                        id="starter-script"
                        checked={wizard.starter_script_enabled}
                        onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, starter_script_enabled: Boolean(checked), with_scripts: checked ? true : prev.with_scripts }))}
                      />
                    </div>
                  </div>
                  {wizard.starter_script_enabled ? (
                    <div className="mt-4 space-y-2">
                      <Label className="text-[11px] text-muted-foreground">{tr("Текст скрипта", "Script content")}</Label>
                      <Textarea
                        rows={7}
                        className="font-mono text-[11px] leading-5"
                        value={wizard.starter_script_content}
                        onChange={(e) => setWizard((prev) => ({ ...prev, starter_script_content: e.target.value }))}
                        spellCheck={false}
                      />
                    </div>
                  ) : null}
                </div>
              </section>

              <Accordion type="single" collapsible className="rounded-lg border border-border/70 bg-background/35 px-3">
                <AccordionItem value="advanced" className="border-0">
                  <AccordionTrigger className="py-4 text-sm font-semibold hover:no-underline">{tr("Дополнительно", "Advanced")}</AccordionTrigger>
                  <AccordionContent className="space-y-4 pb-4">
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Slug</Label>
                        <Input
                          className="h-9 font-mono text-xs"
                          value={wizard.slug}
                          onChange={(e) => {
                            setSlugTouched(true);
                            setWizard((prev) => ({ ...prev, slug: e.target.value }));
                          }}
                          placeholder="docker-health-check"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{tr("Уровень риска", "Safety level")}</Label>
                        <Select value={wizard.safety_level} onValueChange={(value) => setWizard((prev) => ({ ...prev, safety_level: value }))}>
                          <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {SAFETY_LEVELS.map((level) => (<SelectItem key={level} value={level}>{safetyLevelLabel(level, lang)}</SelectItem>))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    <div className="grid gap-4 md:grid-cols-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{tr("Сервис", "Service")}</Label>
                        <Input className="h-9" value={wizard.service} onChange={(e) => setWizard((prev) => ({ ...prev, service: e.target.value }))} placeholder="docker, github" />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{tr("Категория", "Category")}</Label>
                        <Input className="h-9" value={wizard.category} onChange={(e) => setWizard((prev) => ({ ...prev, category: e.target.value }))} placeholder="Ops, IAM" />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{tr("Теги", "Tags")}</Label>
                        <Input className="h-9" value={wizard.tags_text} onChange={(e) => setWizard((prev) => ({ ...prev, tags_text: e.target.value }))} placeholder="docker, health" />
                      </div>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{tr("Краткие ограничения", "Guardrail summary")}</Label>
                        <Textarea rows={3} className="text-xs leading-5" value={wizard.guardrail_summary_text} onChange={(e) => setWizard((prev) => ({ ...prev, guardrail_summary_text: e.target.value }))} placeholder={tr("Например: только read-only проверки без подтверждения.", "Example: read-only checks only without confirmation.")} />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{tr("Рекомендуемые инструменты", "Recommended tools")}</Label>
                        <Textarea rows={3} className="text-xs leading-5" value={wizard.recommended_tools_text} onChange={(e) => setWizard((prev) => ({ ...prev, recommended_tools_text: e.target.value }))} placeholder="report, ask_user, analyze_output" />
                      </div>
                    </div>

                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-card/35 px-3 py-2">
                        <div>
                          <span className="text-xs font-medium text-foreground">{tr("Создать папку assets/", "Create assets/ folder")}</span>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">{tr("Для CSV, шаблонов и примеров данных.", "For CSV, templates, and sample data.")}</p>
                        </div>
                        <Switch checked={wizard.with_assets} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_assets: Boolean(checked) }))} />
                      </div>
                      <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
                        <div>
                          <span className="text-xs font-medium text-destructive">{tr("Перезаписать существующий slug", "Overwrite existing slug")}</span>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">{tr("Только если обновляете свой скилл.", "Only when updating your own skill.")}</p>
                        </div>
                        <Switch checked={wizard.force} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, force: Boolean(checked) }))} />
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Политика выполнения JSON", "Runtime policy JSON")}</Label>
                      <Textarea rows={6} value={wizard.runtime_policy_text} onChange={(e) => setWizard((prev) => ({ ...prev, runtime_policy_text: e.target.value }))} className="font-mono text-[11px] leading-5" spellCheck={false} />
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </div>

          <div className="flex flex-col gap-3 border-t border-border/50 bg-card/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p className="text-xs leading-5 text-muted-foreground">
              {canSubmitWizard
                ? tr(`Будет создан SKILL.md${starterFiles.length ? ` и файлов: ${starterFiles.length}` : ""}.`, `Will create SKILL.md${starterFiles.length ? ` and ${starterFiles.length} file(s)` : ""}.`)
                : tr("Для создания заполните название и когда применять скилл.", "Add a name and when to use the skill to continue.")}
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" className="text-muted-foreground" onClick={() => setCreateOpen(false)}>{tr("Отмена", "Cancel")}</Button>
              <Button onClick={submitWizard} disabled={!canSubmitWizard || scaffoldMutation.isPending} className="h-10 gap-2 px-5">
                {scaffoldMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <WandSparkles className="h-4 w-4" />}
                {tr("Создать", "Create")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={createFileOpen} onOpenChange={setCreateFileOpen}>
        <DialogContent closeLabel={tr("Закрыть", "Close")} className="grid max-h-[calc(100dvh-2rem)] max-w-3xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-md border-border bg-background/95">
          <DialogHeader>
            <DialogTitle>{tr("Новый файл рабочей папки", "New workspace file")}</DialogTitle>
            <DialogDescription>{tr("Создайте текстовый файл внутри references/, scripts/ или assets/. Для нового материала плейбука обычно начинайте с references/guide.md.", "Create a text file inside references/, scripts/, or assets/. For new playbook material, start with references/guide.md.")}</DialogDescription>
          </DialogHeader>
          <div className="min-h-0 space-y-4 overflow-y-auto py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">{tr("Путь", "Path")}</Label>
              <Input value={createFilePath} onChange={(event) => setCreateFilePath(event.target.value)} placeholder="references/guide.md" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{tr("Содержимое", "Content")}</Label>
              <Textarea rows={16} value={createFileContent} onChange={(event) => setCreateFileContent(event.target.value)} className="font-mono text-[12px] leading-5" />
            </div>
            <div className="rounded-xl border border-border/70 bg-background/24 px-4 py-4 text-[11px] leading-5 text-muted-foreground">
              {tr("Разрешены только относительные пути и текстовые расширения. Абсолютные пути, скрытые файлы и выход за пределы папки скилла backend отклоняет.", "Only relative paths and text extensions are allowed. Absolute paths, hidden files, and escaping the skill directory are rejected by the backend.")}
            </div>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCreateFileOpen(false)}>{tr("Отмена", "Cancel")}</Button>
            <Button onClick={() => createFileMutation.mutate({ path: createFilePath.trim(), content: createFileContent })} disabled={!createFilePath.trim() || createFileMutation.isPending || !canEditSkill} className="gap-1.5">
              {createFileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderPlus className="h-3.5 w-3.5" />}
              {tr("Создать файл", "Create file")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={validateOpen} onOpenChange={setValidateOpen}>
        <DialogContent closeLabel={tr("Закрыть", "Close")} className="max-h-[85vh] max-w-4xl overflow-auto rounded-md border-border bg-background/95">
          <DialogHeader>
            <DialogTitle>{tr("Валидация библиотеки скиллов", "Skill Library Validation")}</DialogTitle>
            <DialogDescription>{tr("Проверьте структурные и policy-проблемы в текущей библиотеке скиллов Studio.", "Review structural and policy issues across the current Studio skill library.")}</DialogDescription>
          </DialogHeader>

          <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/20 p-4">
            <div>
              <p className="text-sm font-medium">{tr("Режим валидации", "Validation mode")}</p>
              <p className="text-[11px] text-muted-foreground">{tr("В строгом режиме предупреждения считаются блокерами деплоя.", "Strict mode treats warnings as deployment blockers.")}</p>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs">{tr("Строгий", "Strict")}</Label>
              <Switch checked={strictValidation} onCheckedChange={(checked) => setStrictValidation(Boolean(checked))} />
              <Button variant="outline" size="sm" onClick={() => validateMutation.mutate()} className="gap-1.5">
                {validateMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Shield className="h-3 w-3" />}
                {tr("Повторить", "Re-run")}
              </Button>
            </div>
          </div>

          {validationReport ? (
            <div className="space-y-3">
              <ValidationSummaryCard report={validationReport} />
              {validationReport.results.map((result) => (
                <Card key={result.slug} className={result.errors.length ? "border-red-500/30" : result.warnings.length ? "border-amber-500/30" : "border-green-500/20"}>
                  <CardHeader className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle className="text-sm">{result.slug}</CardTitle>
                      {result.errors.length === 0 && result.warnings.length === 0 && <Badge variant="secondary" className="text-[10px]">ok</Badge>}
                      {result.errors.length > 0 && <Badge variant="destructive" className="text-[10px]">{result.errors.length} {tr("ошибок", "errors")}</Badge>}
                      {result.warnings.length > 0 && <Badge variant="outline" className="text-[10px]">{result.warnings.length} {tr("предупреждений", "warnings")}</Badge>}
                    </div>
                    <p className="text-[11px] text-muted-foreground">{result.path}</p>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {result.errors.length > 0 && (
                      <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
                        <p className="text-xs font-medium text-red-200">{tr("Ошибки", "Errors")}</p>
                        <div className="mt-1 space-y-1">
                          {result.errors.map((item) => (
                            <p key={item} className="text-[11px] text-red-100">• {item}</p>
                          ))}
                        </div>
                      </div>
                    )}
                    {result.warnings.length > 0 && (
                      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                        <p className="text-xs font-medium text-amber-100">{tr("Предупреждения", "Warnings")}</p>
                        <div className="mt-1 space-y-1">
                          {result.warnings.map((item) => (
                            <p key={item} className="text-[11px] text-amber-50">• {item}</p>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              {tr("Валидация ещё не запускалась.", "Validation has not been run yet.")}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
