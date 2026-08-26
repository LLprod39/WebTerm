import { type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Cpu, BookOpen } from "lucide-react";

import { fetchAuthSession, type AgentConfig, type MCPServer, type StudioSkill } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";

import { IterationStepper } from "./IterationStepper";
import { ProviderSelector } from "./ProviderSelector";
import { ServerTagsInput } from "./ServerTagsInput";
import {
  clampNumber,
  getSelectedMcpServers,
  SUDO_POLICY_OPTIONS,
  sudoPolicyLabel,
  t,
  type AgentProviderCardOption,
  type NodePanelLang,
  type StudioServerOption,
} from "./shared";

type NodeSettingsTabProps = {
  lang: NodePanelLang;
  data: Record<string, unknown>;
  agents: AgentConfig[];
  selectedAgent: AgentConfig | null;
  provider: string;
  providerOptions: AgentProviderCardOption[];
  modelList: string[];
  loadingModelsFor: string | null;
  canSelectModels?: boolean;
  mcpList: MCPServer[];
  servers: StudioServerOption[];
  selectedSkills: StudioSkill[];
  onSet: (key: string, value: unknown) => void;
  onSetMany: (patch: Record<string, unknown>) => void;
  onProviderChange: (provider: string) => void;
  onOpenPoliciesTab: () => void;
};

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {title}
        </h3>
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      </div>
      {children}
    </section>
  );
}

export function NodeSettingsTab({
  lang,
  data,
  agents,
  selectedAgent,
  provider,
  providerOptions,
  modelList,
  loadingModelsFor,
  canSelectModels = false,
  mcpList,
  servers,
  selectedSkills,
  onSet,
  onSetMany,
  onProviderChange,
  onOpenPoliciesTab,
}: NodeSettingsTabProps) {
  // Model & agent-profile selection is admin-only; regular users inherit the
  // admin's configured model / the workspace default.
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = Boolean(authData?.user?.is_staff);

  const selectedMcpServerIds = Array.isArray(data.mcp_server_ids)
    ? (data.mcp_server_ids as number[])
    : [];
  const selectedMcpServers = getSelectedMcpServers(mcpList, selectedMcpServerIds);
  const selectedServerIds = Array.isArray(data.server_ids)
    ? (data.server_ids as number[])
    : [];
  const maxIterations = clampNumber(Number(data.max_iterations) || 6, 1, 20);
  const sudoPolicy = (data.sudo_policy as string) || "inherit";

  return (
    <div className="space-y-6">
      <Section
        title={t(lang, "Основное", "Basic")}
        description={t(
          lang,
          "Базовая идентификация ноды и способ конфигурации агента.",
          "Core node identity and the way the agent is configured.",
        )}
      >
        <div className="space-y-2">
          <Label htmlFor="node-label" className="text-xs text-muted-foreground">
            {t(lang, "Метка", "Label")}
          </Label>
          <Input
            id="node-label"
            value={(data.label as string) || ""}
            onChange={(event) => onSet("label", event.target.value)}
            placeholder={t(lang, "Например: разбор инцидента", "Example: incident investigation")}
            className="h-10 rounded-lg border-border/70 bg-background/70"
          />
        </div>

        {isAdmin ? (
          <div className="space-y-2">
            <Label htmlFor="agent-config" className="text-xs text-muted-foreground">
              {t(lang, "Конфиг агента", "Agent config")}
            </Label>
            <Select
              value={data.agent_config_id ? String(data.agent_config_id) : "__none__"}
              onValueChange={(value) => {
                if (value === "__none__") {
                  onSetMany({ agent_config_id: null, agent_name: "" });
                  return;
                }
                const agent = agents.find((item) => String(item.id) === value);
                onSetMany({ agent_config_id: value, agent_name: agent?.name || "" });
              }}
            >
              <SelectTrigger id="agent-config" className="h-10 rounded-lg border-border/70 bg-background/70">
                <SelectValue placeholder={t(lang, "Настроить прямо в ноде", "Configure directly in the node")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">
                  {t(lang, "Настроить прямо в ноде", "Configure directly in the node")}
                </SelectItem>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={String(agent.id)}>
                    {agent.icon} {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}

        {selectedAgent ? (
          <div className="rounded-lg border border-border/70 bg-muted/20 px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <p className="text-sm font-semibold text-foreground">{selectedAgent.name}</p>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t(
                    lang,
                    "Используется сохранённый конфиг: локальные поля модели скрыты, а промпты, инструменты и политики берутся из него.",
                    "The saved config controls this node's prompts, model, tools, and attached policies.",
                  )}
                </p>
              </div>
              <Cpu className="mt-0.5 h-4 w-4 text-muted-foreground" />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant="outline" className="text-xs">
                {selectedAgent.model}
              </Badge>
              <Badge variant="secondary" className="text-xs">
                {selectedAgent.max_iterations} iter
              </Badge>
              {selectedAgent.mcp_servers?.length ? (
                <Badge variant="secondary" className="text-xs">
                  {selectedAgent.mcp_servers.length} MCP
                </Badge>
              ) : null}
              <Badge variant="outline" className="text-xs">
                sudo: {sudoPolicyLabel(selectedAgent.sudo_policy, lang)}
              </Badge>
              {selectedAgent.skills?.length ? (
                <Badge variant="secondary" className="text-xs">
                  {selectedAgent.skills.length} skills
                </Badge>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="space-y-2">
          <Label htmlFor="on-failure" className="text-xs text-muted-foreground">
            {t(lang, "При ошибке", "On failure")}
          </Label>
          <Select
            value={(data.on_failure as string) || "abort"}
            onValueChange={(value) => onSet("on_failure", value)}
          >
            <SelectTrigger id="on-failure" className="h-10 rounded-lg border-border/70 bg-background/70">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="abort">{t(lang, "Остановить pipeline", "Abort pipeline")}</SelectItem>
              <SelectItem value="continue">{t(lang, "Продолжить", "Continue")}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="sudo-policy" className="text-xs text-muted-foreground">
            {t(lang, "Контролируемый sudo", "Controlled sudo")}
          </Label>
          <Select value={sudoPolicy} onValueChange={(value) => onSet("sudo_policy", value)}>
            <SelectTrigger id="sudo-policy" className="h-10 rounded-lg border-border/70 bg-background/70">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SUDO_POLICY_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {t(lang, option.labelRu, option.labelEn)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t(
              lang,
              SUDO_POLICY_OPTIONS.find((option) => option.value === sudoPolicy)?.hintRu || "Команды с sudo будут заблокированы.",
              SUDO_POLICY_OPTIONS.find((option) => option.value === sudoPolicy)?.hintEn || "Commands with sudo are blocked.",
            )}
          </p>
        </div>
      </Section>

      <Separator />

      <Section
        title={t(lang, "Модель", "Model")}
        description={t(
          lang,
          "Провайдер, модель исполнения и лимит шагов для текущей ноды.",
          "Execution provider, model selection, and step budget for this node.",
        )}
      >
        {selectedAgent ? (
          <div className="rounded-lg border border-dashed border-border/70 px-4 py-4 text-sm text-muted-foreground">
            {t(
              lang,
              "Используется сохранённый конфиг агента. Локальные поля модели скрыты, чтобы не было двух источников настроек.",
              "Model settings come from the selected Agent Config. Clear that binding if you want to manage them directly in the node.",
            )}
          </div>
        ) : !canSelectModels || !isAdmin ? (
          <div className="rounded-lg border border-dashed border-border/70 px-4 py-4 text-sm text-muted-foreground">
            {t(
              lang,
              "Используется глобальная модель агента из настроек. Выбор модели доступен только администратору.",
              "Uses the workspace default agent model from settings. Only admins can choose a model.",
            )}
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                {t(lang, "Провайдер", "Provider")}
              </Label>
              <ProviderSelector
                options={providerOptions}
                value={provider || "auto"}
                onChange={onProviderChange}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="node-model" className="text-xs text-muted-foreground">
                {t(lang, "Модель", "Model")}
              </Label>
              {provider === "auto" ? (
                <div className="flex h-10 items-center rounded-lg border border-border/70 bg-muted/20 px-3 text-sm text-muted-foreground">
                  {t(lang, "Используется глобальная модель агента.", "Uses the workspace default agent model.")}
                </div>
              ) : (
                <Select
                  value={(data.model as string) || ""}
                  onValueChange={(value) => onSet("model", value)}
                  disabled={loadingModelsFor === provider}
                >
                  <SelectTrigger id="node-model" className="h-10 rounded-lg border-border/70 bg-background/70">
                    <SelectValue
                      placeholder={
                        loadingModelsFor === provider
                          ? t(lang, "Загрузка моделей...", "Loading models...")
                          : t(lang, "Выберите модель", "Select a model")
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {modelList.length ? (
                      modelList.map((model) => (
                        <SelectItem key={model} value={model}>
                          {model}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value="_empty" disabled>
                        {t(lang, "Модели недоступны", "No models available")}
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              )}
            </div>
          </>
        )}

        {!selectedAgent ? (
          <>
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                {t(lang, "Максимум шагов", "Max iterations")}
              </Label>
              <IterationStepper
                lang={lang}
                value={maxIterations}
                onChange={(nextValue) => onSet("max_iterations", nextValue)}
              />
            </div>

            {mcpList.length ? (
              <div className="space-y-3">
                <Label className="text-xs text-muted-foreground">
                  {t(lang, "MCP-серверы", "MCP servers")}
                </Label>
                <div className="flex flex-wrap gap-2">
                  {selectedMcpServers.length ? (
                    selectedMcpServers.map((server) => (
                      <div
                        key={server.id}
                        className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/70 px-3 py-1.5 text-xs"
                      >
                        <span className="font-medium text-foreground">{server.name}</span>
                        <span className="text-muted-foreground">{server.transport}</span>
                        <button
                          type="button"
                          onClick={() => onSet("mcp_server_ids", selectedMcpServerIds.filter((id) => id !== server.id))}
                          className="rounded-full p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          aria-label={t(lang, "Удалить MCP сервер", "Remove MCP server")}
                        >
                          <ChevronRight className="h-3 w-3 rotate-45" />
                        </button>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      {t(lang, "MCP серверы ещё не подключены.", "No MCP servers attached yet.")}
                    </p>
                  )}
                </div>
                <Select
                  onValueChange={(value) => {
                    const nextId = Number(value);
                    if (!selectedMcpServerIds.includes(nextId)) {
                      onSet("mcp_server_ids", [...selectedMcpServerIds, nextId]);
                    }
                  }}
                >
                  <SelectTrigger
                    className="h-10 rounded-lg border-dashed border-border/70 bg-background/70"
                    disabled={mcpList.every((server) => selectedMcpServerIds.includes(server.id))}
                  >
                    <SelectValue
                      placeholder={t(lang, "Добавить MCP сервер", "Add MCP server")}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {mcpList
                      .filter((server) => !selectedMcpServerIds.includes(server.id))
                      .map((server) => (
                        <SelectItem key={server.id} value={String(server.id)}>
                          {server.name} ({server.transport})
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </>
        ) : null}
      </Section>

      <Separator />

      <Section
        title={t(lang, "Серверы", "Servers")}
        description={t(
          lang,
          "Серверы, которые будут доступны этой ноде во время выполнения.",
          "Servers that this node can target during execution.",
        )}
      >
        <ServerTagsInput
          lang={lang}
          selectedIds={selectedServerIds}
          servers={servers}
          onAdd={(serverId) => {
            if (!selectedServerIds.includes(serverId)) {
              onSet("server_ids", [...selectedServerIds, serverId]);
            }
          }}
          onRemove={(serverId) => onSet("server_ids", selectedServerIds.filter((id) => id !== serverId))}
        />
      </Section>

      <Separator />

      <Section
        title={t(lang, "Политики", "Policies")}
        description={t(
          lang,
          "Краткая сводка по политикам этой ноды и переход в расширенную вкладку.",
          "A compact summary of node-level skills with a shortcut to the detailed policies tab.",
        )}
      >
        <div className="rounded-lg border border-border/70 bg-background/70 px-4 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="text-sm font-semibold text-foreground">
                {selectedSkills.length
                  ? t(lang, `Активно: ${selectedSkills.length}`, `Active: ${selectedSkills.length}`)
                  : t(lang, "Политики не выбраны", "No policies selected")}
              </p>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {selectedAgent
                  ? t(
                      lang,
                      "Политики этой ноды будут объединены с сохранённым конфигом агента.",
                      "Node-level policies will be merged with the saved Agent Config.",
                    )
                  : t(
                      lang,
                      "Выбранные политики дополняют инструкции и ограничения этой ноды.",
                      "Selected policies extend this node's prompts and runtime guardrails.",
                    )}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-9 gap-1.5 rounded-xl"
              onClick={onOpenPoliciesTab}
            >
              <BookOpen className="h-3.5 w-3.5" />
              {t(lang, "Открыть", "Open")}
            </Button>
          </div>

          {selectedSkills.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {selectedSkills.map((skill) => (
                <Badge key={skill.slug} variant="secondary" className="rounded-full px-2.5 py-1 text-xs">
                  {skill.name}
                </Badge>
              ))}
            </div>
          ) : null}
        </div>
      </Section>
    </div>
  );
}
