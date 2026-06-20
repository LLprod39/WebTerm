import { useState } from "react";
import { Bot } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { QueryStateBlock } from "@/components/ui/page-shell";
import {
  fetchAuthSession,
  fetchModels,
  fetchSettings,
} from "@/lib/api";
import { AiSettingsPanel } from "../settings-page/AiSettingsPanel";
import { useAiSettingsForm } from "../settings-page/useAiSettingsForm";

export default function SettingsAIPage() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);

  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;

  const { data: settingsData, isLoading: settingsLoading, error: settingsError } = useQuery({
    queryKey: ["settings", "config"],
    queryFn: fetchSettings,
    staleTime: 30_000,
  });

  const { data: modelsData } = useQuery({
    queryKey: ["settings", "models"],
    queryFn: fetchModels,
    staleTime: 30_000,
  });

  const currentConfig = settingsData?.config;
  const apiKeys = settingsData?.api_keys as Record<string, boolean> | undefined;
  const aiSettings = useAiSettingsForm({
    currentConfig,
    modelsData,
    apiKeys,
    saving,
    setSaving,
  });

  if (settingsLoading || settingsError || !settingsData?.success) {
    return (
      <QueryStateBlock
        loading={settingsLoading}
        error={settingsError || (!settingsLoading && !settingsData?.success ? new Error("Ошибка загрузки настроек") : undefined)}
        errorText="Не удалось загрузить настройки моделей"
        onRetry={() => queryClient.invalidateQueries({ queryKey: ["settings", "config"] })}
      >
        {null}
      </QueryStateBlock>
    );
  }

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-secondary text-foreground">
            <Bot className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-foreground">Настройки AI</h1>
            <p className="text-[11px] text-muted-foreground">
              Провайдеры, модели по ролям, Ollama и безопасная маршрутизация запросов.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{aiSettings.configuredProviderCount} активных API</Badge>
          {aiSettings.aiDraftDirty ? <Badge>Есть черновик</Badge> : <Badge variant="outline">Все сохранено</Badge>}
        </div>
      </div>

      <AiSettingsPanel config={settingsData.config} apiKeys={apiKeys} isAdmin={isAdmin} form={aiSettings} />
    </div>
  );
}
