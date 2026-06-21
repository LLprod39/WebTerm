import { Layers, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { FrontendGroup, ServerGroupRole } from "@/lib/api";

import { jsonText } from "./rules";
import type { ServerRulesController } from "./useServerRulesController";

type ManageableGroup = FrontendGroup & { id: number; role: ServerGroupRole };
type Translate = (key: string) => string;
type TranslateWithVars = (key: string, vars?: Record<string, string | number>) => string;

interface ServerRulesTabProps {
  controller: ServerRulesController;
  manageableGroups: ManageableGroup[];
  t: Translate;
  tr: TranslateWithVars;
}

export function ServerRulesTab({
  controller,
  manageableGroups,
  t,
  tr,
}: ServerRulesTabProps) {
  const {
  effectiveGroupEnvironment,
  effectiveGroupForbidden,
  globalEnvJson,
  globalForbidden,
  globalForbiddenLines,
  globalRequired,
  globalRequiredLines,
  globalRules,
  globalRulesPreview,
  groupEnvJson,
  groupForbidden,
  groupRules,
  groupRulesPreview,
  onSaveGlobalContext,
  onSaveGroupContext,
  parsedGlobalEnvironment,
  parsedGroupEnvironment,
  rulesGroupId,
  rulesLoading,
  rulesScopeTab,
  selectGlobalRules,
  selectGroupRules,
  selectedRulesGroup,
  setGlobalEnvJson,
  setGlobalForbidden,
  setGlobalRequired,
  setGlobalRules,
  setGroupEnvJson,
  setGroupForbidden,
  setGroupRules,
  setRulesScopeTab,
  } = controller;

  return (
    <section className="bg-card border border-border rounded-lg p-5 space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{t("srv.rules_tab")}</h2>
          <p className="text-xs text-muted-foreground mt-1">{t("srv.rules_intro")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center rounded-full border border-border px-2 py-1 font-medium text-foreground">{t("srv.rules_global_badge")}</span>
          <span className="inline-flex items-center rounded-full border border-border px-2 py-1 font-medium text-foreground">{t("srv.rules_group_badge")}</span>
          <span className="inline-flex items-center rounded-full border border-border px-2 py-1 font-medium text-foreground">{t("srv.rules_server_badge")}</span>
        </div>
      </div>

      <Tabs
        value={rulesScopeTab}
        onValueChange={(value) => {
          if (value === "group") setRulesScopeTab("group");
          else selectGlobalRules();
        }}
        className="space-y-4"
      >
        <TabsList className="w-full justify-start">
          <TabsTrigger value="global" className="gap-2">
            <Settings className="h-4 w-4" /> {t("srv.rules_scope_global")}
          </TabsTrigger>
          <TabsTrigger value="group" className="gap-2">
            <Layers className="h-4 w-4" /> {t("srv.rules_scope_group")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="global" className="mt-0">
          {rulesLoading ? (
            <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("loading")}</div>
          ) : (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
              <div className="space-y-4 rounded-lg border border-border p-4">
                <div>
                  <div className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">{t("srv.scope_global")}</div>
                  <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.rules_default_instructions")}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{t("srv.rules_global_help")}</p>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_field_rules")}</Label>
                  <Textarea
                    className="min-h-28 bg-secondary/50 text-sm"
                    value={globalRules}
                    onChange={(event) => setGlobalRules(event.target.value)}
                    placeholder={t("srv.rules_placeholder_global")}
                  />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                    <Textarea
                      className="min-h-24 bg-secondary/50 text-sm font-mono"
                      value={globalForbidden}
                      onChange={(event) => setGlobalForbidden(event.target.value)}
                      placeholder={t("srv.rules_placeholder_forbidden")}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{t("srv.rules_field_checks")}</Label>
                    <Textarea
                      className="min-h-24 bg-secondary/50 text-sm font-mono"
                      value={globalRequired}
                      onChange={(event) => setGlobalRequired(event.target.value)}
                      placeholder={t("srv.rules_placeholder_checks")}
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_field_env")}</Label>
                  <Textarea
                    className="min-h-20 bg-secondary/50 text-sm font-mono"
                    value={globalEnvJson}
                    onChange={(event) => setGlobalEnvJson(event.target.value)}
                    placeholder={t("srv.rules_placeholder_env")}
                  />
                  {parsedGlobalEnvironment.error && (
                    <p className="text-xs text-destructive">{parsedGlobalEnvironment.error}</p>
                  )}
                </div>
                <div className="flex justify-end">
                  <Button size="sm" className="h-8 px-4" onClick={() => void onSaveGlobalContext()}>
                    {t("srv.save_global")}
                  </Button>
                </div>
              </div>

              <div className="space-y-4 rounded-lg border border-border bg-secondary/10 p-4">
                <div>
                  <div className="inline-flex items-center rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-foreground">{t("srv.rules_preview_global_badge")}</div>
                  <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.rules_preview_global_title")}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{t("srv.rules_preview_global_help")}</p>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_field_stack")}</Label>
                  <Textarea className="min-h-44 bg-background text-sm" value={globalRulesPreview} readOnly />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                  <Textarea className="min-h-20 bg-background text-xs font-mono" value={globalForbiddenLines.join("\n") || t("srv.none")} readOnly />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_field_checks")}</Label>
                  <Textarea className="min-h-20 bg-background text-xs font-mono" value={globalRequiredLines.join("\n") || t("srv.none")} readOnly />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.environment")}</Label>
                  <Textarea className="min-h-24 bg-background text-xs font-mono" value={jsonText(parsedGlobalEnvironment.value)} readOnly />
                </div>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="group" className="mt-0">
          {!manageableGroups.length ? (
            <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
              {t("srv.rules_group_empty")}
            </div>
          ) : rulesLoading ? (
            <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("loading")}</div>
          ) : (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
              <div className="space-y-4 rounded-lg border border-border p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">{t("srv.scope_group")}</div>
                    <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.rules_group_title")}</h3>
                    <p className="text-xs text-muted-foreground mt-1">{t("srv.rules_group_help")}</p>
                  </div>
                  <div className="min-w-[220px] space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{t("srv.rules_group_select")}</Label>
                    <Select
                      value={rulesGroupId ? String(rulesGroupId) : undefined}
                      onValueChange={(value) => selectGroupRules(Number(value))}
                    >
                      <SelectTrigger className="h-9 bg-secondary/50" aria-label={t("srv.rules_group_select")}>
                        <SelectValue placeholder={t("srv.selected_group")} />
                      </SelectTrigger>
                      <SelectContent>
                        {manageableGroups.map((group) => (
                          <SelectItem key={group.id} value={String(group.id)}>
                            {group.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_field_rules")}</Label>
                  <Textarea
                    className="min-h-28 bg-secondary/50 text-sm"
                    value={groupRules}
                    onChange={(event) => setGroupRules(event.target.value)}
                    placeholder={t("srv.rules_placeholder_group")}
                  />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                    <Textarea
                      className="min-h-24 bg-secondary/50 text-sm font-mono"
                      value={groupForbidden}
                      onChange={(event) => setGroupForbidden(event.target.value)}
                      placeholder={t("srv.rules_placeholder_group_command")}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{t("srv.rules_field_env")}</Label>
                    <Textarea
                      className="min-h-24 bg-secondary/50 text-sm font-mono"
                      value={groupEnvJson}
                      onChange={(event) => setGroupEnvJson(event.target.value)}
                      placeholder={t("srv.rules_placeholder_group_env")}
                    />
                    {parsedGroupEnvironment.error && (
                      <p className="text-xs text-destructive">{parsedGroupEnvironment.error}</p>
                    )}
                  </div>
                </div>
                <div className="flex justify-end">
                  <Button size="sm" className="h-8 px-4" onClick={() => void onSaveGroupContext()} disabled={!rulesGroupId}>
                    {t("srv.save_group")}
                  </Button>
                </div>
              </div>

              <div className="space-y-4 rounded-lg border border-border bg-secondary/10 p-4">
                <div>
                  <div className="inline-flex items-center rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-foreground">
                    {t("srv.rules_preview_group_badge")}
                  </div>
                  <h3 className="mt-3 text-sm font-semibold text-foreground">
                    {tr("srv.rules_preview_group_title", { name: selectedRulesGroup?.name || t("srv.selected_group") })}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1">{t("srv.rules_preview_group_help")}</p>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_field_stack")}</Label>
                  <Textarea className="min-h-44 bg-background text-sm" value={groupRulesPreview} readOnly />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                  <Textarea className="min-h-20 bg-background text-xs font-mono" value={effectiveGroupForbidden.join("\n") || t("srv.none")} readOnly />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.rules_required_inherited")}</Label>
                  <Textarea className="min-h-20 bg-background text-xs font-mono" value={globalRequiredLines.join("\n") || t("srv.none")} readOnly />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.environment")}</Label>
                  <Textarea className="min-h-24 bg-background text-xs font-mono" value={jsonText(effectiveGroupEnvironment)} readOnly />
                </div>
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </section>
  );
}
