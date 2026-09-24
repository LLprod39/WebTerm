import { Bot, Cpu, Globe, Key, MessageSquare, RefreshCw, Save, Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsField, SettingsSectionActions } from "@/components/settings/SettingsPageShell";
import { cn } from "@/lib/utils";
import type { SettingsConfig } from "@/lib/api";
import { API_KEY_PROVIDERS, getProviderLabel, LLM_PROVIDERS } from "./constants";
import { OllamaRuntimeSettings } from "./OllamaRuntimeSettings";
import { ProviderModelPicker } from "./ProviderModelPicker";
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
  const modelControlsDisabled = !isAdmin;

  return (
    <div className="space-y-5">
      <SectionCard
        title="Провайдер по умолчанию"
        icon={Bot}
        description="Основной провайдер и модель для общего режима"
      >
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {form.providerOverview.map((providerItem) => (
              <button
                key={providerItem.value}
                type="button"
                disabled={modelControlsDisabled}
                onClick={() => form.handleDefaultProviderChange(providerItem.value)}
                className={cn(
                  "rounded-sm border px-3.5 py-3 text-left transition-colors",
                  modelControlsDisabled && "cursor-not-allowed opacity-70",
                  providerItem.isSelected
                    ? "border-primary/40 bg-primary/8"
                    : "border-border bg-surface-0/40 hover:border-border hover:bg-surface-1/60",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-foreground">{providerItem.label}</p>
                  {providerItem.isSelected ? (
                    <Badge className="shrink-0">Основной</Badge>
                  ) : null}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {providerItem.catalogSize
                    ? `${providerItem.catalogSize} моделей`
                    : "Каталог пуст"}
                </p>
                <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      providerItem.configured ? "bg-success" : "bg-warning",
                    )}
                  />
                  <span>{providerItem.configured ? "Готов" : "Нужна настройка"}</span>
                </div>
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <SettingsField label="Провайдер">
              <Select
                value={form.provider}
                onValueChange={form.handleDefaultProviderChange}
                disabled={modelControlsDisabled}
              >
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {LLM_PROVIDERS.map((providerItem) => (
                    <SelectItem key={providerItem.value} value={providerItem.value}>
                      {providerItem.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </SettingsField>
            <SettingsField
              label="Модель"
              hint={
                modelControlsDisabled
                  ? "Только администратор может менять модели и провайдеры."
                  : form.provider === "openrouter"
                    ? "Вставьте id с openrouter.ai или выберите из каталога (Free / Paid)."
                    : form.availableModels.length
                      ? `${getProviderLabel(form.provider)} · модель из каталога или ручной ввод`
                      : `${getProviderLabel(form.provider)} · ручной ввод модели`
              }
            >
              <ProviderModelPicker
                provider={form.provider}
                value={form.model}
                availableModels={form.availableModels}
                disabled={modelControlsDisabled}
                refreshing={form.refreshing}
                onChange={form.setModel}
                onRefresh={form.onRefreshModels}
              />
            </SettingsField>
          </div>

          {isAdmin ? (
            <SettingsSectionActions>
              <Button size="sm" variant="ghost" className="gap-1.5" onClick={form.onRefreshModels} disabled={form.refreshing}>
                <RefreshCw className={cn("h-3.5 w-3.5", form.refreshing && "animate-spin")} />
                Обновить каталог
              </Button>
              <Button size="sm" className="gap-1.5" onClick={form.onSave} disabled={form.saving}>
                <Save className="h-3.5 w-3.5" />
                {form.saving ? "Сохранение…" : "Сохранить"}
              </Button>
            </SettingsSectionActions>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        title="Модели по назначению"
        icon={Cpu}
        description="Отдельные модели для чата, агентов и сценариев"
        actions={
          isAdmin ? (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" className="gap-1.5" onClick={form.applyDefaultToAll}>
                <Bot className="h-3.5 w-3.5" /> Копировать основную
              </Button>
              <Button size="sm" variant="secondary" className="gap-1.5" onClick={form.fillMissingModels}>
                <Cpu className="h-3.5 w-3.5" /> Заполнить пустые
              </Button>
              <Button size="sm" variant="ghost" className="gap-1.5" onClick={form.resetAiDraft}>
                <RefreshCw className="h-3.5 w-3.5" /> Сбросить
              </Button>
              <Button size="sm" className="gap-1.5" onClick={form.onSavePurpose} disabled={form.saving}>
                <Save className="h-3.5 w-3.5" />
                {form.saving ? "Сохранение…" : "Сохранить"}
              </Button>
            </div>
          ) : undefined
        }
      >
        <div className="overflow-hidden rounded-sm border border-border xl:grid xl:grid-cols-3">
          <PurposeModelSelector
            label="Чат / терминал"
            description="Быстрые ответы в терминале"
            icon={MessageSquare}
            provider={form.chatProvider}
            model={form.chatModel}
            availableModels={form.getModelsForProvider(form.chatProvider)}
            disabled={modelControlsDisabled}
            onProviderChange={(nextProvider) => {
              form.setChatProvider(nextProvider);
              form.setChatModel(form.getSuggestedModelForProvider(nextProvider));
            }}
            onModelChange={form.setChatModel}
            onRefresh={() => form.onRefreshPurpose(form.chatProvider)}
            refreshing={form.refreshingPurpose === form.chatProvider}
          />
          <PurposeModelSelector
            label="Агенты"
            description="Инструменты, планирование и итерации"
            icon={Bot}
            provider={form.agentProvider}
            model={form.agentModel}
            availableModels={form.getModelsForProvider(form.agentProvider)}
            disabled={modelControlsDisabled}
            onProviderChange={(nextProvider) => {
              form.setAgentProvider(nextProvider);
              form.setAgentModel(form.getSuggestedModelForProvider(nextProvider));
            }}
            onModelChange={form.setAgentModel}
            onRefresh={() => form.onRefreshPurpose(form.agentProvider)}
            refreshing={form.refreshingPurpose === form.agentProvider}
          />
          <PurposeModelSelector
            label="Сценарии"
            description="Координация многошаговых запусков"
            icon={Workflow}
            provider={form.orchProvider}
            model={form.orchModel}
            availableModels={form.getModelsForProvider(form.orchProvider)}
            disabled={modelControlsDisabled}
            onProviderChange={(nextProvider) => {
              form.setOrchProvider(nextProvider);
              form.setOrchModel(form.getSuggestedModelForProvider(nextProvider));
            }}
            onModelChange={form.setOrchModel}
            onRefresh={() => form.onRefreshPurpose(form.orchProvider)}
            refreshing={form.refreshingPurpose === form.orchProvider}
          />
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

      {apiKeys && isAdmin ? (
        <SectionCard title="API-ключи" icon={Key} description="Ключи внешних провайдеров">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
                <div key={providerItem.value} className="space-y-3 rounded-sm border border-border bg-surface-0/40 px-3.5 py-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">{providerItem.name}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {enabled ? "Активен" : "Отключён"} · ключ скрыт
                      </p>
                    </div>
                    <Badge variant={connected ? "default" : "secondary"} className="shrink-0">
                      {connected ? "Подключён" : "Не задан"}
                    </Badge>
                  </div>
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
                      <Save className="h-3.5 w-3.5" />
                      {saving ? "Сохранение…" : "Сохранить"}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      ) : null}

      {isAdmin && config.domain_auth_enabled !== undefined ? (
        <SectionCard title="Доменная авторизация" icon={Globe} description="SSO через HTTP-заголовок — подробности в разделе SSO">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-sm border border-border bg-surface-0/40 px-3.5 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">Статус</p>
              <p className="mt-1 text-sm font-medium">{config.domain_auth_enabled ? "Включён" : "Выключен"}</p>
            </div>
            <div className="rounded-sm border border-border bg-surface-0/40 px-3.5 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">Заголовок</p>
              <p className="mt-1 font-mono text-sm">{config.domain_auth_header || "REMOTE_USER"}</p>
            </div>
            <div className="rounded-sm border border-border bg-surface-0/40 px-3.5 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">Авто-создание</p>
              <p className="mt-1 text-sm font-medium">{config.domain_auth_auto_create ? "Да" : "Нет"}</p>
            </div>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
