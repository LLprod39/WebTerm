import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, Info, Puzzle, Trash2, X } from "lucide-react";

import { AgentNodePanel } from "@/components/pipeline/node-panel/AgentNodePanel";
import { type NodeType } from "@/components/pipeline/nodes";
import { getNodeTypeGuidance, getNodeTypeInfo } from "@/components/pipeline/nodes/nodeMeta";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  fetchModels,
  refreshModels,
  studioAgents,
  studioMCP,
  studioServers,
  studioSkills,
  type MCPServerInspection,
  type MCPServerTool,
  type ModelsResponse,
  type PipelineNode,
  type StudioCapabilityNode,
  type PipelineTrigger,
} from "@/lib/api";
import { isPluginStudioNode, pluginNodeDescription, pluginNodeLabel } from "@/plugins/studioNodes";

import { NodeFormSection } from "./PanelPrimitives";
import { TriggerBasicFields, TriggerSpecificConfigSections } from "./TriggerConfigSections";
import {
  coerceSchemaFormValue,
  getSchemaProperties,
  getSchemaRequiredFields,
  parseJsonObjectText,
  toJsonEditorText,
} from "./jsonSchemaUtils";
import {
  AGENT_PROVIDER_OPTIONS,
  MCP_MUTATING_TOOL_RE,
  getModelsForProvider,
  isModelProvider,
} from "./pipelineGraphUtils";
import { NODE_TYPE_LOOKUP, localize } from "./presentation";
import { LlmQueryConfig, SshCommandConfig } from "./node-config/AgentConfigSections";
import { LogicConfigSections } from "./node-config/LogicConfigSections";
import { McpCallConfigSection } from "./node-config/McpCallConfigSection";
import { OpsConfigSections } from "./node-config/OpsConfigSections";
import { OutputConfigSections } from "./node-config/OutputConfigSections";
import { PluginSchemaConfigSection } from "./node-config/PluginSchemaConfigSection";

export function NodeConfigPanel({
  node,
  nodeManifests,
  pipelineId,
  trigger,
  lang,
  onUpdate,
  onClose,
  onDelete,
  onDuplicate,
}: {
  node: PipelineNode;
  nodeManifests: StudioCapabilityNode[];
  pipelineId: number | null;
  trigger?: PipelineTrigger | null;
  lang?: "en" | "ru";
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onClose: () => void;
  onDelete: (id: string) => void;
  onDuplicate: (id: string) => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: agents = [] } = useQuery({ queryKey: ["studio", "agents"], queryFn: studioAgents.list });
  const { data: servers = [] } = useQuery({ queryKey: ["studio", "servers"], queryFn: studioServers.list });
  const { data: mcpList = [] } = useQuery({ queryKey: ["studio", "mcp"], queryFn: studioMCP.list });
  const { data: skillList = [] } = useQuery({ queryKey: ["studio", "skills"], queryFn: studioSkills.list });
  const { data: modelsData } = useQuery({ queryKey: ["api", "models"], queryFn: fetchModels });
  const [d, setD] = useState<Record<string, unknown>>(node.data || {});
  const [loadingModelsFor, setLoadingModelsFor] = useState<string | null>(null);
  const [webhookMapText, setWebhookMapText] = useState(() => toJsonEditorText(node.data?.webhook_payload_map));
  const [mcpArgsText, setMcpArgsText] = useState(
    () => (typeof node.data?.arguments_text === "string" ? String(node.data.arguments_text) : toJsonEditorText(node.data?.arguments || {})),
  );
  const uiLang: "en" | "ru" = lang === "ru" ? "ru" : "en";
  const activeManifest = useMemo(
    () => nodeManifests.find((manifest) => manifest.type === node.type),
    [node.type, nodeManifests],
  );
  const isPluginNode = isPluginStudioNode(activeManifest);
  const pluginManifest = isPluginNode ? activeManifest : undefined;

  const set = useCallback((key: string, val: unknown) => {
    setD((prev) => {
      const next = { ...prev, [key]: val };
      onUpdate(node.id, next);
      return next;
    });
  }, [node.id, onUpdate]);

  const setMany = useCallback((patch: Record<string, unknown>) => {
    setD((prev) => {
      const next = { ...prev, ...patch };
      onUpdate(node.id, next);
      return next;
    });
  }, [node.id, onUpdate]);

  const setMonitoringFilters = useCallback((patch: Record<string, unknown>) => {
    setD((prev) => {
      const next = { ...prev, ...patch } as Record<string, unknown>;
      const monitoringFilters: Record<string, unknown> = {};

      if (Array.isArray(next.server_ids) && next.server_ids.length) monitoringFilters.server_ids = next.server_ids;
      if (Array.isArray(next.severities) && next.severities.length) monitoringFilters.severities = next.severities;
      if (Array.isArray(next.alert_types) && next.alert_types.length) monitoringFilters.alert_types = next.alert_types;
      if (Array.isArray(next.container_names) && next.container_names.length) monitoringFilters.container_names = next.container_names;
      if (String(next.match_text || "").trim()) monitoringFilters.match_text = String(next.match_text || "").trim();

      next.monitoring_filters = monitoringFilters;
      onUpdate(node.id, next);
      return next;
    });
  }, [node.id, onUpdate]);

  const type = node.type as NodeType;
  const provider =
    type === "agent/llm_query"
      ? ((d.provider as string) || "gemini")
      : type === "agent/react" || type === "agent/multi"
        ? ((d.provider as string) || "auto")
        : "";
  const currentModel = (d.model as string) || "";
  const modelProvider = provider && provider !== "auto" ? provider : "";
  const modelList = useMemo(() => getModelsForProvider(modelsData, modelProvider), [modelProvider, modelsData]);
  const selectedAgent = agents.find((agent) => String(agent.id) === String(d.agent_config_id || ""));
  const selectedMcpId = d.mcp_server_id ? Number(d.mcp_server_id) : null;
  const selectedMcp = mcpList.find((mcp) => mcp.id === selectedMcpId) || null;
  const selectedSkillSlugs = Array.isArray(d.skill_slugs) ? (d.skill_slugs as string[]) : [];
  const selectedSkills = skillList.filter((skill) => selectedSkillSlugs.includes(skill.slug));
  const mcpArgsState = parseJsonObjectText(mcpArgsText);

  useEffect(() => {
    setD(node.data || {});
    setWebhookMapText(toJsonEditorText(node.data?.webhook_payload_map));
    setMcpArgsText(
      typeof node.data?.arguments_text === "string"
        ? String(node.data.arguments_text)
        : toJsonEditorText(node.data?.arguments || {}),
    );
    setLoadingModelsFor(null);
  }, [node.id, node.data]);

  const { data: mcpInspection, isFetching: isFetchingMcpTools } = useQuery({
    queryKey: ["studio", "mcp", selectedMcpId, "tools"],
    queryFn: () => studioMCP.tools(selectedMcpId as number),
    enabled: type === "agent/mcp_call" && !!selectedMcpId,
  });
  const mcpTools = (mcpInspection as MCPServerInspection | undefined)?.tools || [];
  const selectedToolName = String(d.tool_name || "");
  const embeddedInputSchema =
    d.input_schema && typeof d.input_schema === "object" && !Array.isArray(d.input_schema)
      ? (d.input_schema as Record<string, unknown>)
      : undefined;
  const embeddedTool: MCPServerTool | null =
    selectedToolName && embeddedInputSchema
      ? {
          name: selectedToolName,
          description: typeof d.tool_description === "string" ? d.tool_description : "",
          inputSchema: embeddedInputSchema,
        }
      : null;
  const selectedTool = mcpTools.find((tool) => tool.name === selectedToolName) || embeddedTool;
  const selectedToolProperties = useMemo(() => getSchemaProperties(selectedTool?.inputSchema), [selectedTool]);
  const selectedToolRequiredFields = useMemo(() => getSchemaRequiredFields(selectedTool?.inputSchema), [selectedTool]);
  const mcpArgsForForm = mcpArgsState.value || {};
  const mcpLooksMutating = MCP_MUTATING_TOOL_RE.test(selectedToolName);
  const mcpRiskReasons = useMemo(() => {
    const reasons: string[] = [];
    if (mcpLooksMutating) {
      reasons.push(localize(uiLang, "Имя инструмента похоже на изменение состояния.", "Tool name looks like a state-changing action."));
    }
    if (selectedMcp?.last_test_ok === false) {
      reasons.push(localize(uiLang, "Последняя проверка MCP-сервера завершилась ошибкой.", "Last MCP server test failed."));
    }
    if (mcpLooksMutating && selectedSkillSlugs.length === 0) {
      reasons.push(localize(uiLang, "Для mutating вызова лучше привязать skill/policy.", "Attach a skill/policy for mutating calls."));
    }
    if (!reasons.length) {
      reasons.push(localize(uiLang, "Риск низкий или неизвестный. Проверьте схему инструмента и аргументы.", "Read-only or unknown risk. Review the tool schema and arguments."));
    }
    return reasons;
  }, [mcpLooksMutating, selectedMcp?.last_test_ok, selectedSkillSlugs.length, uiLang]);

  const setMcpArgument = useCallback((key: string, property: Record<string, unknown>, rawValue: string | boolean) => {
    const parsed = parseJsonObjectText(mcpArgsText);
    const base = parsed.value || {};
    const nextArgs = { ...base, [key]: coerceSchemaFormValue(rawValue, property) };
    const text = JSON.stringify(nextArgs, null, 2);
    setMcpArgsText(text);
    setMany({ arguments_text: text, arguments: nextArgs });
  }, [mcpArgsText, setMany]);

  const providerRef = useRef(provider);
  useEffect(() => {
    providerRef.current = provider;
  }, [provider]);

  useEffect(() => {
    if (!(type === "agent/llm_query" || type === "agent/react" || type === "agent/multi") || !modelProvider || !modelList.length) return;
    if (currentModel && !modelList.includes(currentModel)) set("model", modelList[0]);
  }, [currentModel, modelList, modelProvider, set, type]);

  useEffect(() => {
    if (!(type === "agent/llm_query" || type === "agent/react" || type === "agent/multi") || !modelProvider || loadingModelsFor !== null) return;
    const list = getModelsForProvider(modelsData, modelProvider);
    if (list.length > 0 || !isModelProvider(modelProvider)) return;
    const prov = modelProvider;
    setLoadingModelsFor(prov);
    refreshModels(prov)
      .then((res) => {
        queryClient.setQueryData(["api", "models"], (old: ModelsResponse | undefined) => ({
          ...(old ?? {}),
          [prov]: res.models,
        }));
        if (res.models.length && providerRef.current === prov) {
          setD((prev) => {
            const next = { ...prev, provider: prov, model: res.models[0] };
            onUpdate(node.id, next);
            return next;
          });
        }
      })
      .finally(() => setLoadingModelsFor(null));
  }, [loadingModelsFor, modelProvider, modelsData, node.id, onUpdate, queryClient, type]);

  const typeInfo = isPluginNode
    ? { label: pluginNodeLabel(pluginManifest as StudioCapabilityNode) }
    : getNodeTypeInfo(type, uiLang);
  const TypeIcon = NODE_TYPE_LOOKUP[type as NodeType]?.icon || (isPluginNode ? Puzzle : undefined);
  const typeIconClassName = NODE_TYPE_LOOKUP[type as NodeType]?.iconClassName || (isPluginNode ? "text-teal-400" : "text-foreground");
  const nodeGuidance = isPluginNode
    ? {
        category: localize(uiLang, "Плагин", "Plugin"),
        summary: pluginNodeDescription(pluginManifest as StudioCapabilityNode),
        checklist: [
          localize(uiLang, "Проверьте grants и secret bindings плагина перед запуском.", "Review plugin grants and secret bindings before running."),
        ],
      }
    : getNodeTypeGuidance(type, uiLang);
  const triggerWebhookUrl = trigger?.webhook_url ? new URL(trigger.webhook_url, window.location.origin).toString() : "";
  const handleAgentProviderChange = useCallback((nextProvider: string) => {
    if (nextProvider === "auto") {
      setMany({ provider: "auto", model: "" });
      return;
    }
    if (!isModelProvider(nextProvider)) return;

    set("provider", nextProvider);
    setLoadingModelsFor(nextProvider);
    refreshModels(nextProvider)
      .then((res) => {
        queryClient.setQueryData(["api", "models"], (old: Record<string, unknown> | undefined) => ({
          ...(old ?? {}),
          [nextProvider]: res.models,
        }));
        if (res.models.length && providerRef.current === nextProvider) {
          setMany({ provider: nextProvider, model: res.models[0] });
        }
      })
      .finally(() => setLoadingModelsFor(null));
  }, [queryClient, set, setMany]);

  const agentProviderOptions = useMemo(
    () =>
      AGENT_PROVIDER_OPTIONS.map((item) => {
        if (item.value === "auto") {
          return {
            value: item.value,
            label: item.label,
            modelLabel: localize(uiLang, "Глобальная модель агента", "Workspace default agent model"),
            hint: localize(uiLang, "Берётся из системного дефолта", "Uses the workspace default"),
          };
        }

        const availableModels = getModelsForProvider(modelsData, item.value);
        const modelLabel =
          loadingModelsFor === item.value
            ? localize(uiLang, "Загрузка моделей...", "Loading models...")
            : provider === item.value
              ? currentModel || availableModels[0] || localize(uiLang, "Модели недоступны", "No models available")
              : availableModels[0] || localize(uiLang, "Нажмите, чтобы загрузить", "Click to load");

        return {
          value: item.value,
          label: item.label,
          modelLabel,
          hint:
            provider === item.value
              ? localize(uiLang, "Активный провайдер", "Active provider")
              : localize(uiLang, "Доступно для выбора", "Available to select"),
        };
      }),
    [currentModel, loadingModelsFor, modelsData, provider, uiLang],
  );

  if (type === "agent/react" || type === "agent/multi") {
    const displayLabel = typeof d.label === "string" && d.label.trim() ? d.label.trim() : typeInfo.label;

    return (
      <AgentNodePanel
        lang={uiLang}
        node={node}
        data={d}
        title={displayLabel}
        breadcrumb={`${nodeGuidance.category} / ${typeInfo.label}`}
        guidanceSummary={nodeGuidance.summary}
        guidanceChecklist={nodeGuidance.checklist}
        icon={TypeIcon ? <TypeIcon className={`h-5 w-5 ${typeIconClassName}`} /> : <span className="text-xs font-semibold text-foreground">#</span>}
        agents={agents}
        selectedAgent={selectedAgent}
        provider={provider || "auto"}
        providerOptions={agentProviderOptions}
        modelList={modelList}
        loadingModelsFor={loadingModelsFor}
        mcpList={mcpList}
        servers={servers}
        skillList={skillList}
        selectedSkillSlugs={selectedSkillSlugs}
        selectedSkills={selectedSkills}
        onSet={set}
        onSetMany={setMany}
        onProviderChange={handleAgentProviderChange}
        onClose={onClose}
        onDuplicate={() => onDuplicate(node.id)}
        onDelete={() => onDelete(node.id)}
        onBrowseCatalog={() => navigate("/studio/skills")}
      />
    );
  }

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-start gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-border/70 bg-background/70">
            {TypeIcon ? <TypeIcon className={`h-4 w-4 ${typeIconClassName}`} /> : <span className="text-xs">#</span>}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">{(d.label as string) || typeInfo.label}</p>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {nodeGuidance.category} / {typeInfo.label} · {node.id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" className="h-7 w-7" title={localize(uiLang, "Дублировать ноду", "Duplicate node")} onClick={() => onDuplicate(node.id)}>
            <Copy className="h-3.5 w-3.5" />
          </Button>
          <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive" title={localize(uiLang, "Удалить ноду", "Delete node")} onClick={() => onDelete(node.id)}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button size="icon" variant="ghost" className="h-7 w-7" title={localize(uiLang, "Закрыть", "Close")} onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        <section className="rounded-xl border border-primary/15 bg-primary/5 px-3 py-3">
          <div className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <div className="min-w-0">
              <p className="text-xs font-semibold text-foreground">{localize(uiLang, "Что делает эта нода", "What this node does")}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{nodeGuidance.summary}</p>
            </div>
          </div>
          {nodeGuidance.checklist.length ? (
            <div className="mt-3 space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {localize(uiLang, "Нужно настроить", "Required setup")}
              </p>
              {nodeGuidance.checklist.map((item) => (
                <div key={item} className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          ) : null}
        </section>

        <NodeFormSection
          title={localize(uiLang, "Основное", "Basic")}
          description={localize(uiLang, "Название и базовое поведение шага на схеме.", "Name and basic behavior for this graph step.")}
        >
          <div className="space-y-1.5">
            <Label className="text-xs">{localize(uiLang, "Название в схеме", "Node label")}</Label>
            <Input
              value={(d.label as string) || ""}
              onChange={(event) => set("label", event.target.value)}
              placeholder={localize(uiLang, "Например: Проверить alert", "Example: Check alert")}
              className="h-8 text-xs"
            />
          </div>
          <TriggerBasicFields type={type} data={d} lang={uiLang} onSet={set} />
        </NodeFormSection>

        {isPluginNode ? (
          <PluginSchemaConfigSection
            data={d}
            inputSchema={activeManifest?.input_schema}
            lang={uiLang}
            onSet={set}
          />
        ) : null}

        <TriggerSpecificConfigSections
          type={type}
          data={d}
          pipelineId={pipelineId}
          trigger={trigger}
          triggerWebhookUrl={triggerWebhookUrl}
          webhookMapText={webhookMapText}
          servers={servers}
          lang={uiLang}
          onSet={set}
          onSetMonitoringFilters={setMonitoringFilters}
          onWebhookMapTextChange={setWebhookMapText}
        />
        <SshCommandConfig type={type} data={d} servers={servers} lang={uiLang} onSet={set} />
        <OpsConfigSections type={type} data={d} servers={servers} lang={uiLang} onSet={set} />
        <LogicConfigSections type={type} data={d} lang={uiLang} onSet={set} />
        <OutputConfigSections type={type} data={d} lang={uiLang} onSet={set} />
        <LlmQueryConfig
          type={type}
          data={d}
          lang={uiLang}
          nodeId={node.id}
          provider={provider}
          modelList={modelList}
          loadingModelsFor={loadingModelsFor}
          onSet={set}
          onProviderChange={handleAgentProviderChange}
        />
        <McpCallConfigSection
          type={type}
          data={d}
          lang={uiLang}
          selectedMcpId={selectedMcpId}
          selectedMcp={selectedMcp}
          mcpList={mcpList}
          mcpTools={mcpTools}
          isFetchingMcpTools={isFetchingMcpTools}
          selectedTool={selectedTool}
          selectedToolProperties={selectedToolProperties}
          selectedToolRequiredFields={selectedToolRequiredFields}
          mcpArgsForForm={mcpArgsForForm}
          mcpArgsText={mcpArgsText}
          mcpArgsError={mcpArgsState.error}
          mcpLooksMutating={mcpLooksMutating}
          mcpRiskReasons={mcpRiskReasons}
          skillList={skillList}
          selectedSkillSlugs={selectedSkillSlugs}
          selectedSkills={selectedSkills}
          onSet={set}
          onSetMany={setMany}
          onMcpArgsTextChange={setMcpArgsText}
          onSetMcpArgument={setMcpArgument}
          onBrowseCatalog={() => navigate("/studio/skills")}
        />
      </div>
    </div>
  );
}
