import type { Dispatch, SetStateAction } from "react";
import { BookOpen, Loader2, Save, Settings2, Shield } from "lucide-react";

import { ShareAccessEditor } from "@/components/studio/ShareAccessEditor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { StudioSharedUser, StudioSkillDetail, StudioSkillWorkspace } from "@/lib/api";

import {
  createSkillSettingsDraft,
  SAFETY_LEVELS,
  safetyLevelLabel,
  type SkillSettingsDraft,
} from "./skillScaffold";

type TranslateFn = (ru: string, en: string) => string;

export type SkillAccessDraft = {
  is_shared: boolean;
  shared_user_ids: number[];
};

type SkillSettingsTabProps = {
  tr: TranslateFn;
  lang: "ru" | "en";
  selectedSkill: StudioSkillDetail;
  workspace?: StudioSkillWorkspace;
  workspaceErrors: string[];
  workspaceWarnings: string[];
  shareUsers: StudioSharedUser[];
  skillSettingsDraft: SkillSettingsDraft;
  skillAccessDraft: SkillAccessDraft;
  canEditSkill: boolean;
  canShareSkill: boolean;
  isSavingSettings: boolean;
  isSavingAccess: boolean;
  setSkillSettingsDraft: Dispatch<SetStateAction<SkillSettingsDraft>>;
  setSkillAccessDraft: Dispatch<SetStateAction<SkillAccessDraft>>;
  onSaveSettings: () => void;
  onSaveAccess: () => void;
};

export function SkillSettingsTab({
  tr,
  lang,
  selectedSkill,
  workspace,
  workspaceErrors,
  workspaceWarnings,
  shareUsers,
  skillSettingsDraft,
  skillAccessDraft,
  canEditSkill,
  canShareSkill,
  isSavingSettings,
  isSavingAccess,
  setSkillSettingsDraft,
  setSkillAccessDraft,
  onSaveSettings,
  onSaveAccess,
}: SkillSettingsTabProps) {
  return (
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
                disabled={isSavingSettings}
              >
                {tr("Сбросить", "Reset")}
              </Button>
              <Button
                className="gap-2"
                onClick={onSaveSettings}
                disabled={!canEditSkill || isSavingSettings}
              >
                {isSavingSettings ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
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
                disabled={isSavingAccess}
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
                onClick={onSaveAccess}
                disabled={isSavingAccess}
              >
                {isSavingAccess ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
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
  );
}
