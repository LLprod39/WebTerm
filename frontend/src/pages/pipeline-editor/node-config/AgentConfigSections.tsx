import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatCommandListText, parseCommandListText } from "@/components/pipeline/commandList";

import { AdvancedDisclosure, FailureSelect, FieldHint, NodeFormSection } from "../PanelPrimitives";
import { DIRECT_LLM_PROVIDERS } from "../pipelineGraphUtils";
import { localize } from "../presentation";
import type { Lang, NodeData, ServerOption, SetNodeData } from "./types";

const SUDO_DIRECT_OPTIONS = [
  {
    value: "disabled",
    labelRu: "Без sudo",
    labelEn: "No sudo",
    hintRu: "Команды с sudo будут заблокированы.",
    hintEn: "Commands with sudo are blocked.",
  },
  {
    value: "ask",
    labelRu: "Спросить",
    labelEn: "Ask",
    hintRu: "Нода остановится, если команда потребует sudo-разрешение.",
    hintEn: "The node stops when the command needs sudo approval.",
  },
  {
    value: "approved",
    labelRu: "Разрешить",
    labelEn: "Approved",
    hintRu: "Sudo разрешён на этот запуск; backend выполнит его как sudo -n.",
    hintEn: "Sudo is approved for this run; backend enforces sudo -n.",
  },
] as const;

export function SshCommandConfig({
  type,
  data,
  servers,
  lang,
  onSet,
}: {
  type: string;
  data: NodeData;
  servers: ServerOption[];
  lang: Lang;
  onSet: SetNodeData;
}) {
  if (type !== "agent/ssh_cmd") return null;
  const sudoPolicy = (data.sudo_policy as string) || "disabled";
  const sudoHint = SUDO_DIRECT_OPTIONS.find((option) => option.value === sudoPolicy) || SUDO_DIRECT_OPTIONS[0];

  return (
    <NodeFormSection
      title={localize(lang, "Исполнение", "Execution")}
      description={localize(lang, "Команда будет выполнена напрямую по SSH без LLM-планирования.", "The command runs directly over SSH without LLM planning.")}
    >
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Целевой сервер", "Target server")}</Label>
        <Select value={String(data.server_id || "")} onValueChange={(value) => onSet("server_id", parseInt(value, 10))}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue placeholder={localize(lang, "Выберите сервер...", "Select server...")} />
          </SelectTrigger>
          <SelectContent>
            {servers.map((server) => (
              <SelectItem key={server.id} value={String(server.id)}>{server.name} ({server.host})</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Команда", "Command")}</Label>
        <Textarea
          value={(data.command as string) || ""}
          onChange={(event) => onSet("command", event.target.value)}
          placeholder="df -h && free -h"
          className="text-xs font-mono resize-none"
          rows={3}
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Controlled sudo</Label>
        <Select value={sudoPolicy} onValueChange={(value) => onSet("sudo_policy", value)}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SUDO_DIRECT_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {localize(lang, option.labelRu, option.labelEn)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <FieldHint>{localize(lang, sudoHint.hintRu, sudoHint.hintEn)}</FieldHint>
      </div>
      <label className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          className="h-4 w-4"
          checked={data.dry_run === true}
          onChange={(event) => onSet("dry_run", event.target.checked)}
        />
        <span>{localize(lang, "Только предпросмотр изменяющей команды", "Preview changing command only")}</span>
      </label>
      <AdvancedDisclosure title={localize(lang, "Проверки до/после", "Pre/post checks")}>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Preflight команды", "Preflight commands")}</Label>
          <Textarea
            value={formatCommandListText(data.preflight_commands)}
            onChange={(event) => onSet("preflight_commands", parseCommandListText(event.target.value))}
            placeholder={"systemctl is-active nginx\nnginx -t"}
            className="text-xs font-mono resize-none"
            rows={3}
          />
          <FieldHint>
            {localize(
              lang,
              "Одна read-only команда на строку. Если любая вернёт non-zero, основной SSH command не запустится.",
              "One read-only command per line. If any command returns non-zero, the main SSH command will not run.",
            )}
          </FieldHint>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Verification команды", "Verification commands")}</Label>
          <Textarea
            value={formatCommandListText(data.verification_commands)}
            onChange={(event) => onSet("verification_commands", parseCommandListText(event.target.value))}
            placeholder={"systemctl is-active nginx\ncurl -fsS http://localhost/health"}
            className="text-xs font-mono resize-none"
            rows={3}
          />
          <FieldHint>
            {localize(
              lang,
              "Команды выполняются после основной команды и попадают в секции output как verification evidence.",
              "Commands run after the main command and are included in output sections as verification evidence.",
            )}
          </FieldHint>
        </div>
      </AdvancedDisclosure>
      <FailureSelect lang={lang} value={(data.on_failure as string) || "abort"} onChange={(value) => onSet("on_failure", value)} />
    </NodeFormSection>
  );
}

export function LlmQueryConfig({
  type,
  data,
  lang,
  nodeId,
  provider,
  modelList,
  loadingModelsFor,
  onSet,
  onProviderChange,
}: {
  type: string;
  data: NodeData;
  lang: Lang;
  nodeId: string;
  provider: string;
  modelList: string[];
  loadingModelsFor: string | null;
  onSet: SetNodeData;
  onProviderChange: (provider: string) => void;
}) {
  if (type !== "agent/llm_query") return null;

  return (
    <>
      <NodeFormSection
        title={localize(lang, "Вход / условие", "Input / condition")}
        description={localize(lang, "Запрос к модели без автономных инструментов.", "Model prompt without autonomous tools.")}
      >
        <div className="space-y-1.5">
          <Label className="text-xs">Prompt</Label>
          <Textarea
            value={(data.prompt as string) || ""}
            onChange={(event) => onSet("prompt", event.target.value)}
            placeholder="Analyze the data from previous steps and provide recommendations..."
            className="text-xs resize-none"
            rows={5}
          />
          <FieldHint>
            {localize(lang, "Используйте", "Use")} <code>{"{all_outputs}"}</code> {localize(lang, "для всех предыдущих выводов или", "for all previous node outputs, or")} <code>{"{node_id}"}</code> {localize(lang, "для конкретной ноды.", "for a specific node.")}
          </FieldHint>
        </div>
      </NodeFormSection>
      <NodeFormSection title={localize(lang, "Исполнение", "Execution")}>
        <div className="space-y-1.5">
          <Label className="text-xs">System Prompt</Label>
          <Textarea
            value={(data.system_prompt as string) || ""}
            onChange={(event) => onSet("system_prompt", event.target.value)}
            placeholder="You are a senior DevOps engineer..."
            className="text-xs resize-none"
            rows={2}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs">{localize(lang, "Провайдер", "Provider")}</Label>
            <Select value={(data.provider as string) || "gemini"} onValueChange={onProviderChange}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DIRECT_LLM_PROVIDERS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{localize(lang, "Модель", "Model")}</Label>
            <Select value={(data.model as string) || ""} onValueChange={(value) => onSet("model", value)} disabled={loadingModelsFor === provider}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder={loadingModelsFor === provider ? localize(lang, "Загрузка моделей...", "Loading models...") : localize(lang, "Выберите модель", "Select model")} />
              </SelectTrigger>
              <SelectContent>
                {modelList.length
                  ? modelList.map((model) => <SelectItem key={model} value={model}>{model}</SelectItem>)
                  : <SelectItem value="_empty" disabled>{localize(lang, "Модели недоступны", "No models available")}</SelectItem>}
              </SelectContent>
            </Select>
          </div>
        </div>
        <FieldHint>
          {localize(lang, "Вывод доступен следующим нодам как", "Output is available for next nodes as")} <code>{`{${nodeId}}`}</code> {localize(lang, "и", "and")} <code>{`{${nodeId}_output}`}</code>
        </FieldHint>
      </NodeFormSection>
    </>
  );
}
