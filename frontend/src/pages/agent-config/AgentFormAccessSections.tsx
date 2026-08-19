import { BookOpen } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ShareAccessEditor } from "@/components/studio/ShareAccessEditor";
import { Textarea } from "@/components/ui/textarea";
import type { AgentConfig, MCPServer, StudioSharedUser, StudioSkill } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { ALL_TOOLS, MODEL_OPTIONS, SUDO_AGENT_OPTIONS, sudoOption } from "./agentConfigOptions";

type Lang = "ru" | "en";

export function AgentCoreSettingsSection({
  form,
  lang,
  readOnly,
  canSelectModels = false,
  onFieldChange,
  isAdmin = false,
}: {
  form: Partial<AgentConfig>;
  lang: Lang;
  readOnly: boolean;
  canSelectModels?: boolean;
  onFieldChange: (key: keyof AgentConfig, value: unknown) => void;
  /** Model selection is admin-only — regular users inherit the admin's configured model. */
  isAdmin?: boolean;
}) {
  return (
    <>
      <div className="grid gap-4 md:grid-cols-[96px_minmax(0,1fr)]">
        <div className="space-y-2">
          <Label>{localize(lang, "Иконка", "Icon")}</Label>
          <Input
            value={form.icon || "B"}
            onChange={(event) => onFieldChange("icon", event.target.value)}
            className="text-center text-lg"
            disabled={readOnly}
          />
        </div>
        <div className="space-y-2">
          <Label>{localize(lang, "Название", "Name")}</Label>
          <Input
            value={form.name || ""}
            onChange={(event) => onFieldChange("name", event.target.value)}
          placeholder={localize(lang, "OPS-разбор", "Ops triage profile")}
            disabled={readOnly}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>{localize(lang, "Описание", "Description")}</Label>
        <Input
          value={form.description || ""}
          onChange={(event) => onFieldChange("description", event.target.value)}
          placeholder={localize(
            lang,
            "Профиль для проверок инфраструктуры и предложений по ремонту",
            "Profile for infrastructure checks and repair suggestions",
          )}
          disabled={readOnly}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label>{localize(lang, "Модель", "Model")}</Label>
          {canSelectModels && isAdmin ? (
            <Select value={form.model || MODEL_OPTIONS[0]} onValueChange={(value) => onFieldChange("model", value)}>
              <SelectTrigger disabled={readOnly}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODEL_OPTIONS.map((model) => (
                  <SelectItem key={model} value={model}>
                    {model}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <div className="rounded-lg border border-border/70 bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
              <div className="font-mono text-xs text-foreground">
                {form.model || localize(lang, "Модель из настроек", "Workspace default model")}
              </div>
              <p className="mt-1 text-xs leading-relaxed">
                {localize(
                  lang,
                  "Модель задаёт администратор в настройках. Выбор модели недоступен.",
                  "The model is set by an admin in settings. Model selection is not available.",
                )}
              </p>
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Label>{localize(lang, "Лимит итераций", "Max iterations")}</Label>
          <Input
            type="number"
            min={1}
            max={50}
            value={form.max_iterations || 10}
            onChange={(event) => onFieldChange("max_iterations", Number(event.target.value) || 10)}
            disabled={readOnly}
          />
        </div>
      </div>

      <div className="space-y-2 rounded-xl border border-border/70 bg-background/30 px-4 py-3">
        <Label>{localize(lang, "Controlled sudo", "Controlled sudo")}</Label>
        <Select
          value={(form.sudo_policy as string) || "disabled"}
          onValueChange={(value) => onFieldChange("sudo_policy", value)}
        >
          <SelectTrigger disabled={readOnly}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SUDO_AGENT_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {localize(lang, option.labelRu, option.labelEn)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {localize(lang, sudoOption(form.sudo_policy as string).hintRu, sudoOption(form.sudo_policy as string).hintEn)}
        </p>
      </div>

      <div className="space-y-2">
        <Label>{localize(lang, "Системный промпт", "System prompt")}</Label>
        <Textarea
          value={form.system_prompt || ""}
          onChange={(event) => onFieldChange("system_prompt", event.target.value)}
          rows={4}
          placeholder={localize(
            lang,
            "Ты аккуратный OPS-агент. Проверяй контекст перед рискованными действиями.",
            "You are a careful operations agent. Verify before any risky action.",
          )}
          disabled={readOnly}
        />
      </div>

      <div className="space-y-2">
        <Label>{localize(lang, "Инструкции", "Instructions")}</Label>
        <Textarea
          value={form.instructions || ""}
          onChange={(event) => onFieldChange("instructions", event.target.value)}
          rows={4}
          placeholder={localize(
            lang,
            "Сначала собирай контекст. Не выполняй разрушительные команды без явного подтверждения.",
            "Always gather context first. Avoid destructive commands unless explicitly approved.",
          )}
          disabled={readOnly}
        />
      </div>
    </>
  );
}

export function AgentAllowedToolsSection({
  allowedTools,
  lang,
  readOnly,
  onToggleTool,
}: {
  allowedTools: string[];
  lang: Lang;
  readOnly: boolean;
  onToggleTool: (toolId: string) => void;
}) {
  return (
    <div className="space-y-3">
      <Label>{localize(lang, "Разрешённые инструменты", "Allowed tools")}</Label>
      <div className="grid gap-2 md:grid-cols-2">
        {ALL_TOOLS.map((tool) => (
          <label
            key={tool.id}
            className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3 transition-colors hover:bg-background/40"
          >
            <Checkbox
              checked={allowedTools.includes(tool.id)}
              onCheckedChange={() => onToggleTool(tool.id)}
              className="mt-0.5"
              disabled={readOnly}
            />
            <div>
              <div className="text-sm font-medium text-foreground">{localize(lang, tool.labelRu, tool.labelEn)}</div>
              <div className="text-xs text-muted-foreground">{localize(lang, tool.descriptionRu, tool.descriptionEn)}</div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

export function AgentMcpServersSection({
  canUseMcp,
  lang,
  mcpIds,
  mcpList,
  readOnly,
  onToggleMcp,
}: {
  canUseMcp: boolean;
  lang: Lang;
  mcpIds: number[];
  mcpList: MCPServer[];
  readOnly: boolean;
  onToggleMcp: (mcpId: number) => void;
}) {
  if (!canUseMcp || mcpList.length === 0) return null;

  return (
    <div className="space-y-3">
      <Label>{localize(lang, "MCP-серверы", "MCP servers")}</Label>
      <div className="grid gap-2">
        {mcpList.map((mcp) => (
          <label
            key={mcp.id}
            className="flex cursor-pointer items-center gap-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3 transition-colors hover:bg-background/40"
          >
            <Checkbox checked={mcpIds.includes(mcp.id)} onCheckedChange={() => onToggleMcp(mcp.id)} disabled={readOnly} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{mcp.name}</span>
                <Badge variant="outline" className="text-xs font-mono">
                  {mcp.transport}
                </Badge>
                {mcp.last_test_ok === true ? <Badge variant="secondary">OK</Badge> : null}
                {mcp.last_test_ok === false ? <Badge variant="destructive">ERR</Badge> : null}
              </div>
              <div className="text-xs text-muted-foreground">
                {mcp.description || localize(lang, "Описание не заполнено", "No description")}
              </div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

export function AgentSkillsSection({
  canUseSkills,
  lang,
  readOnly,
  selectedSkillSlugs,
  skills,
  onBrowseCatalog,
  onToggleSkill,
}: {
  canUseSkills: boolean;
  lang: Lang;
  readOnly: boolean;
  selectedSkillSlugs: string[];
  skills: StudioSkill[];
  onBrowseCatalog: () => void;
  onToggleSkill: (slug: string) => void;
}) {
  if (!canUseSkills || skills.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Label>{localize(lang, "Skills", "Skills")}</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 gap-1.5 rounded-md px-3 text-xs"
          onClick={onBrowseCatalog}
          disabled={readOnly}
        >
          <BookOpen className="h-3.5 w-3.5" />
          {localize(lang, "Открыть каталог", "Browse catalog")}
        </Button>
      </div>
      <div className="grid gap-2">
        {skills.map((skill) => (
          <label
            key={skill.slug}
            className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3 transition-colors hover:bg-background/40"
          >
            <Checkbox
              checked={selectedSkillSlugs.includes(skill.slug)}
              onCheckedChange={() => onToggleSkill(skill.slug)}
              className="mt-0.5"
              disabled={readOnly}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{skill.name}</span>
                <span className="font-mono text-xs text-muted-foreground">{skill.slug}</span>
                {skill.service ? <span className="text-xs text-muted-foreground">{skill.service}</span> : null}
                {skill.safety_level ? <span className="text-xs text-muted-foreground">{skill.safety_level}</span> : null}
              </div>
              <div className="text-xs text-muted-foreground">{skill.description}</div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

type ScopedServer = {
  id: number;
  name: string;
  host: string;
};

export function AgentServerScopeSection({
  lang,
  readOnly,
  serverScopeIds,
  servers,
  onToggleServerScope,
}: {
  lang: Lang;
  readOnly: boolean;
  serverScopeIds: number[];
  servers: ScopedServer[];
  onToggleServerScope: (serverId: number) => void;
}) {
  if (servers.length === 0) return null;

  return (
    <div className="space-y-3">
      <Label>{localize(lang, "Ограничение по серверам", "Server scope")}</Label>
      <p className="text-xs text-muted-foreground">
        {localize(
          lang,
          "Оставьте пустым, чтобы профиль работал со всеми доступными серверами. Выберите серверы, чтобы жёстко ограничить scope.",
          "Leave empty to allow all accessible servers. Select specific servers to hard-scope this profile.",
        )}
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        {servers.map((server) => (
          <label
            key={server.id}
            className="flex cursor-pointer items-center gap-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3 transition-colors hover:bg-background/40"
          >
            <Checkbox
              checked={serverScopeIds.includes(server.id)}
              onCheckedChange={() => onToggleServerScope(server.id)}
              disabled={readOnly}
            />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-foreground">{server.name}</div>
              <div className="text-xs text-muted-foreground">{server.host}</div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

export function AgentVisibilitySection({
  isAdmin,
  isShared,
  lang,
  readOnly,
  sharedUserIds,
  users,
  onSharedChange,
  onToggleUser,
}: {
  isAdmin: boolean;
  isShared: boolean;
  lang: Lang;
  readOnly: boolean;
  sharedUserIds: number[];
  users: StudioSharedUser[];
  onSharedChange: (value: boolean) => void;
  onToggleUser: (userId: number) => void;
}) {
  if (!isAdmin) return null;

  return (
    <ShareAccessEditor
      title={localize(lang, "Видимость", "Visibility")}
      description={localize(
        lang,
        "Администратор управляет тем, кто может открывать и переиспользовать этот профиль выполнения.",
        "Admin controls who can open and reuse this execution profile.",
      )}
      isShared={isShared}
      sharedUserIds={sharedUserIds}
      users={users}
      disabled={readOnly}
      onSharedChange={onSharedChange}
      onToggleUser={onToggleUser}
    />
  );
}
