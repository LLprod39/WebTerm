import { useState } from "react";
import { Bot } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
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
    <div className="space-y-5 pb-10">
      <SettingsPageHeader
        icon={Bot}
        title="AI и модели"
        description="Провайдеры, API-ключи и модели для чата, агентов и оркестратора. Настраивается в UI после деплоя."
        actions={
          <>
            <Badge variant="secondary">{aiSettings.configuredProviderCount} активных API</Badge>
            {aiSettings.aiDraftDirty ? <Badge>Есть черновик</Badge> : <Badge variant="outline">Все сохранено</Badge>}
          </>
        }
      />

      <AiSettingsPanel config={settingsData.config} apiKeys={apiKeys} isAdmin={isAdmin} form={aiSettings} />
    </div>
  );
}
