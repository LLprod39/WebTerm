import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Save, Settings2 } from "lucide-react";

import { bindPluginSecret, fetchPluginSettings, updatePluginSettings } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";

function schemaProperties(schema: Record<string, unknown>) {
  const properties = schema.properties;
  return properties && typeof properties === "object" && !Array.isArray(properties)
    ? properties as Record<string, { type?: string; default?: unknown }>
    : {};
}

export function PluginSettingsPanel({ installationId }: { installationId: number | null }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [secretRefs, setSecretRefs] = useState<Record<string, string>>({});

  const settingsQuery = useQuery({
    queryKey: ["plugins", "settings", installationId],
    queryFn: () => fetchPluginSettings(installationId as number),
    enabled: Boolean(installationId),
  });

  const properties = useMemo(() => schemaProperties(settingsQuery.data?.schema ?? {}), [settingsQuery.data?.schema]);
  const propertyEntries = Object.entries(properties);

  useEffect(() => {
    const current = settingsQuery.data?.settings;
    if (!current) return;
    setSettings(
      Object.fromEntries(
        Object.keys(properties).map((key) => [key, String(current[key] ?? properties[key]?.default ?? "")]),
      ),
    );
  }, [properties, settingsQuery.data?.settings]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["plugins", "settings", installationId] });
    await queryClient.invalidateQueries({ queryKey: ["plugins", "installed"] });
  };

  const saveSettings = useMutation({
    mutationFn: () => updatePluginSettings(installationId as number, settings),
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Настройки сохранены.", "Plugin settings saved.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const bindSecret = useMutation({
    mutationFn: ({ key, ref }: { key: string; ref: string }) => bindPluginSecret(installationId as number, key, ref),
    onSuccess: () => {
      setSecretRefs({});
      invalidate();
      toast({ description: localize(lang, "Секрет подключён.", "Secret reference bound.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  return (
    <SectionCard title={localize(lang, "Настройки и секреты", "Settings and secrets")} description={localize(lang, "Параметры выбранного плагина.", "Settings for the selected plugin.")} icon={<Settings2 className="h-4 w-4" />}>
      <QueryStateBlock loading={settingsQuery.isLoading} error={settingsQuery.error}>
        {!installationId ? (
          <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
            {localize(lang, "Выберите плагин, чтобы изменить настройки.", "Select a plugin to edit its settings.")}
          </p>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-3">
              {propertyEntries.length ? propertyEntries.map(([key, spec]) => (
                <label key={key} className="block rounded-lg border border-border/70 bg-secondary/15 px-4 py-3">
                  <span className="flex items-center justify-between gap-2 text-xs font-semibold text-muted-foreground">
                    {key}
                    <Badge variant="outline">{spec.type || "value"}</Badge>
                  </span>
                  <Input
                    className="mt-2"
                    value={settings[key] ?? ""}
                    onChange={(event) => setSettings((prev) => ({ ...prev, [key]: event.target.value }))}
                  />
                </label>
              )) : (
                <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
                  {localize(lang, "У этого плагина нет настраиваемых параметров.", "This plugin has no configurable settings.")}
                </p>
              )}
              {propertyEntries.length ? (
                <Button size="sm" onClick={() => saveSettings.mutate()} disabled={saveSettings.isPending}>
                  <Save className="h-4 w-4" />
                  {localize(lang, "Сохранить", "Save")}
                </Button>
              ) : null}
            </div>

            <div className="space-y-3">
              {(settingsQuery.data?.secrets ?? []).length ? settingsQuery.data?.secrets.map((secret) => (
                <div key={secret.key} className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-semibold text-foreground">{secret.label}</div>
                      <div className="mt-0.5 text-xs text-muted-foreground">{secret.key}</div>
                    </div>
                    <StatusBadge label={secret.bound ? localize(lang, "подключён", "bound") : localize(lang, "не подключён", "unbound")} tone={secret.bound ? "success" : secret.required ? "warning" : "neutral"} />
                  </div>
                  {secret.bound ? <div className="mt-2 text-xs text-muted-foreground">{localize(lang, "Текущая ссылка:", "Current reference:")} {secret.secret_ref}</div> : null}
                  <div className="mt-3 flex gap-2">
                    <Input
                      value={secretRefs[secret.key] ?? ""}
                      onChange={(event) => setSecretRefs((prev) => ({ ...prev, [secret.key]: event.target.value }))}
                      placeholder={localize(lang, "Ссылка на управляемый секрет", "Managed secret reference")}
                    />
                    <Button
                      size="icon"
                      variant="outline"
                      disabled={bindSecret.isPending || !secretRefs[secret.key]}
                      onClick={() => bindSecret.mutate({ key: secret.key, ref: secretRefs[secret.key] })}
                    >
                      <KeyRound className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )) : (
                <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
                  {localize(lang, "Плагину не нужны секреты.", "This plugin does not require secrets.")}
                </p>
              )}
            </div>
          </div>
        )}
      </QueryStateBlock>
    </SectionCard>
  );
}
