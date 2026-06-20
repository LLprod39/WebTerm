import type { Dispatch, SetStateAction } from "react";
import { ArrowLeft, BookMarked, BookOpen, FileCode2, Loader2, Server, Settings2, Shield, ShieldCheck, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type {
  StudioSharedUser,
  StudioSkillDetail,
  StudioSkillWorkspace,
  StudioSkillWorkspaceFile,
  StudioSkillWorkspaceFileDetail,
} from "@/lib/api";

import { SkillMarkdown } from "./SkillCards";
import { SkillSettingsTab, type SkillAccessDraft } from "./SkillSettingsTab";
import { SkillWorkspaceTab } from "./SkillWorkspaceTab";
import { safetyLevelLabel, type SkillSettingsDraft } from "./skillScaffold";

type TranslateFn = (ru: string, en: string) => string;

type SkillDetailViewProps = {
  tr: TranslateFn;
  lang: "ru" | "en";
  selectedSkill?: StudioSkillDetail;
  isFetchingSkill: boolean;
  workspace?: StudioSkillWorkspace;
  selectedFilePath: string;
  selectedWorkspaceFile: StudioSkillWorkspaceFile | null;
  selectedFileDetail?: StudioSkillWorkspaceFileDetail;
  editorValue: string;
  workspaceErrors: string[];
  workspaceWarnings: string[];
  isEditorDirty: boolean;
  isFetchingWorkspace: boolean;
  isFetchingFile: boolean;
  isSavingFile: boolean;
  isDeletingFile: boolean;
  canEditSkill: boolean;
  canEditSelectedFile: boolean;
  shareUsers: StudioSharedUser[];
  skillSettingsDraft: SkillSettingsDraft;
  skillAccessDraft: SkillAccessDraft;
  canShareSkill: boolean;
  isSavingSettings: boolean;
  isSavingAccess: boolean;
  setSkillSettingsDraft: Dispatch<SetStateAction<SkillSettingsDraft>>;
  setSkillAccessDraft: Dispatch<SetStateAction<SkillAccessDraft>>;
  onBack: () => void;
  onCreateFile: () => void;
  onSaveFile: () => void;
  onRemoveFile: () => void;
  onSelectFile: (path: string) => void;
  onEditorValueChange: (value: string) => void;
  onSaveSettings: () => void;
  onSaveAccess: () => void;
};

export function SkillDetailView({
  tr,
  lang,
  selectedSkill,
  isFetchingSkill,
  workspace,
  selectedFilePath,
  selectedWorkspaceFile,
  selectedFileDetail,
  editorValue,
  workspaceErrors,
  workspaceWarnings,
  isEditorDirty,
  isFetchingWorkspace,
  isFetchingFile,
  isSavingFile,
  isDeletingFile,
  canEditSkill,
  canEditSelectedFile,
  shareUsers,
  skillSettingsDraft,
  skillAccessDraft,
  canShareSkill,
  isSavingSettings,
  isSavingAccess,
  setSkillSettingsDraft,
  setSkillAccessDraft,
  onBack,
  onCreateFile,
  onSaveFile,
  onRemoveFile,
  onSelectFile,
  onEditorValueChange,
  onSaveSettings,
  onSaveAccess,
}: SkillDetailViewProps) {
  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-muted/10 relative">
      <div className="px-6 py-3 flex items-center justify-between gap-4 border-b border-border/40 bg-background/70 backdrop-blur-md sticky top-0 z-20 shrink-0 shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} className="h-10 shrink-0 gap-2 rounded-lg text-muted-foreground hover:text-foreground">
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

            <SkillWorkspaceTab
              tr={tr}
              lang={lang}
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
              isSavingFile={isSavingFile}
              isDeletingFile={isDeletingFile}
              canEditSkill={canEditSkill}
              canEditSelectedFile={canEditSelectedFile}
              onCreateFile={onCreateFile}
              onSaveFile={onSaveFile}
              onRemoveFile={onRemoveFile}
              onSelectFile={onSelectFile}
              onEditorValueChange={onEditorValueChange}
            />

            <SkillSettingsTab
              tr={tr}
              lang={lang}
              selectedSkill={selectedSkill}
              workspace={workspace}
              workspaceErrors={workspaceErrors}
              workspaceWarnings={workspaceWarnings}
              shareUsers={shareUsers}
              skillSettingsDraft={skillSettingsDraft}
              skillAccessDraft={skillAccessDraft}
              canEditSkill={canEditSkill}
              canShareSkill={canShareSkill}
              isSavingSettings={isSavingSettings}
              isSavingAccess={isSavingAccess}
              setSkillSettingsDraft={setSkillSettingsDraft}
              setSkillAccessDraft={setSkillAccessDraft}
              onSaveSettings={onSaveSettings}
              onSaveAccess={onSaveAccess}
            />
          </Tabs>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-red-500/80">
            {tr("Ошибка загрузки скилла.", "Error loading skill.")}
          </div>
        )}
      </div>
    </div>
  );
}
