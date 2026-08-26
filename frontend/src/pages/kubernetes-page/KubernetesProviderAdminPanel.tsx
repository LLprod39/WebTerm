import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, CloudCog, Play, Plus, Save, Trash2 } from "lucide-react";

import {
  createKubernetesProvider,
  deleteKubernetesProvider,
  probeKubernetesProvider,
  syncKubernetesProvider,
  updateKubernetesProvider,
  type KubernetesAuthMode,
  type KubernetesProviderProbeResult,
  type KubernetesProvider,
  type KubernetesProviderKind,
  type KubernetesProviderPayload,
  type KubernetesSyncResult,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { localize } from "@/lib/i18n";
import { statusTone } from "@/pages/kubernetes-page/kubernetesPageSections";

type ProviderForm = {
  id: number | null;
  name: string;
  kind: KubernetesProviderKind;
  base_url: string;
  enabled: boolean;
  auth_mode: KubernetesAuthMode;
  secret_ref: string;
  secret_value: string;
  labels: string;
};

const RANCHER_LABELS = JSON.stringify(
  {
    clusters_path: "/v3/clusters",
    namespaces_path: "/v3/projectnamespaces",
    workloads_path: "/v3/workloads",
    pods_path: "/v3/pods",
    services_path: "/v3/services",
    ingresses_path: "/v3/ingresses",
    events_path: "/v3/events",
    pod_logs_path_template: "/v3/pods/{namespace}:{pod_name}/logs?tail={tail}",
    fleet_bundles_path: "/v1/fleet.cattle.io.bundles",
  },
  null,
  2,
);

const DEVTRON_LABELS = JSON.stringify(
  {
    auth_strategy: "devtron_session",
    auth_username: "admin",
    login_path: "/orchestrator/api/v1/session",
    probe_path: "/orchestrator/devtron/auth/verify/v2",
    apps_path: "/orchestrator/application?clusterIds=1",
  },
  null,
  2,
);

function defaultForm(kind: KubernetesProviderKind = "rancher"): ProviderForm {
  return {
    id: null,
    name: kind === "devtron" ? "devtron-main" : "rancher-main",
    kind,
    base_url: "",
    enabled: true,
    auth_mode: "secret_ref",
    secret_ref: kind === "devtron" ? "env:DEVTRON_TOKEN" : "env:RANCHER_TOKEN",
    secret_value: "",
    labels: kind === "devtron" ? DEVTRON_LABELS : RANCHER_LABELS,
  };
}

function providerToForm(provider: KubernetesProvider): ProviderForm {
  return {
    id: provider.id,
    name: provider.name,
    kind: provider.kind,
    base_url: provider.base_url,
    enabled: provider.enabled,
    auth_mode: provider.auth_mode,
    secret_ref: "",
    secret_value: "",
    labels: JSON.stringify(provider.labels || {}, null, 2),
  };
}

function parseLabels(raw: string): Record<string, unknown> {
  const text = raw.trim();
  if (!text) return {};
  const parsed = JSON.parse(text) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Labels JSON must be an object.");
  }
  return parsed as Record<string, unknown>;
}

function resultText(result: KubernetesSyncResult) {
  if (!result.success) return result.error || "Sync failed.";
  return `clusters=${result.clusters}, namespaces=${result.namespaces}, workloads=${result.workloads}, pods=${result.pods}, services=${result.services}, ingresses=${result.ingresses}, events=${result.events}, apps=${result.apps}, fleet=${result.fleet_bundles}`;
}

function probeText(result: KubernetesProviderProbeResult) {
  if (!result.success) return result.error || "Probe failed.";
  const keys = result.payload_keys.length ? ` keys=${result.payload_keys.join(",")}` : "";
  return `${result.path} responded in ${result.duration_ms}ms, items=${result.item_count}.${keys}`;
}

export function KubernetesProviderAdminPanel({
  providers,
  isAdmin,
  lang,
}: {
  providers: KubernetesProvider[];
  isAdmin: boolean;
  lang: string;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [form, setForm] = useState<ProviderForm>(() => defaultForm());
  const [lastResults, setLastResults] = useState<KubernetesSyncResult[]>([]);
  const [lastProbes, setLastProbes] = useState<KubernetesProviderProbeResult[]>([]);
  const editingProvider = useMemo(() => providers.find((provider) => provider.id === form.id) || null, [providers, form.id]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["kubernetes", "overview"] });
  };

  const createMutation = useMutation({
    mutationFn: createKubernetesProvider,
    onSuccess: async () => {
      await invalidate();
      setForm(defaultForm(form.kind));
      toast({ description: localize(lang, "Провайдер добавлен.", "Provider added.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<KubernetesProviderPayload> }) => updateKubernetesProvider(id, payload),
    onSuccess: async () => {
      await invalidate();
      toast({ description: localize(lang, "Провайдер обновлён.", "Provider updated.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteKubernetesProvider,
    onSuccess: async () => {
      await invalidate();
      setForm(defaultForm());
      toast({ description: localize(lang, "Провайдер удалён.", "Provider deleted.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const syncMutation = useMutation({
    mutationFn: ({ id, dryRun }: { id: number; dryRun: boolean }) => syncKubernetesProvider(id, { dry_run: dryRun }),
    onSuccess: async (result) => {
      setLastResults(result.results);
      await invalidate();
      toast({ description: result.success ? localize(lang, "Синхронизация завершена.", "Sync finished.") : localize(lang, "Синхронизация завершилась с ошибкой.", "Sync failed.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const probeMutation = useMutation({
    mutationFn: probeKubernetesProvider,
    onSuccess: (result) => {
      setLastProbes((items) => [result.probe, ...items.filter((item) => item.provider_id !== result.probe.provider_id)].slice(0, 4));
      toast({
        variant: result.success ? "default" : "destructive",
        description: result.success ? localize(lang, "Подключение проверено.", "Provider probe passed.") : result.probe.error || localize(lang, "Не удалось проверить подключение.", "Provider probe failed."),
      });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  if (!isAdmin) return null;

  const setKind = (kind: KubernetesProviderKind) => {
    setForm((state) => ({ ...defaultForm(kind), id: state.id, base_url: state.base_url, enabled: state.enabled }));
  };

  const saveProvider = () => {
    let labels: Record<string, unknown>;
    try {
      labels = parseLabels(form.labels);
    } catch (error) {
      toast({ variant: "destructive", description: error instanceof Error ? error.message : localize(lang, "JSON меток содержит ошибку.", "Labels JSON is invalid.") });
      return;
    }
    const payload: KubernetesProviderPayload = {
      name: form.name,
      kind: form.kind,
      base_url: form.base_url,
      enabled: form.enabled,
      auth_mode: form.auth_mode,
      labels,
      ...(form.secret_ref ? { secret_ref: form.secret_ref } : {}),
      ...(form.secret_value ? { secret_value: form.secret_value } : {}),
    };
    if (form.id) {
      updateMutation.mutate({ id: form.id, payload });
      return;
    }
    createMutation.mutate(payload);
  };

  return (
    <SectionCard
      title={localize(lang, "Настройка провайдеров", "Provider setup")}
      description={localize(lang, "Подключения, секреты и ручная синхронизация. Только для администраторов.", "Connections, secrets, and manual sync. Administrators only.")}
      icon={<CloudCog className="h-4 w-4" />}
      actions={<StatusBadge label={localize(lang, "администратор", "admin")} tone="info" />}
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input value={form.name} onChange={(event) => setForm((state) => ({ ...state, name: event.target.value }))} placeholder="rancher-main" aria-label={localize(lang, "Имя подключения", "Provider name")} />
            <Input value={form.base_url} onChange={(event) => setForm((state) => ({ ...state, base_url: event.target.value }))} placeholder="https://rancher.example" aria-label={localize(lang, "Базовый URL подключения", "Provider base URL")} />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Select value={form.kind} onValueChange={setKind}>
              <SelectTrigger aria-label={localize(lang, "Тип подключения", "Provider kind")}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="rancher">Rancher/Fleet</SelectItem>
                <SelectItem value="devtron">Devtron</SelectItem>
              </SelectContent>
            </Select>
            <Select value={form.auth_mode} onValueChange={(value) => setForm((state) => ({ ...state, auth_mode: value }))}>
              <SelectTrigger aria-label={localize(lang, "Способ входа", "Provider auth mode")}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="secret_ref">{localize(lang, "Ссылка на секрет", "Secret ref")}</SelectItem>
                <SelectItem value="oidc">OIDC</SelectItem>
                <SelectItem value="none">{localize(lang, "Без авторизации", "None")}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={form.enabled ? "enabled" : "disabled"} onValueChange={(value) => setForm((state) => ({ ...state, enabled: value === "enabled" }))}>
              <SelectTrigger aria-label={localize(lang, "Состояние подключения", "Provider enabled")}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="enabled">{localize(lang, "Включён", "Enabled")}</SelectItem>
                <SelectItem value="disabled">{localize(lang, "Выключен", "Disabled")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Input value={form.secret_ref} onChange={(event) => setForm((state) => ({ ...state, secret_ref: event.target.value }))} placeholder="env:RANCHER_TOKEN" aria-label={localize(lang, "Ссылка на секрет подключения", "Provider secret reference")} />
          <Input value={form.secret_value} type="password" onChange={(event) => setForm((state) => ({ ...state, secret_value: event.target.value }))} placeholder={localize(lang, "Новый защищённый токен", "Managed token for rotation")} aria-label={localize(lang, "Защищённый токен подключения", "Provider managed token")} />
          <Textarea value={form.labels} onChange={(event) => setForm((state) => ({ ...state, labels: event.target.value }))} className="min-h-[132px] font-mono text-xs" aria-label={localize(lang, "Метки подключения в JSON", "Provider labels JSON")} />
          <div className="flex flex-wrap gap-2">
            <Button onClick={saveProvider} disabled={createMutation.isPending || updateMutation.isPending} className="gap-2">
              {form.id ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              {form.id ? localize(lang, "Сохранить", "Save") : localize(lang, "Добавить", "Add")}
            </Button>
            <Button variant="outline" onClick={() => setForm(defaultForm())}>{localize(lang, "Новый", "New")}</Button>
            {form.id ? (
              <Button variant="outline" onClick={() => deleteMutation.mutate(form.id as number)} disabled={deleteMutation.isPending} className="gap-2">
                <Trash2 className="h-4 w-4" />
                {localize(lang, "Удалить", "Delete")}
              </Button>
            ) : null}
          </div>
        </div>

        <div className="space-y-3">
          {providers.map((provider) => (
            <div key={provider.id} className="rounded-lg border border-border/70 bg-background/45 px-4 py-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <button type="button" onClick={() => setForm(providerToForm(provider))} className="min-w-0 text-left">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">{provider.name}</span>
                    <StatusBadge label={provider.kind} tone="info" />
                    <StatusBadge label={provider.enabled ? localize(lang, "включено", "enabled") : localize(lang, "выключено", "disabled")} tone={provider.enabled ? "success" : "neutral"} />
                    <StatusBadge
                      label={provider.secret_storage === "managed"
                        ? localize(lang, "защищённый секрет", "managed secret")
                        : provider.secret_storage === "external"
                          ? localize(lang, "внешний секрет", "external secret")
                          : provider.secret_storage === "none"
                            ? localize(lang, "без секрета", "no secret")
                            : provider.secret_storage}
                      tone={provider.secret_storage === "managed" ? "success" : "neutral"}
                    />
                  </div>
                  <div className="mt-1 truncate font-mono text-xs text-muted-foreground">{provider.base_url}</div>
                </button>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => probeMutation.mutate(provider.id)} disabled={probeMutation.isPending} className="gap-2">
                    <Activity className="h-4 w-4" />
                    Probe
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => syncMutation.mutate({ id: provider.id, dryRun: true })} disabled={syncMutation.isPending} className="gap-2">
                    <Play className="h-4 w-4" />
                    Dry run
                  </Button>
                  <Button size="sm" onClick={() => syncMutation.mutate({ id: provider.id, dryRun: false })} disabled={syncMutation.isPending} className="gap-2">
                    <Play className="h-4 w-4" />
                    Sync
                  </Button>
                </div>
              </div>
            </div>
          ))}
          {!providers.length ? (
            <div className="rounded-lg border border-dashed border-border/70 bg-secondary/15 px-4 py-6 text-sm text-muted-foreground">
              {localize(lang, "Добавьте подключения Rancher и Devtron, затем проверьте синхронизацию.", "Add Rancher and Devtron connections, then test the sync.")}
            </div>
          ) : null}
          {editingProvider ? <div className="text-xs text-muted-foreground">{localize(lang, "Редактируется:", "Editing:")} {editingProvider.name}</div> : null}
          {lastResults.length ? (
            <div className="space-y-2">
              {lastResults.map((result) => (
                <div key={`${result.provider_id}-${result.dry_run}`} className="rounded-md border border-border/60 bg-secondary/20 px-3 py-2 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge label={result.success ? "ok" : "failed"} tone={result.success ? "success" : "danger"} />
                    <span className="font-semibold text-foreground">{result.provider_name}</span>
                  </div>
                  <div className="mt-1 text-muted-foreground">{resultText(result)}</div>
                </div>
              ))}
            </div>
          ) : null}
          {lastProbes.length ? (
            <div className="space-y-2">
              {lastProbes.map((result) => (
                <div key={`${result.provider_id}-${result.checked_at}`} className="rounded-md border border-border/60 bg-secondary/20 px-3 py-2 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge label={result.success ? "probe ok" : "probe failed"} tone={result.success ? "success" : "danger"} />
                    <span className="font-semibold text-foreground">{result.provider_name}</span>
                  </div>
                  <div className="mt-1 text-muted-foreground">{probeText(result)}</div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </SectionCard>
  );
}
