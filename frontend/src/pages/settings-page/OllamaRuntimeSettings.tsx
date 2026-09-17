import { Database, RefreshCw, Save } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { SettingsField, SettingsSectionActions } from "@/components/settings/SettingsPageShell";
import { cn } from "@/lib/utils";
import {
  AUTO_OLLAMA_THINKING_VALUE,
  AUTO_REASONING_VALUE,
  OLLAMA_RUNTIME_OPTIONS,
  OLLAMA_THINKING_OPTIONS,
} from "./constants";
import { SectionCard } from "./SectionCard";

type OllamaRuntimeSettingsProps = {
  ollamaRoutingActive: boolean;
  openAiRoutingActive: boolean;
  ollamaRuntimeSummary: string;
  ollamaRuntimeMode: string;
  ollamaCloudEnabled: boolean;
  ollamaBaseUrl: string;
  ollamaCloudBaseUrl: string;
  ollamaThinkMode: string;
  reasoningEffort: string;
  ollamaLocalModels: string[];
  ollamaCloudModels: string[];
  ollamaCatalogModels: string[];
  saving: boolean;
  refreshingPurpose: string | null;
  setOllamaRuntimeMode: Dispatch<SetStateAction<string>>;
  setOllamaCloudEnabled: Dispatch<SetStateAction<boolean>>;
  setOllamaBaseUrl: Dispatch<SetStateAction<string>>;
  setOllamaCloudBaseUrl: Dispatch<SetStateAction<string>>;
  setOllamaThinkMode: Dispatch<SetStateAction<string>>;
  setReasoningEffort: Dispatch<SetStateAction<string>>;
  onSaveOllama: () => Promise<void>;
  onRefreshPurpose: (provider: string) => Promise<void>;
};

export function OllamaRuntimeSettings({
  ollamaRoutingActive,
  openAiRoutingActive,
  ollamaRuntimeSummary,
  ollamaRuntimeMode,
  ollamaCloudEnabled,
  ollamaBaseUrl,
  ollamaCloudBaseUrl,
  ollamaThinkMode,
  reasoningEffort,
  ollamaLocalModels,
  ollamaCloudModels,
  ollamaCatalogModels,
  saving,
  refreshingPurpose,
  setOllamaRuntimeMode,
  setOllamaCloudEnabled,
  setOllamaBaseUrl,
  setOllamaCloudBaseUrl,
  setOllamaThinkMode,
  setReasoningEffort,
  onSaveOllama,
  onRefreshPurpose,
}: OllamaRuntimeSettingsProps) {
  return (
    <SectionCard
      title="Ollama и рассуждение"
      icon={Database}
      description="Локальные и облачные модели, глубина рассуждения"
      actions={
        <Badge variant={ollamaRoutingActive ? "default" : "secondary"}>
          {ollamaRoutingActive ? `Используется · ${ollamaRuntimeSummary}` : `Готов · ${ollamaRuntimeSummary}`}
        </Badge>
      }
    >
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2 xl:gap-8">
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-foreground">Среда Ollama</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Локальный сервер и облако</p>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <SettingsField label="Режим запуска">
              <Select
                value={ollamaRuntimeMode}
                onValueChange={(value) => {
                  setOllamaRuntimeMode(value);
                  if (value === "cloud") setOllamaCloudEnabled(true);
                }}
              >
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {OLLAMA_RUNTIME_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </SettingsField>

            <div className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-0/40 px-3 py-2.5">
              <div className="min-w-0">
                <p className="text-xs font-medium text-foreground">Ollama Cloud</p>
                <p className="text-xs text-muted-foreground">Модели с ollama.com</p>
              </div>
              <Switch
                checked={ollamaCloudEnabled}
                onCheckedChange={(checked) => {
                  setOllamaCloudEnabled(checked);
                  if (!checked && ollamaRuntimeMode === "cloud") setOllamaRuntimeMode("auto");
                }}
              />
            </div>
          </div>

          <SettingsField label="Адрес локального Ollama">
            <Input
              value={ollamaBaseUrl}
              onChange={(e) => setOllamaBaseUrl(e.target.value)}
              placeholder="http://127.0.0.1:11434"
              className="h-9"
            />
          </SettingsField>

          <SettingsField label="Адрес Ollama Cloud">
            <Input
              value={ollamaCloudBaseUrl}
              onChange={(e) => setOllamaCloudBaseUrl(e.target.value)}
              placeholder="https://ollama.com"
              className="h-9"
              disabled={!ollamaCloudEnabled}
            />
          </SettingsField>

          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>Локальные: {ollamaLocalModels.length}</span>
            <span aria-hidden>·</span>
            <span>Облачные: {ollamaCloudModels.length}</span>
            <span aria-hidden>·</span>
            <span>В каталоге: {ollamaCatalogModels.length}</span>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            Авто сначала использует локальный Ollama. Для облака нужен ключ OLLAMA_API_KEY.
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-foreground">Глубина рассуждения</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Отдельно для Ollama и OpenAI</p>
          </div>

          <SettingsField
            label="Рассуждение Ollama"
            hint={
              ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE
                ? "Модель сама выбирает режим. Один режим для локальных и облачных моделей."
                : ollamaThinkMode === "off"
                  ? "Рассуждение будет отключено."
                  : `В Ollama будет отправлен think=${ollamaThinkMode}.`
            }
          >
            <Select value={ollamaThinkMode} onValueChange={setOllamaThinkMode}>
              <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {OLLAMA_THINKING_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingsField>

          <SettingsField
            label="Рассуждение OpenAI"
            hint={
              openAiRoutingActive
                ? "OpenAI используется для одной из задач. Более высокая глубина может увеличить время и стоимость."
                : "Настройку можно сохранить заранее. Авто оставляет выбор модели."
            }
          >
            <Select value={reasoningEffort} onValueChange={setReasoningEffort}>
              <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={AUTO_REASONING_VALUE}>Авто</SelectItem>
                <SelectItem value="none">Выкл</SelectItem>
                <SelectItem value="low">Низкая</SelectItem>
                <SelectItem value="medium">Средняя</SelectItem>
                <SelectItem value="high">Высокая</SelectItem>
              </SelectContent>
            </Select>
          </SettingsField>
        </div>
      </div>

      <SettingsSectionActions className="mt-6">
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          onClick={() => onRefreshPurpose("ollama")}
          disabled={refreshingPurpose === "ollama"}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", refreshingPurpose === "ollama" && "animate-spin")} />
          Проверить модели
        </Button>
        <Button size="sm" className="gap-1.5" onClick={onSaveOllama} disabled={saving}>
          <Save className="h-3.5 w-3.5" />
          {saving ? "Сохранение…" : "Сохранить"}
        </Button>
      </SettingsSectionActions>
    </SectionCard>
  );
}
