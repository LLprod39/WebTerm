import { BookOpen } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { MCPServer, MCPServerTool, StudioSkill } from "@/lib/api";

import { AdvancedDisclosure, FailureSelect, FieldHint, NodeFormSection } from "../PanelPrimitives";
import {
  buildSchemaTemplate,
  getSchemaFormTextValue,
  getSchemaType,
  parseJsonObjectText,
} from "../jsonSchemaUtils";
import { MCP_PERMISSION_MODE_OPTIONS } from "../pipelineGraphUtils";
import { localize } from "../presentation";
import type { Lang, NodeData, SetNodeData, SetNodePatch } from "./types";

export function McpCallConfigSection({
  type,
  data,
  lang,
  selectedMcpId,
  selectedMcp,
  mcpList,
  mcpTools,
  isFetchingMcpTools,
  selectedTool,
  selectedToolProperties,
  selectedToolRequiredFields,
  mcpArgsForForm,
  mcpArgsText,
  mcpArgsError,
  mcpLooksMutating,
  mcpRiskReasons,
  skillList,
  selectedSkillSlugs,
  selectedSkills,
  onSet,
  onSetMany,
  onMcpArgsTextChange,
  onSetMcpArgument,
  onBrowseCatalog,
}: McpCallConfigProps) {
  if (type !== "agent/mcp_call") return null;

  return (
    <>
      <NodeFormSection
        title={localize(lang, "Исполнение", "Execution")}
        description={localize(lang, "Прямой вызов конкретного MCP-инструмента без выбора со стороны агента.", "Direct MCP tool call without waiting for an agent to choose.")}
      >
        <McpServerSelect
          data={data}
          lang={lang}
          selectedMcpId={selectedMcpId}
          selectedMcp={selectedMcp}
          mcpList={mcpList}
          onSetMany={onSetMany}
          onMcpArgsTextChange={onMcpArgsTextChange}
        />
        <McpToolSelect
          data={data}
          lang={lang}
          selectedMcpId={selectedMcpId}
          mcpTools={mcpTools}
          isFetchingMcpTools={isFetchingMcpTools}
          onSetMany={onSetMany}
          onMcpArgsTextChange={onMcpArgsTextChange}
        />
        {selectedTool && (
          <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 space-y-2">
            {selectedTool.description && <p className="text-xs">{selectedTool.description}</p>}
            {selectedTool.inputSchema && (
              <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-all max-h-40 overflow-auto">
                {JSON.stringify(selectedTool.inputSchema, null, 2)}
              </pre>
            )}
          </div>
        )}
      </NodeFormSection>
      {selectedTool && Object.keys(selectedToolProperties).length > 0 && (
        <TypedMcpArguments
          lang={lang}
          properties={selectedToolProperties}
          requiredFields={selectedToolRequiredFields}
          values={mcpArgsForForm}
          onSetMcpArgument={onSetMcpArgument}
        />
      )}
      <McpPolicySection
        data={data}
        lang={lang}
        selectedMcp={selectedMcp}
        mcpLooksMutating={mcpLooksMutating}
        mcpRiskReasons={mcpRiskReasons}
        skillList={skillList}
        selectedSkillSlugs={selectedSkillSlugs}
        selectedSkills={selectedSkills}
        onSet={onSet}
        onBrowseCatalog={onBrowseCatalog}
      />
      <AdvancedDisclosure title={localize(lang, "Дополнительно", "Advanced")} defaultOpen>
        <div className="space-y-1.5">
          <Label className="text-xs">Arguments (JSON)</Label>
          <Textarea
            value={mcpArgsText}
            onChange={(event) => {
              const value = event.target.value;
              onMcpArgsTextChange(value);
              const parsed = parseJsonObjectText(value);
              if (!parsed.error) onSetMany({ arguments_text: value, arguments: parsed.value || {} });
              else onSetMany({ arguments_text: value, arguments: null });
            }}
            placeholder={'{\n  "path": "{repo_path}"\n}'}
            className="text-xs font-mono resize-none"
            rows={8}
          />
          <FieldHint>
            {localize(lang, "Аргументы поддерживают переменные pipeline вроде", "Arguments support pipeline variables like")} <code>{"{branch}"}</code> {localize(lang, "и", "and")} <code>{"{node_2_output}"}</code>.
          </FieldHint>
          {mcpArgsError && <p className="text-xs text-red-400">{mcpArgsError}</p>}
        </div>
      </AdvancedDisclosure>
      <NodeFormSection title={localize(lang, "Ошибки", "Errors")}>
        <FailureSelect lang={lang} value={(data.on_failure as string) || "abort"} onChange={(value) => onSet("on_failure", value)} />
      </NodeFormSection>
    </>
  );
}

function McpServerSelect({ data, lang, selectedMcpId, selectedMcp, mcpList, onSetMany, onMcpArgsTextChange }: McpServerSelectProps) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">MCP-сервер</Label>
      <Select
        value={selectedMcpId ? String(selectedMcpId) : "__none__"}
        onValueChange={(value) => {
          if (value === "__none__") {
            onSetMany({ mcp_server_id: null, mcp_server_name: "", tool_name: "", tool_description: "", input_schema: null, arguments_text: "{}", arguments: {} });
            onMcpArgsTextChange("{}");
            return;
          }
          const nextMcp = mcpList.find((item) => String(item.id) === value);
          onSetMany({ mcp_server_id: Number(value), mcp_server_name: nextMcp?.name || "", tool_name: "", tool_description: "", input_schema: null });
        }}
      >
        <SelectTrigger className="h-8 text-xs">
          <SelectValue placeholder={localize(lang, "Выберите MCP-сервер...", "Select MCP server...")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">{localize(lang, "Выберите MCP-сервер...", "Select MCP server...")}</SelectItem>
          {mcpList.map((mcp) => (
            <SelectItem key={mcp.id} value={String(mcp.id)}>{mcp.name} ({mcp.transport})</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selectedMcp && (
        <FieldHint>
          {selectedMcp.last_test_ok === true
            ? localize(lang, "Последняя проверка подключения успешна.", "Last connection test passed.")
            : selectedMcp.last_test_ok === false
              ? localize(lang, "Последняя проверка подключения упала.", "Last connection test failed.")
              : localize(lang, "Сервер ещё не проверялся.", "Server has not been tested yet.")}
        </FieldHint>
      )}
    </div>
  );
}

function McpToolSelect({ data, lang, selectedMcpId, mcpTools, isFetchingMcpTools, onSetMany, onMcpArgsTextChange }: McpToolSelectProps) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{localize(lang, "Инструмент", "Tool")}</Label>
      <Select
        value={(data.tool_name as string) || "__none__"}
        onValueChange={(value) => {
          const tool = mcpTools.find((item) => item.name === value);
          if (!tool) {
            onSetMany({ tool_name: "", tool_description: "", input_schema: null });
            return;
          }
          const toolPatch = { tool_name: tool.name, tool_description: tool.description || "", input_schema: tool.inputSchema || null };
          const shouldSeedArgs = !String(data.arguments_text || "").trim() || String(data.arguments_text || "").trim() === "{}";
          if (shouldSeedArgs) {
            const template = buildSchemaTemplate(tool.inputSchema);
            const text = JSON.stringify(template, null, 2);
            onMcpArgsTextChange(text);
            onSetMany({ ...toolPatch, arguments_text: text, arguments: template });
            return;
          }
          onSetMany(toolPatch);
        }}
        disabled={!selectedMcpId || isFetchingMcpTools}
      >
        <SelectTrigger className="h-8 text-xs">
          <SelectValue placeholder={isFetchingMcpTools ? localize(lang, "Загрузка инструментов...", "Loading tools...") : localize(lang, "Выберите инструмент", "Select tool")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__" disabled>{localize(lang, "Выберите инструмент", "Select tool")}</SelectItem>
          {mcpTools.map((tool) => <SelectItem key={tool.name} value={tool.name}>{tool.name}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}

function TypedMcpArguments({ lang, properties, requiredFields, values, onSetMcpArgument }: TypedMcpArgumentsProps) {
  return (
    <NodeFormSection
      title={localize(lang, "Typed arguments", "Typed arguments")}
      description={localize(lang, "Форма собрана из MCP tool schema и синхронизируется с JSON ниже.", "Generated from the MCP tool schema and synced to the JSON editor below.")}
    >
      <div className="grid gap-2">
        {Object.entries(properties).map(([key, property]) => {
          const schemaType = getSchemaType(property);
          const required = requiredFields.has(key);
          const value = values[key];
          const description = typeof property.description === "string" ? property.description : "";
          return (
            <div key={key} className="rounded-lg border border-border/70 bg-background/40 px-3 py-2">
              <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                <Label className="text-xs">{key}</Label>
                {required && <Badge variant="secondary" className="text-xs">required</Badge>}
                <Badge variant="outline" className="text-xs">{schemaType}</Badge>
              </div>
              {schemaType === "boolean" ? (
                <div className="flex items-center gap-2">
                  <Switch checked={Boolean(value)} onCheckedChange={(checked) => onSetMcpArgument(key, property, checked)} />
                  <span className="text-xs text-muted-foreground">{String(Boolean(value))}</span>
                </div>
              ) : schemaType === "array" || schemaType === "object" ? (
                <Textarea value={getSchemaFormTextValue(value, property)} onChange={(event) => onSetMcpArgument(key, property, event.target.value)} className="min-h-20 resize-none font-mono text-xs" />
              ) : (
                <Input type={schemaType === "number" || schemaType === "integer" ? "number" : "text"} value={getSchemaFormTextValue(value, property)} onChange={(event) => onSetMcpArgument(key, property, event.target.value)} placeholder={schemaType === "string" ? `{${key}}` : undefined} className="h-8 text-xs" />
              )}
              {description && <FieldHint>{description}</FieldHint>}
            </div>
          );
        })}
      </div>
    </NodeFormSection>
  );
}

function McpPolicySection({ data, lang, selectedMcp, mcpLooksMutating, mcpRiskReasons, skillList, selectedSkillSlugs, selectedSkills, onSet, onBrowseCatalog }: McpPolicySectionProps) {
  return (
    <NodeFormSection
      title={localize(lang, "Policy and risk", "Policy and risk")}
      description={localize(lang, "Для сервисных изменений привяжите skill/policy и держите подтверждение перед этой нодой.", "For service changes, attach a skill/policy and place approval before this node.")}
    >
      <div className="rounded-lg border border-border/70 bg-background/40 px-3 py-2">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant={mcpLooksMutating ? "secondary" : "outline"} className="text-xs">
            {mcpLooksMutating ? localize(lang, "Review required", "Review required") : localize(lang, "Low/unknown risk", "Low/unknown risk")}
          </Badge>
          {selectedMcp?.last_test_ok === true && <Badge variant="outline" className="text-xs">MCP tested</Badge>}
          {selectedSkillSlugs.length > 0 && <Badge variant="outline" className="text-xs">{selectedSkillSlugs.length} skills</Badge>}
        </div>
        <ul className="space-y-1 text-xs text-muted-foreground">
          {mcpRiskReasons.map((reason) => <li key={reason}>- {reason}</li>)}
        </ul>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Permission mode", "Permission mode")}</Label>
        <Select value={(data.permission_mode as string) || "SAFE"} onValueChange={(value) => onSet("permission_mode", value)}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {MCP_PERMISSION_MODE_OPTIONS.map((mode) => <SelectItem key={mode.value} value={mode.value}>{mode.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <FieldHint>{MCP_PERMISSION_MODE_OPTIONS.find((mode) => mode.value === ((data.permission_mode as string) || "SAFE"))?.[lang === "ru" ? "descriptionRu" : "descriptionEn"]}</FieldHint>
      </div>
      {skillList.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-xs">{localize(lang, "Skills / политики", "Skills / policies")}</Label>
            <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs" onClick={onBrowseCatalog}>
              <BookOpen className="h-3 w-3" />
              {localize(lang, "Каталог", "Browse Catalog")}
            </Button>
          </div>
          <SkillChecklist skills={skillList} selectedSkillSlugs={selectedSkillSlugs} selectedSkills={selectedSkills} onSet={onSet} />
        </div>
      )}
    </NodeFormSection>
  );
}

function SkillChecklist({ skills, selectedSkillSlugs, selectedSkills, onSet }: { skills: StudioSkill[]; selectedSkillSlugs: string[]; selectedSkills: StudioSkill[]; onSet: SetNodeData }) {
  return (
    <>
      <div className="space-y-1">
        {skills.map((skill) => (
          <label key={skill.slug} className="flex cursor-pointer items-start gap-2 rounded border border-border px-2 py-2 transition-colors hover:bg-muted/30">
            <input
              type="checkbox"
              className="mt-0.5 h-3.5 w-3.5 rounded border-border bg-background"
              checked={selectedSkillSlugs.includes(skill.slug)}
              onChange={() => onSet("skill_slugs", selectedSkillSlugs.includes(skill.slug) ? selectedSkillSlugs.filter((item) => item !== skill.slug) : [...selectedSkillSlugs, skill.slug])}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-medium">{skill.name}</span>
                {skill.service ? <Badge variant="outline" className="text-xs">{skill.service}</Badge> : null}
                {skill.runtime_enforced ? <Badge variant="secondary" className="text-xs">runtime</Badge> : null}
                {skill.safety_level ? <Badge variant="outline" className="text-xs">{skill.safety_level}</Badge> : null}
              </div>
              {skill.guardrail_summary?.length ? <p className="mt-1 text-xs text-muted-foreground">{skill.guardrail_summary.slice(0, 2).join(" • ")}</p> : null}
            </div>
          </label>
        ))}
      </div>
      {selectedSkills.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {selectedSkills.map((skill) => <span key={skill.slug} className="rounded bg-muted/60 px-1 py-0.5 text-xs text-muted-foreground">{skill.name}</span>)}
        </div>
      ) : null}
    </>
  );
}

type McpCallConfigProps = {
  type: string;
  data: NodeData;
  lang: Lang;
  selectedMcpId: number | null;
  selectedMcp: MCPServer | null;
  mcpList: MCPServer[];
  mcpTools: MCPServerTool[];
  isFetchingMcpTools: boolean;
  selectedTool: MCPServerTool | null;
  selectedToolProperties: Record<string, Record<string, unknown>>;
  selectedToolRequiredFields: Set<string>;
  mcpArgsForForm: Record<string, unknown>;
  mcpArgsText: string;
  mcpArgsError: string | null;
  mcpLooksMutating: boolean;
  mcpRiskReasons: string[];
  skillList: StudioSkill[];
  selectedSkillSlugs: string[];
  selectedSkills: StudioSkill[];
  onSet: SetNodeData;
  onSetMany: SetNodePatch;
  onMcpArgsTextChange: (value: string) => void;
  onSetMcpArgument: (key: string, property: Record<string, unknown>, rawValue: string | boolean) => void;
  onBrowseCatalog: () => void;
};

type McpServerSelectProps = Pick<McpCallConfigProps, "data" | "lang" | "selectedMcpId" | "selectedMcp" | "mcpList" | "onSetMany" | "onMcpArgsTextChange">;
type McpToolSelectProps = Pick<McpCallConfigProps, "data" | "lang" | "selectedMcpId" | "mcpTools" | "isFetchingMcpTools" | "onSetMany" | "onMcpArgsTextChange">;
type TypedMcpArgumentsProps = Pick<McpCallConfigProps, "lang" | "onSetMcpArgument"> & {
  properties: Record<string, Record<string, unknown>>;
  requiredFields: Set<string>;
  values: Record<string, unknown>;
};
type McpPolicySectionProps = Pick<McpCallConfigProps, "data" | "lang" | "selectedMcp" | "mcpLooksMutating" | "mcpRiskReasons" | "skillList" | "selectedSkillSlugs" | "selectedSkills" | "onSet" | "onBrowseCatalog">;
