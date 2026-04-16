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
  Copy,
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
  force: boolean;
};

function listToCsv(items?: string[]) {
  return (items || []).join(", ");
}

function parseCsvInput(text: string) {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
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

function createWizardState(template?: StudioSkillTemplate | null): SkillWizardState {
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
    with_references: true,
    with_assets: false,
    force: false,
  };
}

function parseRuntimePolicy(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Runtime policy must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
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
      return tr("reference", "reference");
    case "script":
      return tr("script", "script");
    case "asset":
      return tr("asset", "asset");
    default:
      return tr("file", "file");
  }
}

function SkillMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        code: ({ className, children }) => {
          const code = String(children).replace(/\n$/, "");
          if ((className || "").includes("language-") || code.includes("\n")) {
            return (
              <code className="block whitespace-pre-wrap rounded-lg border border-border bg-muted/20 p-3 font-mono text-[11px] leading-5 text-foreground">
                {code}
              </code>
            );
          }
          return <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px] text-foreground">{children}</code>;
        },
        h1: ({ children }) => <h1 className="text-base font-semibold text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="mt-4 text-sm font-semibold text-foreground">{children}</h2>,
        h3: ({ children }) => <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</h3>,
        p: ({ children }) => <p className="text-xs leading-6 text-muted-foreground">{children}</p>,
        ul: ({ children }) => <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal space-y-1 pl-4 text-xs text-muted-foreground">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-primary/40 pl-3 text-xs italic text-muted-foreground">{children}</blockquote>
        ),
        hr: () => <hr className="my-3 border-border" />,
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
            {skill.runtime_enforced && <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-500">{tr("enforced", "enforced")}</span>}
            {skill.is_owner && <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">Mine</Badge>}
            {!skill.is_owner && skill.owner_username && <Badge variant="outline" className="px-1.5 py-0 text-[10px]">Owner: {skill.owner_username}</Badge>}
            {skill.is_shared && <Badge variant="outline" className="px-1.5 py-0 text-[10px]">Shared</Badge>}
            {skill.can_edit === false && <Badge variant="outline" className="px-1.5 py-0 text-[10px] opacity-70">Read only</Badge>}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] font-medium text-muted-foreground">
            {skill.service && <span className="flex items-center gap-1"><Server className="h-3 w-3" />{skill.service}</span>}
            {skill.category && <span className="opacity-80">· {skill.category}</span>}
          </div>
        </div>
        {skill.safety_level && <Badge variant="outline" className="shrink-0 bg-background/50 px-1.5 py-0 text-[10px] shadow-sm">{skill.safety_level}</Badge>}
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
  const [launcherTemplateSlug, setLauncherTemplateSlug] = useState("__none__");
  const [createOpen, setCreateOpen] = useState(false);
  const [validateOpen, setValidateOpen] = useState(false);
  const [createFileOpen, setCreateFileOpen] = useState(false);
  const [selectedTemplateSlug, setSelectedTemplateSlug] = useState("__none__");
  const [selectedFilePath, setSelectedFilePath] = useState("");
  const [createFilePath, setCreateFilePath] = useState("");
  const [createFileContent, setCreateFileContent] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [wizard, setWizard] = useState<SkillWizardState>(() => createWizardState(null));
  const [wizardSection, setWizardSection] = useState<"basics" | "policy" | "files">("basics");
  const [slugTouched, setSlugTouched] = useState(false);
  const [validationReport, setValidationReport] = useState<StudioSkillValidationResponse | null>(null);
  const [strictValidation, setStrictValidation] = useState(false);
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

  const launcherTemplate = useMemo(
    () => templates.find((item) => item.slug === launcherTemplateSlug) || null,
    [templates, launcherTemplateSlug],
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
      await invalidateSkillQueries(response.skill.slug);
      setSelectedSlug(response.skill.slug);
      setCreateOpen(false);
      toast({
        description:
          response.validation.warnings.length > 0
            ? tr(`Скилл создан с предупреждениями: ${response.validation.warnings.length}`, `Skill created with ${response.validation.warnings.length} warning(s)`)
            : tr("Скилл создан", "Skill created"),
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
      if (!selectedSlug) throw new Error("Skill is not selected");
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
      if (!selectedSlug) throw new Error("Skill is not selected");
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
      if (!selectedSlug) throw new Error("Skill is not selected");
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
      if (!selectedSkill) throw new Error("Skill is not selected");
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

  const openCreateDialog = (template?: StudioSkillTemplate | null) => {
    setSelectedTemplateSlug(template?.slug || "__none__");
    setWizard(createWizardState(template || null));
    setWizardSection("basics");
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
        description: error instanceof Error ? error.message : tr("Runtime policy должен быть валидным JSON-объектом", "Runtime policy must be valid JSON"),
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
      with_scripts: wizard.with_scripts,
      with_references: wizard.with_references,
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
            kicker={tr("Studio library", "Studio library")}
            title={tr("Каталог скиллов", "Skill Catalog")}
            titleIcon={<BookOpen className="h-7 w-7 text-primary" />}
            description={tr(
              "Скилл здесь это рабочий плейбук. Выберите сервис, проверьте guardrails и runtime policy, а затем правьте сам workspace прямо из Studio.",
              "A skill here is an operating playbook. Pick the service, review guardrails and runtime policy, then edit the workspace directly from Studio.",
            )}
            stats={
              <>
                <HeroStatChip icon={<BookOpen className="h-3.5 w-3.5" />} label={tr(`${skills.length} скиллов`, `${skills.length} skills`)} />
                <HeroStatChip icon={<ShieldCheck className="h-3.5 w-3.5 text-amber-500/80" />} label={tr(`${runtimeEnforcedCount} enforced`, `${runtimeEnforcedCount} enforced`)} />
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
              <div className="flex items-center gap-3 shrink-0">
                <Select value={serviceFilter} onValueChange={setServiceFilter}>
                  <SelectTrigger className="h-9 w-[180px] text-xs bg-background/50 border-border/50 rounded-lg">
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
                <Button size="sm" variant="outline" className="h-9 gap-1.5 rounded-lg px-3" onClick={() => openCreateDialog()}>
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
          <div className="px-6 py-3 flex items-center justify-between border-b border-border/40 bg-background/60 backdrop-blur-md sticky top-0 z-20 shrink-0 shadow-sm">
            <Button variant="ghost" size="sm" onClick={() => setSelectedSlug("")} className="h-8 gap-2 rounded-lg text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-4 w-4" />
              {tr("Назад в каталог", "Back to catalog")}
            </Button>
            
            <div className="flex items-center gap-2">
              {selectedSkill && <Badge variant="outline" className="font-mono text-[10px] bg-background/50">{selectedSkill.slug}</Badge>}
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
              <Tabs defaultValue="overview" className="flex h-full flex-col w-full max-w-7xl mx-auto space-y-4">
                  <div className="rounded-xl border border-border/50 bg-background/40 backdrop-blur-md px-5 pt-5 shadow-sm">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <h2 className="text-xl font-bold tracking-tight text-foreground">{selectedSkill.name}</h2>
                          <Badge variant="outline" className="font-mono text-[10px] bg-background/50 backdrop-blur text-muted-foreground ring-1 ring-border/50">{selectedSkill.slug}</Badge>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                          {selectedSkill.service && <span className="flex items-center gap-1"><Server className="h-3 w-3" /> {selectedSkill.service}</span>}
                          {selectedSkill.category && <span>· {selectedSkill.category}</span>}
                          {selectedSkill.runtime_enforced && <span className="flex items-center gap-1 text-amber-500/80">· <ShieldCheck className="h-3 w-3"/> {tr("runtime enforced", "runtime enforced")}</span>}
                          {selectedSkill.safety_level && <span>· {selectedSkill.safety_level}</span>}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {selectedSkill.is_owner ? <Badge variant="secondary" className="shadow-sm">{tr("Мой скилл", "My skill")}</Badge> : null}
                        {!selectedSkill.is_owner && selectedSkill.owner_username ? <Badge variant="outline" className="shadow-sm">{tr(`Владелец: ${selectedSkill.owner_username}`, `Owner: ${selectedSkill.owner_username}`)}</Badge> : null}
                        {selectedSkill.is_shared ? <Badge variant="outline" className="shadow-sm">{tr("Shared", "Shared")}</Badge> : null}
                        {selectedSkill.can_edit === false ? <Badge variant="outline" className="shadow-sm opacity-70">{tr("Только чтение", "Read only")}</Badge> : null}
                      </div>
                    </div>
                    
                    <div className="mt-5">
                      <TabsList className="bg-transparent h-auto p-0 border-b border-border/50 w-full flex justify-start rounded-none">
                        <TabsTrigger value="overview" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 pb-3 pt-2 font-medium text-muted-foreground data-[state=active]:text-foreground">Основа / Overview</TabsTrigger>
                        <TabsTrigger value="playbook" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 pb-3 pt-2 font-medium text-muted-foreground data-[state=active]:text-foreground">Плейбук / Playbook</TabsTrigger>
                        <TabsTrigger value="workspace" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 pb-3 pt-2 font-medium flex items-center gap-1.5 text-muted-foreground data-[state=active]:text-foreground"><FileCode2 className="h-3.5 w-3.5"/> Workspace</TabsTrigger>
                        <TabsTrigger value="settings" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 pb-3 pt-2 font-medium flex items-center gap-1.5 text-muted-foreground data-[state=active]:text-foreground"><Settings2 className="h-3.5 w-3.5"/> Настройки</TabsTrigger>
                      </TabsList>
                    </div>
                  </div>

                  <TabsContent value="overview" className="m-0 space-y-4 outline-none">
                    <div className="grid gap-4 lg:grid-cols-2">
                       <div className="flex flex-col gap-4">
                         <div className="rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-5 shadow-sm">
                           <p className="text-sm font-semibold">{tr("Описание", "Description")}</p>
                           {selectedSkill.description ? (
                             <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{selectedSkill.description}</p>
                           ) : (
                             <p className="mt-2 text-[12px] italic text-muted-foreground">{tr("Нет описания", "No description")}</p>
                           )}
                           
                           {selectedSkill.ui_hint && (
                             <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-[12px] text-foreground/90 flex gap-2">
                               <Sparkles className="h-4 w-4 shrink-0 text-primary mt-0.5" />
                               <span>{selectedSkill.ui_hint}</span>
                             </div>
                           )}
                         </div>

                         <div className="rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-5 shadow-sm">
                           <p className="text-sm font-semibold">{tr("Путь в системе", "System Path")}</p>
                           <div className="mt-3 flex items-center gap-2 rounded-lg border border-border/60 bg-background/40 p-2 pl-3">
                             <div className="flex-1 break-all font-mono text-[11px] text-foreground">{selectedSkill.path}</div>
                             <Button variant="ghost" size="icon" className="h-7 w-7 rounded-md shrink-0 focus:outline-none focus:ring-2 focus:ring-primary/20 hover:bg-background/80" onClick={() => {
                               navigator.clipboard.writeText(selectedSkill.path);
                               toast({description: tr("Путь скопирован", "Path copied")});
                             }}>
                               <Copy className="h-3.5 w-3.5 text-muted-foreground" />
                             </Button>
                           </div>
                         </div>
                       </div>

                       <div className="flex flex-col gap-4">
                         {selectedSkill.guardrail_summary?.length > 0 && (
                           <div className="rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-5 shadow-sm">
                             <div className="flex items-center gap-2">
                               <Shield className="h-4 w-4 text-emerald-500" />
                               <p className="text-sm font-semibold">{tr("Guardrails", "Guardrails")}</p>
                             </div>
                             <div className="mt-3 space-y-1.5 border-l-2 border-emerald-500/30 pl-3">
                               {selectedSkill.guardrail_summary.map((item) => (
                                 <p key={item} className="text-[12px] leading-relaxed text-muted-foreground">{item}</p>
                               ))}
                             </div>
                           </div>
                         )}

                         {selectedSkill.recommended_tools?.length > 0 && (
                           <div className="rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-5 shadow-sm">
                             <p className="text-sm font-semibold">{tr("Рекомендуемые инструменты агента", "Recommended agent tools")}</p>
                             <div className="mt-3 flex flex-wrap gap-2">
                               {selectedSkill.recommended_tools.map((toolName) => (
                                 <Badge key={toolName} variant="secondary" className="px-2.5 py-0.5 text-[11px] bg-secondary/60 hover:bg-secondary/80 font-mono font-normal">
                                   {toolName}
                                 </Badge>
                               ))}
                             </div>
                           </div>
                         )}

                         {selectedSkill.runtime_enforced && (
                           <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 shadow-sm backdrop-blur-md">
                             <div className="flex items-center gap-2">
                               <ShieldCheck className="h-4 w-4 text-amber-500/80" />
                               <p className="text-sm font-semibold text-amber-600/90 dark:text-amber-400/90">{tr("Runtime policy", "Runtime policy")}</p>
                             </div>
                             <pre className="mt-3 overflow-auto whitespace-pre-wrap rounded-lg bg-background/50 border border-amber-500/20 p-4 font-mono text-[11px] leading-5 text-muted-foreground shadow-inner">
                               {JSON.stringify(selectedSkill.runtime_policy, null, 2)}
                             </pre>
                           </div>
                         )}
                       </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="playbook" className="m-0 space-y-4 outline-none">
                    <div className="rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-6 shadow-sm">
                      <div className="mb-6 flex items-center gap-3 border-b border-border/50 pb-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20 shadow-inner">
                          <BookMarked className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <h3 className="text-base font-semibold text-foreground">{tr("Плейбук скилла (SKILL.md)", "Skill Playbook (SKILL.md)")}</h3>
                          <p className="text-[12px] text-muted-foreground">{tr("Ниже полный Markdown документации, который читают агенты.", "Below is the full Markdown the agents read at runtime.")}</p>
                        </div>
                      </div>
                      <div className="prose prose-sm dark:prose-invert max-w-none text-muted-foreground">
                        <SkillMarkdown content={selectedSkill.content} />
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="workspace" className="m-0 flex flex-col gap-4 outline-none min-h-[600px] h-[calc(100vh-280px)]">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-4 shadow-sm shrink-0">
                      <div className="flex items-center gap-3">
                         <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
                           <FileCode2 className="h-4 w-4 text-primary" />
                         </div>
                         <div>
                           <h3 className="text-sm font-semibold text-foreground">{tr("Workspace редактор", "Workspace Editor")}</h3>
                           <p className="text-[11px] text-muted-foreground">
                             {tr("Править SKILL.md и text-файлы в references/, scripts/ и assets/.", "Edit SKILL.md and text files under references/, scripts/, and assets/.")}
                           </p>
                         </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button variant="secondary" size="sm" className="h-8 gap-1.5 rounded-md px-3 text-[11px]" onClick={() => setCreateFileOpen(true)} disabled={!canEditSkill}>
                          <FolderPlus className="h-3.5 w-3.5" />
                          {tr("Новый файл", "New File")}
                        </Button>
                        <Button size="sm" className="h-8 gap-1.5 rounded-md px-3 text-[11px] shadow-sm bg-primary hover:bg-primary/90 text-primary-foreground transition-all" onClick={saveCurrentFile} disabled={!selectedFilePath || !isEditorDirty || updateFileMutation.isPending || !canEditSelectedFile}>
                          {updateFileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                          {tr("Сохранить", "Save")}
                        </Button>

                        <div className="w-px h-5 bg-border/80 mx-1"></div>

                        <Button variant="ghost" size="sm" className="h-8 gap-1.5 rounded-md px-3 text-[11px] text-destructive hover:bg-destructive/10 hover:text-destructive transition-colors" onClick={removeCurrentFile} disabled={!selectedFilePath || selectedFilePath === "SKILL.md" || deleteFileMutation.isPending || !canEditSelectedFile}>
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
                      <div className="w-1/4 min-w-[240px] flex flex-col gap-2 rounded-xl border border-border/40 bg-muted/10 p-3 overflow-y-auto">
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <div>
                            <p className="text-xs font-medium text-foreground">{tr("Файлы пакета", "Package Files")}</p>
                            <p className="text-[10px] text-muted-foreground">{tr("SKILL.md, references/, scripts/, assets/", "SKILL.md, references/, scripts/, assets/")}</p>
                          </div>
                          {isFetchingWorkspace ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : null}
                        </div>
                        {!workspace?.files.length ? (
                          <div className="rounded-xl border border-dashed border-border/70 px-3 py-6 text-center text-[11px] text-muted-foreground">
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
                                  selectedFilePath === file.path ? "border-primary/40 bg-primary/5" : "border-border/70 bg-background/24 hover:bg-background/40"
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="truncate text-[11px] font-medium text-foreground">{file.name}</span>
                                  <span className="text-[10px] text-muted-foreground">{formatFileSize(file.size)}</span>
                                </div>
                                <div className="mt-1 truncate font-mono text-[10px] text-muted-foreground">{file.path}</div>
                                <div className="mt-2 flex flex-wrap gap-1">
                                  <Badge variant="outline" className="text-[9px]">{fileKindLabel(file.kind, lang)}</Badge>
                                  <Badge variant="secondary" className="text-[9px]">{file.language}</Badge>
                                </div>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="flex-1 flex flex-col rounded-xl border border-border/40 bg-muted/5">
                        {!selectedWorkspaceFile ? (
                          <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted-foreground">
                            {tr("Выберите файл слева, чтобы открыть редактор.", "Select a file on the left to open the editor.")}
                          </div>
                        ) : isFetchingFile && !selectedFileDetail ? (
                          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            {tr("Загрузка файла...", "Loading file...")}
                          </div>
                        ) : (
                          <div className="flex flex-col h-full">
                            <div className="border-b border-border/40 px-4 py-4 bg-background/50 shrink-0">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <div className="text-sm font-medium text-foreground">{selectedWorkspaceFile.name}</div>
                                  <div className="mt-1 break-all font-mono text-[10px] text-muted-foreground">{selectedWorkspaceFile.path}</div>
                                </div>
                                <div className="flex flex-wrap gap-1">
                                  <Badge variant="outline" className="text-[9px]">{fileKindLabel(selectedWorkspaceFile.kind, lang)}</Badge>
                                  <Badge variant="secondary" className="text-[9px]">{selectedWorkspaceFile.language}</Badge>
                                  <Badge variant="outline" className="text-[9px]">{formatFileSize(selectedWorkspaceFile.size)}</Badge>
                                </div>
                              </div>
                            </div>
                            
                            <div className="p-4 flex-1 flex flex-col min-h-0 bg-background/20">
                              <Textarea 
                                value={editorValue} 
                                onChange={(event) => setEditorValue(event.target.value)} 
                                className="flex-1 font-mono text-[12px] leading-relaxed resize-none shadow-inner border-border/50" 
                                readOnly={!canEditSelectedFile} 
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="settings" className="m-0 space-y-4 outline-none">
                    <div className="rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-6 shadow-sm">
                      <div className="mb-6 flex items-center gap-3 border-b border-border/50 pb-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20 shadow-inner">
                          <Settings2 className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <h3 className="text-base font-semibold text-foreground">{tr("Настройки доступа", "Access Settings")}</h3>
                          <p className="text-[12px] text-muted-foreground">{tr("Текущее управление доступом пока не реализовано в Studio, перейдите в Access Management.", "Access control is managed in Access Management.")}</p>
                        </div>
                      </div>
                      <div className="text-[13px] text-muted-foreground">
                        {tr("В будущем здесь можно будет детально управлять настройками скилла, владельцем и привязками.", "In the future, detailed skill settings, ownership, and bindings will be manageable here.")}
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
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-auto p-0 rounded-xl border-border bg-background shadow-2xl">
          <div className="bg-muted/30 px-6 py-5 border-b border-border/40">
            <DialogHeader>
              <DialogTitle className="text-xl font-semibold flex items-center gap-2">
                <WandSparkles className="h-5 w-5 text-primary" />
                {tr("Создание скилла", "Create Skill")}
              </DialogTitle>
              <DialogDescription className="text-[13px] mt-1.5">
                {tr("Скилл — это рабочий плейбук агента. Заполните основные поля, а сложную конфигурацию мы спрятали в продвинутых настройках.", "A skill is an operational playbook. Fill out the basics, and we'll leave the complex configuration in advanced settings.")}
              </DialogDescription>
            </DialogHeader>
          </div>

          <div className="px-6 py-6 space-y-8">
            {/* 1. Base Info */}
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">1</div>
                <h3 className="text-sm font-medium">{tr("Основная информация", "Basic Information")}</h3>
              </div>
              
              <div className="space-y-4 pl-8">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Если есть готовый концепт, выберите шаблон", "If you have a concept, pick a template")}</Label>
                  <Select
                    value={selectedTemplateSlug}
                    onValueChange={(value) => {
                      setSelectedTemplateSlug(value);
                      const template = templates.find((item) => item.slug === value) || null;
                      setWizard(createWizardState(template));
                      setSlugTouched(false);
                    }}
                  >
                    <SelectTrigger className="h-10">
                      <SelectValue placeholder={tr("Начать с чистого листа", "Start from a blank slate")} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">{tr("С чистого листа (пустой скилл)", "Blank slate")}</SelectItem>
                      {templates.map((template) => (
                        <SelectItem key={template.slug} value={template.slug}>{template.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Название (Что делает?)", "Name (What it does)")}</Label>
                    <Input
                      className="h-10"
                      value={wizard.name}
                      onChange={(e) => {
                        const value = e.target.value;
                        setWizard((prev) => ({ ...prev, name: value, slug: slugTouched ? prev.slug : slugifySkillName(value) }));
                      }}
                      placeholder={tr("Управление токенами", "Token Management")}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Сервис (Где делает?)", "Service (Where)")}</Label>
                    <Input className="h-10" value={wizard.service} onChange={(e) => setWizard((prev) => ({ ...prev, service: e.target.value }))} placeholder={tr("github, keycloak...", "github, keycloak...")} />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Описание для агентов", "Description for agents")}</Label>
                  <Textarea rows={2} className="resize-none" value={wizard.description} onChange={(e) => setWizard((prev) => ({ ...prev, description: e.target.value }))} placeholder={tr("Когда и зачем агент должен применять этот плейбук.", "When and why the agent should apply this playbook.")} />
                </div>
              </div>
            </div>

            {/* 2. Architecture */}
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">2</div>
                <h3 className="text-sm font-medium">{tr("Структура и безопасность", "Structure & Security")}</h3>
              </div>

              <div className="pl-8 grid gap-6 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Уровень безопасности", "Safety Level")}</Label>
                  <Select value={wizard.safety_level} onValueChange={(value) => setWizard((prev) => ({ ...prev, safety_level: value }))}>
                    <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SAFETY_LEVELS.map((level) => (<SelectItem key={level} value={level}>{level}</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-3 pt-1">
                  <div className="flex items-center justify-between gap-2">
                    <Label className="cursor-pointer text-xs font-normal" htmlFor="tog-ref">{tr("Добавить папку references/", "Include references/ folder")}</Label>
                    <Switch id="tog-ref" checked={wizard.with_references} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_references: Boolean(checked) }))} />
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <Label className="cursor-pointer text-xs font-normal" htmlFor="tog-scr">{tr("Добавить папку scripts/", "Include scripts/ folder")}</Label>
                    <Switch id="tog-scr" checked={wizard.with_scripts} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_scripts: Boolean(checked) }))} />
                  </div>
                </div>
              </div>
            </div>

            {/* 3. Advanced Tools */}
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="advanced" className="border-border/40">
                <AccordionTrigger className="text-sm px-2 hover:bg-muted/30 rounded-md transition-colors">{tr("Продвинутые настройки (Опционально)", "Advanced Settings (Optional)")}</AccordionTrigger>
                <AccordionContent className="pt-4 px-2 space-y-5">
                  
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Slug (Уникальный ID)", "Slug (Unique ID)")}</Label>
                      <Input className="h-9 font-mono text-xs" value={wizard.slug} onChange={(e) => { setSlugTouched(true); setWizard((prev) => ({ ...prev, slug: e.target.value })); }} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Категория", "Category")}</Label>
                      <Input className="h-9 text-xs" value={wizard.category} onChange={(e) => setWizard((prev) => ({ ...prev, category: e.target.value }))} placeholder="IAM, DevOps..." />
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("UI-подсказка", "UI Hint")}</Label>
                      <Input className="h-9 text-xs" value={wizard.ui_hint} onChange={(e) => setWizard((prev) => ({ ...prev, ui_hint: e.target.value }))} placeholder={tr("Инструкция для списка", "Hint for list view")} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Теги (CSV)", "Tags (CSV)")}</Label>
                      <Input className="h-9 text-xs" value={wizard.tags_text} onChange={(e) => setWizard((prev) => ({ ...prev, tags_text: e.target.value }))} placeholder="tag1, tag2" />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Рекомендуемые MCP инструменты (CSV)", "Recommended MCP tools (CSV)")}</Label>
                    <Input className="h-9 text-xs" value={wizard.recommended_tools_text} onChange={(e) => setWizard((prev) => ({ ...prev, recommended_tools_text: e.target.value }))} placeholder="github_search, ask_user" />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Guardrail Правила", "Guardrail Rules")}</Label>
                    <Textarea rows={2} className="text-xs" value={wizard.guardrail_summary_text} onChange={(e) => setWizard((prev) => ({ ...prev, guardrail_summary_text: e.target.value }))} placeholder={tr("Описание жестких ограничений.", "Description of hard constraints.")} />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Runtime Policy (Конфиг среды)", "Runtime Policy (Env config)")}</Label>
                    <Textarea rows={6} value={wizard.runtime_policy_text} onChange={(e) => setWizard((prev) => ({ ...prev, runtime_policy_text: e.target.value }))} className="font-mono text-[11px] bg-muted/20" />
                  </div>

                  <div className="flex items-center space-x-2 pt-2">
                    <Switch id="force-overwrite" checked={wizard.force} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, force: Boolean(checked) }))} />
                    <Label htmlFor="force-overwrite" className="text-xs text-destructive">{tr("Перезаписать скилл с таким же slug", "Overwrite skill with same slug")}</Label>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>

          <div className="bg-muted/20 px-6 py-4 flex items-center justify-between border-t border-border/40">
            <Button variant="ghost" className="text-muted-foreground" onClick={() => setCreateOpen(false)}>{tr("Отмена", "Cancel")}</Button>
            <Button onClick={submitWizard} disabled={!wizard.name.trim() || !wizard.description.trim() || scaffoldMutation.isPending} className="gap-2 px-6">
              {scaffoldMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <WandSparkles className="h-4 w-4" />}
              {tr("Создать", "Create")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={createFileOpen} onOpenChange={setCreateFileOpen}>
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-auto rounded-md border-border bg-background/95">
          <DialogHeader>
            <DialogTitle>{tr("Новый workspace-файл", "New workspace file")}</DialogTitle>
            <DialogDescription>{tr("Создайте text-файл внутри references/, scripts/ или assets/. Для нового playbook-материала обычно начинайте с references/guide.md.", "Create a text file inside references/, scripts/, or assets/. For new playbook material, start with references/guide.md.")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs">{tr("Путь", "Path")}</Label>
              <Input value={createFilePath} onChange={(event) => setCreateFilePath(event.target.value)} placeholder="references/guide.md" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{tr("Содержимое", "Content")}</Label>
              <Textarea rows={16} value={createFileContent} onChange={(event) => setCreateFileContent(event.target.value)} className="font-mono text-[12px] leading-5" />
            </div>
            <div className="rounded-xl border border-border/70 bg-background/24 px-4 py-4 text-[11px] leading-5 text-muted-foreground">
              {tr("Разрешены только относительные пути и только text-расширения. Абсолютные пути, скрытые файлы и выход за пределы skill directory backend отклоняет.", "Only relative paths and text extensions are allowed. Absolute paths, hidden files, and escaping the skill directory are rejected by the backend.")}
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
        <DialogContent className="max-h-[85vh] max-w-4xl overflow-auto rounded-md border-border bg-background/95">
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
