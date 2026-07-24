import { Bot, Cpu, Globe, Key, MessageSquare, RefreshCw, Save, Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { SettingsConfig } from "@/lib/api";
import { API_KEY_PROVIDERS, getProviderLabel, LLM_PROVIDERS } from "./constants";
import { OllamaRuntimeSettings } from "./OllamaRuntimeSettings";
import { PurposeModelSelector } from "./PurposeModelSelector";
import { SectionCard } from "./SectionCard";
import type { UseAiSettingsFormResult } from "./useAiSettingsForm";

type AiSettingsPanelProps = {
  config: SettingsConfig;
  apiKeys?: Record<string, boolean>;
  isAdmin: boolean;
  form: UseAiSettingsFormResult;
};

export function AiSettingsPanel({ config, apiKeys, isAdmin, form }: AiSettingsPanelProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-secondary/20 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">Модели и маршруты</p>
          <p className="max-w-3xl text-xs text-muted-foreground">
            Сначала выберите провайдера по умолчанию. Роли настраивайте отдельно только там, где это действительно нужно.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={form.aiDraftDirty ? "default" : "secondary"}>
            {form.aiDraftDirty ? "Есть несохраненные изменения" : "Настройки синхронизированы"}
          </Badge>
          <Badge variant="outline">{form.uniqueRouteProviders.length > 1 ? "Раздельная маршрутизация" : "Один провайдер на все роли"}</Badge>
        </div>
      </div>

      <SectionCard title="Провайдер по умолчанию" icon={Bot} description="Выбор основного провайдера и модели для общего режима">
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-3">
            {form.providerOverview.map((providerItem) => (
              <button
                key={providerItem.value}
                type="button"
                onClick={() => form.handleDefaultProviderChange(providerItem.value)}
                className={cn(
                  "rounded-2xl border px-4 py-3 text-left transition-colors",
                  providerItem.isSelected
                    ? "border-primary/40 bg-primary/5"
                    : "border-border/60 bg-secondary/15 hover:border-border hover:bg-secondary/35",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">{providerItem.label}</p>
                    <p className="text-xs text-muted-foreground">
                      {providerItem.catalogSize ? `${providerItem.catalogSize} моделей` : "Каталог пуст, доступен ручной ввод"}
                    </p>
                  </div>
                  {providerItem.isSelected ? <Badge className="shrink-0">Основной</Badge> : null}
                </div>
                <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                  <span className={cn("h-2 w-2 rounded-full", providerItem.configured ? "bg-emerald-400" : "bg-amber-400")} />
                  <span>{providerItem.configured ? "Готов к использованию" : "Нужна настройка"}</span>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {providerItem.activeRoutes.length > 0
                    ? `Маршруты: ${providerItem.activeRoutes.join(", ")}`
                    : "Отдельные роли пока не используют этот провайдер"}
                </p>
              </button>
            ))}
          </div>

          <div className="space-y-4 rounded-2xl border border-border/60 bg-secondary/15 p-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground uppercase">Провайдер</label>
                <Select value={form.provider} onValueChange={form.handleDefaultProviderChange}>
                  <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {LLM_PROVIDERS.map((providerItem) => (
                      <SelectItem key={providerItem.value} value={providerItem.value}>{providerItem.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground uppercase">Модель</label>
                {form.availableModels.length > 0 ? (
                  <Select value={form.model} onValueChange={form.setModel}>
                    <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {form.availableModels.map((providerModel) => (
                        <SelectItem key={providerModel} value={providerModel}>{providerModel}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <div className="flex gap-2">
                    <Input value={form.model} onChange={(e) => form.setModel(e.target.value)} placeholder="Model name" className="h-9" />
                    <Button size="sm" variant="outline" className="h-9 px-3" onClick={form.onRefreshModels} disabled={form.refreshing}>
                      <RefreshCw className={cn("h-3.5 w-3.5", form.refreshing && "animate-spin")} />
                    </Button>
                  </div>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-2 rounded-xl border border-border/60 bg-background/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1">
                <p className="text-xs font-medium">{getProviderLabel(form.provider)}</p>
                <p className="text-xs text-muted-foreground">
                  {form.availableModels.length
                    ? "Модель можно выбрать из синхронизированного каталога."
                    : "Для этого провайдера сейчас используется ручной ввод модели."}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">{form.availableModels.length ? `${form.availableModels.length} вариантов` : "Ручной ввод"}</Badge>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button size="sm" variant="ghost" className="gap-1.5" onClick={form.onRefreshModels} disabled={form.refreshing}>
                <RefreshCw className={cn("h-3.5 w-3.5", form.refreshing && "animate-spin")} /> Обновить каталог
              </Button>
              <Button size="sm" className="gap-1.5" onClick={form.onSave} disabled={form.saving}>
                <Save className="h-3.5 w-3.5" /> {form.saving ? "Сохранение..." : "Сохранить основную"}
              </Button>
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Маршруты по ролям" icon={Cpu} description="Отдельные пары провайдер/модель для чата, агентов и пайплайнов">
        <div className="space-y-4">
          <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-secondary/20 p-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-1">
              <p className="text-xs font-medium text-foreground">Быстрые действия</p>
              <p className="text-xs text-muted-foreground">
                Можно скопировать основную модель в роли, дозаполнить пустые поля или откатить черновик к сохраненному состоянию.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" className="gap-1.5" onClick={form.applyDefaultToAll}>
                <Bot className="h-3.5 w-3.5" /> Копировать основную
              </Button>
              <Button size="sm" variant="secondary" className="gap-1.5" onClick={form.fillMissingModels}>
                <Cpu className="h-3.5 w-3.5" /> Заполнить пустые
              </Button>
              <Button size="sm" variant="ghost" className="gap-1.5" onClick={form.resetAiDraft}>
                <RefreshCw className="h-3.5 w-3.5" /> Сбросить черновик
              </Button>
              <Button size="sm" className="gap-1.5" onClick={form.onSavePurpose} disabled={form.saving}>
                <Save className="h-3.5 w-3.5" /> {form.saving ? "Сохранение..." : "Сохранить маршруты"}
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
            <PurposeModelSelector
              label="Чат / терминал"
              description="Быстрые ответы в терминале"
              icon={MessageSquare}
              provider={form.chatProvider}
              model={form.chatModel}
              availableModels={form.getModelsForProvider(form.chatProvider)}
              onProviderChange={(nextProvider) => {
                form.setChatProvider(nextProvider);
                form.setChatModel(form.getSuggestedModelForProvider(nextProvider));
              }}
              onModelChange={form.setChatModel}
              onRefresh={() => form.onRefreshPurpose(form.chatProvider)}
              refreshing={form.refreshingPurpose === form.chatProvider}
            />
            <PurposeModelSelector
              label="Агенты (ReAct)"
              description="Инструменты, планирование и итерации"
              icon={Bot}
              provider={form.agentProvider}
              model={form.agentModel}
              availableModels={form.getModelsForProvider(form.agentProvider)}
              onProviderChange={(nextProvider) => {
                form.setAgentProvider(nextProvider);
                form.setAgentModel(form.getSuggestedModelForProvider(nextProvider));
              }}
              onModelChange={form.setAgentModel}
              onRefresh={() => form.onRefreshPurpose(form.agentProvider)}
              refreshing={form.refreshingPurpose === form.agentProvider}
            />
            <PurposeModelSelector
              label="Пайплайны"
              description="Координация многошаговых запусков"
              icon={Workflow}
              provider={form.orchProvider}
              model={form.orchModel}
              availableModels={form.getModelsForProvider(form.orchProvider)}
              onProviderChange={(nextProvider) => {
                form.setOrchProvider(nextProvider);
                form.setOrchModel(form.getSuggestedModelForProvider(nextProvider));
              }}
              onModelChange={form.setOrchModel}
              onRefresh={() => form.onRefreshPurpose(form.orchProvider)}
              refreshing={form.refreshingPurpose === form.orchProvider}
            />
          </div>
        </div>
      </SectionCard>

      <OllamaRuntimeSettings
        ollamaRoutingActive={form.ollamaRoutingActive}
        openAiRoutingActive={form.openAiRoutingActive}
        ollamaRuntimeSummary={form.ollamaRuntimeSummary}
        ollamaRuntimeMode={form.ollamaRuntimeMode}
        ollamaCloudEnabled={form.ollamaCloudEnabled}
        ollamaBaseUrl={form.ollamaBaseUrl}
        ollamaCloudBaseUrl={form.ollamaCloudBaseUrl}
        ollamaThinkMode={form.ollamaThinkMode}
        reasoningEffort={form.reasoningEffort}
        ollamaLocalModels={form.ollamaLocalModels}
        ollamaCloudModels={form.ollamaCloudModels}
        ollamaCatalogModels={form.ollamaCatalogModels}
        saving={form.saving}
        refreshingPurpose={form.refreshingPurpose}
        setOllamaRuntimeMode={form.setOllamaRuntimeMode}
        setOllamaCloudEnabled={form.setOllamaCloudEnabled}
        setOllamaBaseUrl={form.setOllamaBaseUrl}
        setOllamaCloudBaseUrl={form.setOllamaCloudBaseUrl}
        setOllamaThinkMode={form.setOllamaThinkMode}
        setReasoningEffort={form.setReasoningEffort}
        onSaveOllama={form.onSaveOllama}
        onRefreshPurpose={form.onRefreshPurpose}
      />

      {apiKeys && isAdmin && (
        <SectionCard title="API ключи" icon={Key} description="Подключение и ротация ключей провайдеров">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {API_KEY_PROVIDERS.map((providerItem) => {
              const enabled =
                providerItem.value === "gemini" ? config.gemini_enabled
                  : providerItem.value === "grok" ? config.grok_enabled
                    : providerItem.value === "openai" ? config.openai_enabled
                      : providerItem.value === "claude" ? config.claude_enabled
                        : config.ollama_enabled && form.ollamaCloudEnabled;
              const connected = Boolean(apiKeys[providerItem.statusKey]);
              const draft = form.apiKeyDrafts[providerItem.value] || "";
              const saving = form.savingApiKey === providerItem.value;
              return (
                <div key={providerItem.value} className="space-y-3 rounded-lg border border-border px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-medium">{providerItem.name}</p>
                      <p className="truncate text-xs text-muted-foreground">{providerItem.envName}</p>
                    </div>
                    <Badge variant={connected ? "default" : "secondary"} className="shrink-0">
                      {connected ? "Подключен" : "Не задан"}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className={cn("h-2.5 w-2.5 rounded-full", connected ? "bg-green-500" : "bg-red-500")} />
                    <p className="text-xs text-muted-foreground">
                      {enabled ? "Активен" : "Отключен"} · значение ключа не выводится
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Input
                      type="password"
                      autoComplete="new-password"
                      value={draft}
                      onChange={(event) => form.setApiKeyDraft(providerItem.value, event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && draft.trim()) form.onSaveApiKey(providerItem.value);
                      }}
                      placeholder={providerItem.placeholder}
                      className="h-9 font-mono text-xs"
                    />
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => form.onClearApiKey(providerItem.value)}
                        disabled={saving || !connected}
                      >
                        Очистить
                      </Button>
                      <Button
                        size="sm"
                        className="gap-1.5"
                        onClick={() => form.onSaveApiKey(providerItem.value)}
                        disabled={saving || !draft.trim()}
                      >
                        <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение..." : "Сохранить"}
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}

      {isAdmin && config.domain_auth_enabled !== undefined && (
        <SectionCard title="Доменная авторизация" icon={Globe} description="SSO через HTTP-заголовок">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-border px-3 py-2.5">
              <p className="text-xs text-muted-foreground uppercase">Статус</p>
              <p className="text-sm font-medium">{config.domain_auth_enabled ? "Включен" : "Выключен"}</p>
            </div>
            <div className="rounded-lg border border-border px-3 py-2.5">
              <p className="text-xs text-muted-foreground uppercase">Header</p>
              <p className="text-sm font-mono">{config.domain_auth_header || "REMOTE_USER"}</p>
            </div>
            <div className="rounded-lg border border-border px-3 py-2.5">
              <p className="text-xs text-muted-foreground uppercase">Авто-создание</p>
              <p className="text-sm font-medium">{config.domain_auth_auto_create ? "Да" : "Нет"}</p>
            </div>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
