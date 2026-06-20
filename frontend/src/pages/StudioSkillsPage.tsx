import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { StudioNav } from "@/components/StudioNav";
import { useToast } from "@/hooks/use-toast";
import {
  fetchAuthSession,
  studioShareUsers,
  studioSkills,
  type StudioSkillDetail,
  type StudioSkillScaffoldPayload,
  type StudioSkillTemplate,
  type StudioSkillValidationResponse,
} from "@/lib/api";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { useI18n } from "@/lib/i18n";

import { SkillCatalogView } from "./studio-skills/SkillCatalogView";
import { ValidationSummaryCard } from "./studio-skills/SkillCards";
import { SkillDetailView } from "./studio-skills/SkillDetailView";
import { CreateFileDialog, CreateSkillDialog, SkillValidationDialog } from "./studio-skills/SkillDialogs";
import type { SkillAccessDraft } from "./studio-skills/SkillSettingsTab";
import {
  buildSkillScaffoldPayload,
  buildSkillSettingsPayload,
  createSkillSettingsDraft,
  createWizardState,
  runtimePolicyErrorMessage,
  starterFilesFromWizard,
  type SkillSettingsDraft,
  type SkillWizardState,
} from "./studio-skills/skillScaffold";

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
  const [skillAccessDraft, setSkillAccessDraft] = useState<SkillAccessDraft>({
    is_shared: false,
    shared_user_ids: [],
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

  const services = useMemo(
    () => Array.from(new Set(skills.map((skill) => skill.service).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
    [skills],
  );
  const filteredSkills = useMemo(
    () =>
      skills.filter((skill) => {
        const haystack = [skill.name, skill.slug, skill.description, skill.service, skill.category, ...(skill.tags || [])]
          .join(" ")
          .toLowerCase();
        const matchesSearch = !search.trim() || haystack.includes(search.trim().toLowerCase());
        const matchesService = serviceFilter === "__all__" || skill.service === serviceFilter;
        return matchesSearch && matchesService;
      }),
    [search, serviceFilter, skills],
  );
  const selectedTemplate = useMemo(
    () => templates.find((item) => item.slug === selectedTemplateSlug) || null,
    [templates, selectedTemplateSlug],
  );

  const filteredSignature = filteredSkills.map((skill) => skill.slug).join("|");
  const runtimeEnforcedCount = skills.filter((skill) => skill.runtime_enforced).length;
  const serviceCount = services.length;
  const starterFiles = starterFilesFromWizard(wizard);
  const canSubmitWizard = Boolean(wizard.name.trim()) && Boolean(wizard.description.trim());

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
      toast({ description });
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
  }, [filteredSignature, filteredSkills, selectedSlug]);

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
    [selectedFilePath, workspace],
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

  const isEditorDirty = Boolean(selectedFileDetail && editorValue !== selectedFileDetail.content);
  const workspaceErrors = workspace?.validation.errors || [];
  const workspaceWarnings = workspace?.validation.warnings || [];
  const canEditSkill = Boolean(selectedSkill?.can_edit);
  const canShareSkill = Boolean(selectedSkill?.can_share && isAdmin);
  const canEditSelectedFile = Boolean(selectedWorkspaceFile?.editable && canEditSkill);

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

    let payload: Partial<StudioSkillDetail>;
    try {
      payload = buildSkillSettingsPayload(skillSettingsDraft);
    } catch (error) {
      toast({ variant: "destructive", description: runtimePolicyErrorMessage(error, tr) });
      return;
    }

    updateSkillSettingsMutation.mutate(payload);
  };

  const openCreateDialog = (template?: StudioSkillTemplate | null) => {
    setSelectedTemplateSlug(template?.slug || "__none__");
    setWizard(createWizardState(template || null, lang));
    setSlugTouched(false);
    setCreateOpen(true);
  };

  const submitWizard = () => {
    let payload: StudioSkillScaffoldPayload;
    try {
      payload = buildSkillScaffoldPayload(wizard, selectedTemplateSlug);
    } catch (error) {
      toast({ variant: "destructive", description: runtimePolicyErrorMessage(error, tr) });
      return;
    }

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

  return (
    <div className="flex h-full flex-col">
      <StudioNav />
      {validationReport && (
        <div className="px-6 py-2">
          <ValidationSummaryCard report={validationReport} />
        </div>
      )}

      {!selectedSlug ? (
        <SkillCatalogView
          tr={tr}
          lang={lang}
          skills={skills}
          filteredSkills={filteredSkills}
          services={services}
          search={search}
          serviceFilter={serviceFilter}
          runtimeEnforcedCount={runtimeEnforcedCount}
          serviceCount={serviceCount}
          isLoading={isLoading}
          isValidating={validateMutation.isPending}
          canOpenMcp={canOpenMcp}
          canOpenAgents={canOpenAgents}
          onSearchChange={setSearch}
          onServiceFilterChange={setServiceFilter}
          onSelectSkill={setSelectedSlug}
          onCreateSkill={() => openCreateDialog()}
          onValidate={() => validateMutation.mutate()}
          onOpenMcp={() => navigate("/studio/mcp")}
          onOpenAgents={() => navigate("/studio/agents")}
        />
      ) : (
        <SkillDetailView
          tr={tr}
          lang={lang}
          selectedSkill={selectedSkill}
          isFetchingSkill={isFetchingSkill}
          workspace={workspace}
          selectedFilePath={selectedFilePath}
          selectedWorkspaceFile={selectedWorkspaceFile}
          selectedFileDetail={selectedFileDetail}
          editorValue={editorValue}
          workspaceErrors={workspaceErrors}
          workspaceWarnings={workspaceWarnings}
          isEditorDirty={isEditorDirty}
          isFetchingWorkspace={isFetchingWorkspace}
          isFetchingFile={isFetchingFile}
          isSavingFile={updateFileMutation.isPending}
          isDeletingFile={deleteFileMutation.isPending}
          canEditSkill={canEditSkill}
          canEditSelectedFile={canEditSelectedFile}
          shareUsers={shareUsers}
          skillSettingsDraft={skillSettingsDraft}
          skillAccessDraft={skillAccessDraft}
          canShareSkill={canShareSkill}
          isSavingSettings={updateSkillSettingsMutation.isPending}
          isSavingAccess={updateSkillAccessMutation.isPending}
          setSkillSettingsDraft={setSkillSettingsDraft}
          setSkillAccessDraft={setSkillAccessDraft}
          onBack={() => setSelectedSlug("")}
          onCreateFile={() => setCreateFileOpen(true)}
          onSaveFile={saveCurrentFile}
          onRemoveFile={removeCurrentFile}
          onSelectFile={setSelectedFilePath}
          onEditorValueChange={setEditorValue}
          onSaveSettings={saveSkillSettings}
          onSaveAccess={() => updateSkillAccessMutation.mutate()}
        />
      )}

      <CreateSkillDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        tr={tr}
        lang={lang}
        templates={templates}
        selectedTemplate={selectedTemplate}
        selectedTemplateSlug={selectedTemplateSlug}
        wizard={wizard}
        slugTouched={slugTouched}
        canSubmitWizard={canSubmitWizard}
        starterFilesCount={starterFiles.length}
        isPending={scaffoldMutation.isPending}
        setSelectedTemplateSlug={setSelectedTemplateSlug}
        setWizard={setWizard}
        setSlugTouched={setSlugTouched}
        onSubmit={submitWizard}
      />

      <CreateFileDialog
        open={createFileOpen}
        onOpenChange={setCreateFileOpen}
        tr={tr}
        path={createFilePath}
        content={createFileContent}
        canEditSkill={canEditSkill}
        isPending={createFileMutation.isPending}
        onPathChange={setCreateFilePath}
        onContentChange={setCreateFileContent}
        onCreate={(path, content) => createFileMutation.mutate({ path, content })}
      />

      <SkillValidationDialog
        open={validateOpen}
        onOpenChange={setValidateOpen}
        tr={tr}
        strictValidation={strictValidation}
        isPending={validateMutation.isPending}
        report={validationReport}
        onStrictValidationChange={setStrictValidation}
        onValidate={() => validateMutation.mutate()}
      />
    </div>
  );
}
