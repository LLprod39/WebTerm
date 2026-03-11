import { useEffect, useMemo, useState } from "react";
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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import {
  studioSkills,
  type StudioSkill,
  type StudioSkillScaffoldPayload,
  type StudioSkillTemplate,
  type StudioSkillValidationResponse,
  type StudioSkillWorkspaceFile,
} from "@/lib/api";
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
      className={`w-full rounded-xl border px-3 py-3 text-left transition-[border-color,background-color] ${
        isSelected
          ? "border-border/90 bg-background/40"
          : "border-border/70 bg-background/24 hover:border-border/90 hover:bg-background/36"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-foreground">{skill.name}</p>
            {skill.runtime_enforced && <span className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{tr("enforced", "enforced")}</span>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
            {skill.service && <span>{skill.service}</span>}
            {skill.category && <span>· {skill.category}</span>}
          </div>
        </div>
        {skill.safety_level && <span className="text-[10px] text-muted-foreground">{skill.safety_level}</span>}
      </div>
      {skill.description && <p className="mt-3 text-[11px] leading-5 text-muted-foreground">{skill.description}</p>}
      {skill.guardrail_summary?.length > 0 && <p className="mt-2 text-[10px] leading-5 text-muted-foreground">{skill.guardrail_summary[0]}</p>}
      {skill.tags?.length > 0 && <div className="mt-3 text-[10px] text-muted-foreground">{skill.tags.slice(0, 3).join(" · ")}</div>}
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

  const { data: skills = [], isLoading } = useQuery({
    queryKey: ["studio", "skills"],
    queryFn: studioSkills.list,
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
    if (!filteredSkills.length) {
      if (selectedSlug) setSelectedSlug("");
      return;
    }
    if (!selectedSlug || !filteredSkills.some((skill) => skill.slug === selectedSlug)) {
      setSelectedSlug(filteredSkills[0].slug);
    }
  }, [filteredSignature, selectedSlug, filteredSkills]);

  const { data: selectedSkill, isFetching: isFetchingSkill } = useQuery({
    queryKey: ["studio", "skills", selectedSlug],
    queryFn: () => studioSkills.get(selectedSlug),
    enabled: !!selectedSlug,
  });

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
    if (!selectedFilePath) return;
    updateFileMutation.mutate({ path: selectedFilePath, content: editorValue });
  };

  const removeCurrentFile = () => {
    if (!selectedFilePath || selectedFilePath === "SKILL.md") return;
    const confirmed = window.confirm(
      tr(`Удалить файл ${selectedFilePath}? Это действие нельзя отменить.`, `Delete ${selectedFilePath}? This cannot be undone.`),
    );
    if (!confirmed) return;
    deleteFileMutation.mutate(selectedFilePath);
  };

  const isEditorDirty = Boolean(selectedFileDetail && editorValue !== selectedFileDetail.content);
  const workspaceErrors = workspace?.validation.errors || [];
  const workspaceWarnings = workspace?.validation.warnings || [];

  return (
    <div className="flex h-full flex-col">
      <div className="px-6 py-6">
        <section className="rounded-xl border border-border/70 bg-background/24 px-5 py-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="max-w-3xl space-y-3">
              <div className="flex items-center gap-3">
                <Button variant="ghost" size="icon" className="h-9 w-9 rounded-md" onClick={() => navigate("/studio")}>
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{tr("Studio library", "Studio library")}</div>
                  <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-foreground">
                    <BookOpen className="h-5 w-5 text-primary" />
                    {tr("Каталог скиллов", "Skill Catalog")}
                  </h1>
                </div>
              </div>
              <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                {tr(
                  "Скилл здесь это рабочий плейбук. Выберите сервис, проверьте guardrails и runtime policy, а затем правьте сам workspace прямо из Studio.",
                  "A skill here is an operating playbook. Pick the service, review guardrails and runtime policy, then edit the workspace directly from Studio.",
                )}
              </p>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
                <span>{tr(`${skills.length} скиллов`, `${skills.length} skills`)}</span>
                <span>{tr(`${runtimeEnforcedCount} enforced`, `${runtimeEnforcedCount} enforced`)}</span>
                <span>{tr(`${serviceCount} сервисов`, `${serviceCount} services`)}</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 xl:justify-end">
              <Button variant="outline" size="sm" onClick={() => navigate("/studio/mcp")} className="h-9 gap-1.5 rounded-md px-3">
                <Server className="h-3.5 w-3.5" />
                {tr("MCP Реестр", "MCP Registry")}
              </Button>
              <Button variant="outline" size="sm" onClick={() => validateMutation.mutate()} className="h-9 gap-1.5 rounded-md px-3">
                {validateMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Shield className="h-3.5 w-3.5" />}
                {tr("Проверить библиотеку", "Validate Library")}
              </Button>
              <Button size="sm" onClick={() => openCreateDialog()} className="h-9 gap-1.5 rounded-md px-4">
                <WandSparkles className="h-3.5 w-3.5" />
                {tr("Новый скилл", "New Skill")}
              </Button>
              <Button size="sm" variant="outline" onClick={() => navigate("/studio/agents")} className="h-9 gap-1.5 rounded-md px-3">
                <Bot className="h-3.5 w-3.5" />
                {tr("Конфиги агентов", "Agent Configs")}
              </Button>
            </div>
          </div>
        </section>
      </div>

      <div className="flex-1 overflow-auto px-6 pb-8">
        <div className="space-y-4">
          {validationReport && <ValidationSummaryCard report={validationReport} />}
          <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
            <div className="space-y-4 xl:sticky xl:top-6 xl:self-start">
              <div className="rounded-xl border border-border/70 bg-background/24 p-4">
                <div className="mb-3">
                  <Label className="text-xs">{tr("Каталог", "Catalog")}</Label>
                  <p className="mt-1 text-[11px] text-muted-foreground">{tr("Ищите по сервису, тегам или названию. Полный playbook и файловый workspace откроются справа.", "Search by service, tags, or name. The full playbook and workspace open on the right.")}</p>
                </div>

                <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_160px] xl:grid-cols-1">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder={tr("Поиск по скиллам, сервисам и тегам...", "Search skills, services, tags...")}
                      className="h-10 rounded-md pl-9 text-sm"
                    />
                  </div>
                  <Select value={serviceFilter} onValueChange={setServiceFilter}>
                    <SelectTrigger className="h-10 rounded-md text-xs">
                      <SelectValue placeholder={tr("Все сервисы", "All services")} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all__">{tr("Все сервисы", "All services")}</SelectItem>
                      {services.map((service) => (
                        <SelectItem key={service} value={service}>{service}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                  <span>{tr(`${filteredSkills.length} найдено`, `${filteredSkills.length} found`)}</span>
                  <span>{tr(`${services.length} сервисных фильтров`, `${services.length} service filters`)}</span>
                </div>

                <div className="mt-4">
                  {isLoading ? (
                    <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {tr("Загрузка скиллов...", "Loading skills...")}
                    </div>
                  ) : filteredSkills.length === 0 ? (
                    <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-border/70 bg-background/24 text-center text-sm text-muted-foreground">
                      {tr("По текущим фильтрам скиллы не найдены.", "No skills match the current filters.")}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {filteredSkills.map((skill) => (
                        <SkillCard key={skill.slug} skill={skill} isSelected={skill.slug === selectedSlug} onSelect={() => setSelectedSlug(skill.slug)} lang={lang} />
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-border/70 bg-background/24 p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <Label className="text-xs">{tr("Создать новый скилл", "Create a new skill")}</Label>
                    <p className="mt-1 text-[11px] text-muted-foreground">{tr("Лучше выбрать шаблон сервиса и потом открывать мастер. Так сразу подтянутся дефолтные policy и guardrails.", "Pick a service template first, then open the wizard. That preloads sensible policy and guardrails.")}</p>
                  </div>
                  <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md px-3 text-[11px]" onClick={() => openCreateDialog()}>
                    <Sparkles className="h-3 w-3" />
                    {tr("Пустой мастер", "Blank Wizard")}
                  </Button>
                </div>

                <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <Select value={launcherTemplateSlug} onValueChange={setLauncherTemplateSlug}>
                    <SelectTrigger className="h-10 rounded-md text-xs">
                      <SelectValue placeholder={tr("Выберите шаблон сервиса", "Choose a service template")} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">{tr("Начать с нуля", "Start from scratch")}</SelectItem>
                      {templates.map((template) => (
                        <SelectItem key={template.slug} value={template.slug}>
                          {template.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button size="sm" className="h-10 gap-1.5 rounded-md px-4" onClick={() => openCreateDialog(launcherTemplate)}>
                    <WandSparkles className="h-3.5 w-3.5" />
                    {tr("Открыть мастер", "Open wizard")}
                  </Button>
                </div>

                {launcherTemplate && (
                  <div className="mt-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3">
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="font-medium text-foreground">{launcherTemplate.name}</span>
                      {launcherTemplate.defaults.service && <span className="text-muted-foreground">{launcherTemplate.defaults.service}</span>}
                      {launcherTemplate.defaults.safety_level && <span className="text-muted-foreground">· {launcherTemplate.defaults.safety_level}</span>}
                    </div>
                    <p className="mt-2 text-[11px] leading-5 text-muted-foreground">{launcherTemplate.summary || launcherTemplate.description}</p>
                  </div>
                )}
              </div>
            </div>

            <div className="min-w-0">
              {!selectedSlug ? (
                <div className="flex h-72 items-center justify-center rounded-xl border border-border/70 bg-background/24 text-center text-sm text-muted-foreground">
                  {tr("Выберите скилл слева, чтобы изучить его плейбук, guardrails и workspace.", "Select a skill on the left to inspect its playbook, guardrails, and workspace.")}
                </div>
              ) : isFetchingSkill && !selectedSkill ? (
                <div className="flex h-72 items-center justify-center rounded-xl border border-border/70 bg-background/24 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {tr("Загрузка деталей скилла...", "Loading skill details...")}
                </div>
              ) : selectedSkill ? (
                <div className="space-y-4">
                  <div className="rounded-xl border border-border/70 bg-background/24 p-5">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-lg font-semibold text-foreground">{selectedSkill.name}</h2>
                      <Badge variant="outline" className="font-mono text-[10px]">{selectedSkill.slug}</Badge>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                      {selectedSkill.service && <span>{selectedSkill.service}</span>}
                      {selectedSkill.category && <span>· {selectedSkill.category}</span>}
                      {selectedSkill.runtime_enforced && <span>· {tr("runtime enforced", "runtime enforced")}</span>}
                      {selectedSkill.safety_level && <span>· {selectedSkill.safety_level}</span>}
                    </div>
                    {selectedSkill.description && <p className="mt-3 text-sm leading-6 text-muted-foreground">{selectedSkill.description}</p>}
                    {selectedSkill.ui_hint && <div className="mt-3 rounded-lg border border-border/60 bg-background/28 px-3 py-2 text-[11px] text-muted-foreground">{selectedSkill.ui_hint}</div>}
                    <div className="mt-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3">
                      <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{tr("Workspace path", "Workspace path")}</div>
                      <div className="mt-1 break-all font-mono text-[11px] text-foreground">{selectedSkill.path}</div>
                    </div>
                  </div>

                  <div className="grid gap-4 lg:grid-cols-2">
                    {selectedSkill.guardrail_summary?.length > 0 && (
                      <div className="rounded-xl border border-border/70 bg-background/24 p-4">
                        <p className="text-xs font-medium">{tr("Guardrails", "Guardrails")}</p>
                        <div className="mt-2 space-y-1">
                          {selectedSkill.guardrail_summary.map((item) => (
                            <p key={item} className="text-[11px] leading-5 text-muted-foreground">• {item}</p>
                          ))}
                        </div>
                      </div>
                    )}

                    {selectedSkill.recommended_tools?.length > 0 && (
                      <div className="rounded-xl border border-border/70 bg-background/24 p-4">
                        <p className="text-xs font-medium">{tr("Рекомендуемые инструменты агента", "Recommended agent tools")}</p>
                        <div className="mt-2 flex flex-wrap gap-1">
                          {selectedSkill.recommended_tools.map((toolName) => (
                            <span key={toolName} className="rounded-full bg-background/30 px-2 py-1 text-[10px] text-muted-foreground">{toolName}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {selectedSkill.runtime_enforced && (
                      <div className="rounded-xl border border-border/70 bg-background/24 p-4 lg:col-span-2">
                        <p className="text-xs font-medium">{tr("Runtime policy", "Runtime policy")}</p>
                        <pre className="mt-2 overflow-auto whitespace-pre-wrap rounded bg-muted/20 p-3 font-mono text-[11px] leading-5 text-muted-foreground">
                          {JSON.stringify(selectedSkill.runtime_policy, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>

                  <div className="rounded-xl border border-border/70 bg-background/24 p-5">
                    <div className="mb-4">
                      <h3 className="text-base font-medium text-foreground">{tr("Плейбук скилла", "Skill Playbook")}</h3>
                      <p className="mt-1 text-[11px] text-muted-foreground">{tr("Ниже полный Markdown, который читает агент во время работы.", "Below is the full Markdown the agent reads at runtime.")}</p>
                    </div>
                    <SkillMarkdown content={selectedSkill.content} />
                  </div>

                  <div className="rounded-xl border border-border/70 bg-background/24 p-5">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <h3 className="flex items-center gap-2 text-base font-medium text-foreground">
                          <FileCode2 className="h-4 w-4 text-primary" />
                          {tr("Workspace редактор", "Workspace Editor")}
                        </h3>
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {tr(
                            "Здесь можно править сам SKILL.md и text-файлы в references/, scripts/ и assets/. Backend это уже поддерживает, теперь и фронт тоже.",
                            "You can edit SKILL.md and text files under references/, scripts/, and assets/. The backend already supported it; now the frontend does too.",
                          )}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md px-3 text-[11px]" onClick={() => setCreateFileOpen(true)}>
                          <FolderPlus className="h-3.5 w-3.5" />
                          {tr("Новый файл", "New File")}
                        </Button>
                        <Button size="sm" className="h-8 gap-1.5 rounded-md px-3 text-[11px]" onClick={saveCurrentFile} disabled={!selectedFilePath || !isEditorDirty || updateFileMutation.isPending}>
                          {updateFileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                          {tr("Сохранить", "Save")}
                        </Button>
                        <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md px-3 text-[11px]" onClick={removeCurrentFile} disabled={!selectedFilePath || selectedFilePath === "SKILL.md" || deleteFileMutation.isPending}>
                          {deleteFileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                          {tr("Удалить", "Delete")}
                        </Button>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                      <span>{tr(`${workspace?.files.length || 0} файлов`, `${workspace?.files.length || 0} files`)}</span>
                      <span>{tr("Только UTF-8 text файлы", "UTF-8 text files only")}</span>
                      <span>{tr("Лимит файла: 500 KB", "File limit: 500 KB")}</span>
                    </div>

                    <div className="mt-4 grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                      <div className="rounded-xl border border-border/70 bg-background/30 p-3">
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

                      <div className="rounded-xl border border-border/70 bg-background/30">
                        {!selectedWorkspaceFile ? (
                          <div className="flex min-h-[360px] items-center justify-center px-6 text-center text-sm text-muted-foreground">
                            {tr("Выберите файл слева, чтобы открыть редактор.", "Select a file on the left to open the editor.")}
                          </div>
                        ) : isFetchingFile && !selectedFileDetail ? (
                          <div className="flex min-h-[360px] items-center justify-center text-sm text-muted-foreground">
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            {tr("Загрузка файла...", "Loading file...")}
                          </div>
                        ) : (
                          <>
                            <div className="border-b border-border/70 px-4 py-4">
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

                            <div className="p-4">
                              <Textarea rows={20} value={editorValue} onChange={(event) => setEditorValue(event.target.value)} className="min-h-[360px] font-mono text-[12px] leading-5" />
                              <div className="mt-3 flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
                                <div className="text-[11px] text-muted-foreground">
                                  {selectedWorkspaceFile.path === "SKILL.md"
                                    ? tr("Изменения в SKILL.md обновят playbook, который читает агент во время выполнения.", "Changes to SKILL.md update the playbook the agent reads at runtime.")
                                    : tr("Редактируются только text-файлы. Для бинарных assets backend пока не подходит.", "Only text files are editable. Binary assets are not supported here yet.")}
                                </div>
                                <div className="flex flex-wrap items-center gap-2">
                                  {isEditorDirty ? <span className="text-[11px] text-amber-300">{tr("Есть несохранённые изменения", "Unsaved changes")}</span> : <span className="text-[11px] text-muted-foreground">{tr("Сохранено", "Saved")}</span>}
                                  <Button size="sm" className="h-8 gap-1.5 rounded-md px-3 text-[11px]" onClick={saveCurrentFile} disabled={!isEditorDirty || updateFileMutation.isPending}>
                                    {updateFileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                                    {tr("Сохранить файл", "Save file")}
                                  </Button>
                                </div>
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 lg:grid-cols-2">
                      <div className="rounded-xl border border-border/70 bg-background/30 p-4">
                        <div className="flex items-center gap-2">
                          {workspace?.validation.is_valid ? <CheckCircle2 className="h-4 w-4 text-green-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
                          <p className="text-sm font-medium text-foreground">{tr("Состояние workspace", "Workspace status")}</p>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                          <span>{workspaceErrors.length} {tr("ошибок", "errors")}</span>
                          <span>{workspaceWarnings.length} {tr("предупреждений", "warnings")}</span>
                        </div>
                      </div>
                      <div className="rounded-xl border border-border/70 bg-background/30 p-4 text-[11px] leading-5 text-muted-foreground">
                        {tr(
                          "Если нужен новый runtime-материал, сначала создайте файл вида references/guide.md или scripts/helper.py, потом уже прикрепляйте этот skill к агенту или pipeline node.",
                          "If you need new runtime material, create a file like references/guide.md or scripts/helper.py first, then attach the skill to an agent or pipeline node.",
                        )}
                      </div>
                    </div>

                    {(workspaceErrors.length > 0 || workspaceWarnings.length > 0) && (
                      <div className="mt-4 space-y-3">
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
                  </div>
                </div>
              ) : (
                <div className="flex h-72 items-center justify-center rounded-xl border border-border/70 bg-background/24 text-sm text-muted-foreground">
                  {tr("Детали скилла недоступны.", "Skill details are unavailable.")}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[90vh] max-w-5xl overflow-auto rounded-md border-border bg-background/95">
          <DialogHeader>
            <DialogTitle>{tr("Мастер скиллов", "Skill Wizard")}</DialogTitle>
            <DialogDescription>{tr("Создайте корпоративный пакет скиллов из шаблона сервиса или с нуля.", "Create a corporate skill pack from a service template or from scratch.")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border/70 bg-background/24 px-3 py-3 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{wizard.name.trim() || tr("Новый скилл", "New skill")}</span>
            <span>{selectedTemplate ? selectedTemplate.name : tr("без шаблона", "no template")}</span>
            <span>{tr(`safety: ${wizard.safety_level}`, `safety: ${wizard.safety_level}`)}</span>
            <span>{tr(`${[wizard.with_references, wizard.with_scripts, wizard.with_assets].filter(Boolean).length} папок`, `${[wizard.with_references, wizard.with_scripts, wizard.with_assets].filter(Boolean).length} folders`)}</span>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-4">
              <div className="workspace-subtle rounded-2xl px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  {([
                    { id: "basics", label: tr("1. Основа", "1. Basics"), description: tr("Шаблон, имя, сервис", "Template, name, service") },
                    { id: "policy", label: tr("2. Guardrails", "2. Guardrails"), description: tr("Правила, теги, runtime policy", "Rules, tags, runtime policy") },
                    { id: "files", label: tr("3. Файлы", "3. Files"), description: tr("references, scripts, assets", "references, scripts, assets") },
                  ] as const).map((section) => {
                    const active = wizardSection === section.id;
                    return (
                      <button
                        key={section.id}
                        type="button"
                        onClick={() => setWizardSection(section.id)}
                        className={`rounded-xl border px-3 py-2 text-left transition-colors ${
                          active ? "border-border bg-background text-foreground" : "border-transparent bg-transparent text-muted-foreground hover:border-border/70 hover:bg-background/35 hover:text-foreground"
                        }`}
                      >
                        <div className="text-xs font-medium">{section.label}</div>
                        <div className="mt-1 text-[11px] leading-5 text-muted-foreground">{section.description}</div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {wizardSection === "basics" && (
                <div className="space-y-4 rounded-xl border border-border/70 bg-background/24 p-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">{tr("Шаблон сервиса", "Service Template")}</Label>
                    <Select
                      value={selectedTemplateSlug}
                      onValueChange={(value) => {
                        setSelectedTemplateSlug(value);
                        const template = templates.find((item) => item.slug === value) || null;
                        setWizard(createWizardState(template));
                        setSlugTouched(false);
                      }}
                    >
                      <SelectTrigger className="text-xs">
                        <SelectValue placeholder={tr("Начать с нуля", "Start from scratch")} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">{tr("Пустой мастер", "Blank wizard")}</SelectItem>
                        {templates.map((template) => (
                          <SelectItem key={template.slug} value={template.slug}>{template.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {selectedTemplate && (
                    <div className="rounded-xl border border-border/70 bg-background/30 px-3 py-3">
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <span className="font-medium text-foreground">{selectedTemplate.name}</span>
                        {selectedTemplate.defaults.service && <span className="text-muted-foreground">{selectedTemplate.defaults.service}</span>}
                        {selectedTemplate.defaults.safety_level && <span className="text-muted-foreground">· {selectedTemplate.defaults.safety_level}</span>}
                      </div>
                      <p className="mt-2 text-[11px] leading-5 text-muted-foreground">{selectedTemplate.summary || selectedTemplate.description}</p>
                    </div>
                  )}

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs">{tr("Название", "Name")}</Label>
                      <Input
                        value={wizard.name}
                        onChange={(e) => {
                          const value = e.target.value;
                          setWizard((prev) => ({ ...prev, name: value, slug: slugTouched ? prev.slug : slugifySkillName(value) }));
                        }}
                        placeholder={tr("Рабочий процесс операций Keycloak", "Keycloak Operations Workflow")}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">{tr("Slug", "Slug")}</Label>
                      <Input value={wizard.slug} onChange={(e) => { setSlugTouched(true); setWizard((prev) => ({ ...prev, slug: e.target.value })); }} placeholder={tr("keycloak-operations-workflow", "keycloak-operations-workflow")} />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs">{tr("Описание", "Description")}</Label>
                    <Textarea rows={3} value={wizard.description} onChange={(e) => setWizard((prev) => ({ ...prev, description: e.target.value }))} placeholder={tr("Когда этот скилл нужно подключать и использовать.", "When this skill should be attached and used.")} />
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs">{tr("Сервис", "Service")}</Label>
                      <Input value={wizard.service} onChange={(e) => setWizard((prev) => ({ ...prev, service: e.target.value }))} placeholder={tr("keycloak", "keycloak")} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">{tr("Категория", "Category")}</Label>
                      <Input value={wizard.category} onChange={(e) => setWizard((prev) => ({ ...prev, category: e.target.value }))} placeholder={tr("Управление доступом", "Identity and Access")} />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs">{tr("Уровень безопасности", "Safety level")}</Label>
                    <Select value={wizard.safety_level} onValueChange={(value) => setWizard((prev) => ({ ...prev, safety_level: value }))}>
                      <SelectTrigger className="text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {SAFETY_LEVELS.map((level) => (
                          <SelectItem key={level} value={level}>{level}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}

              {wizardSection === "policy" && (
                <div className="space-y-4 rounded-xl border border-border/70 bg-background/24 p-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">{tr("UI-подсказка", "UI hint")}</Label>
                    <Input value={wizard.ui_hint} onChange={(e) => setWizard((prev) => ({ ...prev, ui_hint: e.target.value }))} placeholder={tr("Короткая инструкция для админа в Studio", "Short admin-facing instruction in Studio")} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">{tr("Теги", "Tags")}</Label>
                    <Input value={wizard.tags_text} onChange={(e) => setWizard((prev) => ({ ...prev, tags_text: e.target.value }))} placeholder={tr("keycloak, iam, mcp, безопасность", "keycloak, iam, mcp, safety")} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">{tr("Сводка guardrail-правил", "Guardrail summary")}</Label>
                    <Textarea rows={3} value={wizard.guardrail_summary_text} onChange={(e) => setWizard((prev) => ({ ...prev, guardrail_summary_text: e.target.value }))} placeholder={tr("Требует preflight, фиксирует profile=test, блокирует переключение профиля", "Requires preflight, Pins profile=test, Blocks profile switching")} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">{tr("Рекомендуемые инструменты агента", "Recommended agent tools")}</Label>
                    <Input value={wizard.recommended_tools_text} onChange={(e) => setWizard((prev) => ({ ...prev, recommended_tools_text: e.target.value }))} placeholder={tr("report, ask_user, analyze_output", "report, ask_user, analyze_output")} />
                  </div>
                  <div className="rounded-xl border border-border/70 bg-background/30 p-4">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-muted-foreground" />
                      <p className="text-sm font-medium">{tr("Runtime policy", "Runtime policy")}</p>
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">{tr("Оставляйте template-default policy, если не уверены в точных названиях MCP tool и pinned args.", "Keep the template default unless you know the exact MCP tool names and pinned arguments.")}</p>
                    <Textarea rows={14} value={wizard.runtime_policy_text} onChange={(e) => setWizard((prev) => ({ ...prev, runtime_policy_text: e.target.value }))} className="mt-3 font-mono text-[11px]" />
                  </div>
                </div>
              )}

              {wizardSection === "files" && (
                <div className="space-y-4 rounded-xl border border-border/70 bg-background/24 p-4">
                  <div className="space-y-3 rounded-xl border border-border/70 bg-background/30 p-4">
                    <p className="text-sm font-medium">{tr("Необязательные папки скилла", "Optional skill folders")}</p>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-medium">{tr("references/", "references/")}</p>
                        <p className="text-[10px] text-muted-foreground">{tr("Доменные документы, примеры и длинные процедуры.", "Domain docs, examples, and longer procedures.")}</p>
                      </div>
                      <Switch checked={wizard.with_references} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_references: Boolean(checked) }))} />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-medium">{tr("scripts/", "scripts/")}</p>
                        <p className="text-[10px] text-muted-foreground">{tr("Детерминированные помощники для хрупких и повторяющихся действий.", "Deterministic helpers for fragile or repetitive actions.")}</p>
                      </div>
                      <Switch checked={wizard.with_scripts} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_scripts: Boolean(checked) }))} />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-medium">{tr("assets/", "assets/")}</p>
                        <p className="text-[10px] text-muted-foreground">{tr("Шаблоны, бренд-файлы и выходные ассеты.", "Templates, brand files, and output assets.")}</p>
                      </div>
                      <Switch checked={wizard.with_assets} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_assets: Boolean(checked) }))} />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-medium">{tr("Перезаписать существующий скилл", "Overwrite existing skill")}</p>
                        <p className="text-[10px] text-muted-foreground">{tr("Используйте только если осознанно обновляете тот же slug.", "Use only when intentionally updating the same slug.")}</p>
                      </div>
                      <Switch checked={wizard.force} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, force: Boolean(checked) }))} />
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className="rounded-xl border border-border/70 bg-background/24 p-4">
                <p className="text-xs font-medium text-foreground">{tr("Текущий пакет", "Current package")}</p>
                <div className="mt-3 space-y-2 text-[11px] text-muted-foreground">
                  <div className="rounded-xl border border-border/70 bg-background/30 px-3 py-3">
                    <div className="font-medium text-foreground">{wizard.name.trim() || tr("Новый скилл", "New skill")}</div>
                    <div className="mt-1 font-mono text-[10px] text-muted-foreground">{wizard.slug || tr("slug будет сгенерирован", "slug will be generated")}</div>
                  </div>
                  <div className="rounded-xl border border-border/70 bg-background/30 px-3 py-3">
                    <div>{selectedTemplate ? selectedTemplate.name : tr("Без сервисного шаблона", "No service template")}</div>
                    <div className="mt-1">{wizard.service || tr("Сервис не указан", "No service yet")} {wizard.category ? `· ${wizard.category}` : ""}</div>
                    <div className="mt-1">{tr(`safety: ${wizard.safety_level}`, `safety: ${wizard.safety_level}`)}</div>
                  </div>
                  <div className="rounded-xl border border-border/70 bg-background/30 px-3 py-3">
                    <div>{tr("Guardrails", "Guardrails")}: {wizard.guardrail_summary_text.trim() ? parseCsvInput(wizard.guardrail_summary_text).length : 0}</div>
                    <div className="mt-1">{tr("Рекомендуемые инструменты", "Recommended tools")}: {wizard.recommended_tools_text.trim() ? parseCsvInput(wizard.recommended_tools_text).length : 0}</div>
                    <div className="mt-1">{tr("Папки", "Folders")}: {[wizard.with_references, wizard.with_scripts, wizard.with_assets].filter(Boolean).length}</div>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-border/70 bg-background/24 p-4">
                <p className="text-xs font-medium text-foreground">{tr("Простой порядок", "Simple order")}</p>
                <div className="mt-2 space-y-2 text-[11px] leading-5 text-muted-foreground">
                  <p>{tr("1. Выберите template или начните с нуля.", "1. Pick a template or start from scratch.")}</p>
                  <p>{tr("2. Коротко опишите назначение и сервис.", "2. Describe the purpose and service.")}</p>
                  <p>{tr("3. Добавьте только нужные guardrails и policy.", "3. Add only the guardrails and policy you actually need.")}</p>
                  <p>{tr("4. Подключайте папки только если они реально нужны рантайму.", "4. Add folders only if the runtime truly needs them.")}</p>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCreateOpen(false)}>{tr("Отмена", "Cancel")}</Button>
            <Button onClick={submitWizard} disabled={!wizard.name.trim() || !wizard.description.trim() || scaffoldMutation.isPending} className="gap-1.5">
              {scaffoldMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <WandSparkles className="h-3.5 w-3.5" />}
              {tr("Создать скилл", "Create Skill")}
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
            <Button onClick={() => createFileMutation.mutate({ path: createFilePath.trim(), content: createFileContent })} disabled={!createFilePath.trim() || createFileMutation.isPending} className="gap-1.5">
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
