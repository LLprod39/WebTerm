import { Database, RefreshCw, Save } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
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
    <SectionCard title="Ollama и рассуждение" icon={Database} description="Локальные и облачные модели">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="rounded-xl border border-border p-4 space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-medium">Среда Ollama</p>
              <p className="text-xs text-muted-foreground">Локальный сервер и облако</p>
            </div>
            <Badge variant={ollamaRoutingActive ? "default" : "secondary"}>
              {ollamaRoutingActive ? `Используется · ${ollamaRuntimeSummary}` : `Готов · ${ollamaRuntimeSummary}`}
            </Badge>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase">Режим запуска</label>
              <Select
                value={ollamaRuntimeMode}
                onValueChange={(value) => {
                  setOllamaRuntimeMode(value);
                  if (value === "cloud") {
                    setOllamaCloudEnabled(true);
                  }
                }}
              >
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {OLLAMA_RUNTIME_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
                <div>
                  <p className="text-xs font-medium">Ollama Cloud</p>
                  <p className="text-xs text-muted-foreground">Модели с ollama.com</p>
                </div>
                <Switch
                  checked={ollamaCloudEnabled}
                  onCheckedChange={(checked) => {
                    setOllamaCloudEnabled(checked);
                    if (!checked && ollamaRuntimeMode === "cloud") {
                      setOllamaRuntimeMode("auto");
                    }
                  }}
                />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground uppercase">Адрес локального Ollama</label>
            <Input
              value={ollamaBaseUrl}
              onChange={(e) => setOllamaBaseUrl(e.target.value)}
              placeholder="http://127.0.0.1:11434"
              className="h-9"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground uppercase">Адрес Ollama Cloud</label>
            <Input
              value={ollamaCloudBaseUrl}
              onChange={(e) => setOllamaCloudBaseUrl(e.target.value)}
              placeholder="https://ollama.com"
              className="h-9"
              disabled={!ollamaCloudEnabled}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="gap-1.5" onClick={onSaveOllama} disabled={saving}>
              <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение…" : "Сохранить Ollama"}
            </Button>
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
          </div>

          <div className="rounded-lg border border-dashed border-border px-4 py-3">
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">Локальные: {ollamaLocalModels.length}</Badge>
              <Badge variant="secondary">Облачные: {ollamaCloudModels.length}</Badge>
              <Badge variant="outline">{ollamaRuntimeSummary}</Badge>
              <Badge variant="outline">{ollamaCatalogModels.length} всего в каталоге</Badge>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Авто сначала использует локальный Ollama. Для облака нужен ключ OLLAMA_API_KEY.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-border p-4 space-y-4">
          <div>
            <p className="text-xs font-medium">Глубина рассуждения</p>
            <p className="text-xs text-muted-foreground">Отдельно для Ollama и OpenAI</p>
          </div>

          <div className="space-y-2">
            <div>
              <p className="text-xs font-medium">Рассуждение Ollama</p>
              <p className="text-xs text-muted-foreground">Для моделей с поддержкой параметра think</p>
            </div>

            <Select value={ollamaThinkMode} onValueChange={setOllamaThinkMode}>
              <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {OLLAMA_THINKING_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="rounded-lg border border-dashed border-border px-4 py-3">
              <p className="text-xs font-medium">
                {ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE
                  ? "Модель сама выбирает режим."
                  : ollamaThinkMode === "off"
                    ? "Рассуждение будет отключено."
                    : `В Ollama будет отправлен think=${ollamaThinkMode}.`}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Один режим применяется к локальным и облачным моделям.
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <div>
              <p className="text-xs font-medium">Рассуждение OpenAI</p>
              <p className="text-xs text-muted-foreground">Глубина рассуждения для Responses API</p>
            </div>

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

            <div className="rounded-lg border border-dashed border-border px-4 py-3">
              <p className="text-xs font-medium">
                {openAiRoutingActive
                  ? "OpenAI используется для одной из задач."
                  : "Настройку можно сохранить заранее."}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Авто оставляет выбор модели. Более высокая глубина может увеличить время и стоимость ответа.
              </p>
            </div>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
