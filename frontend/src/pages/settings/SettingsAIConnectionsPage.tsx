import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, KeyRound, Link2, Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";

import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
import { SettingsPageShell } from "@/components/settings/SettingsPageShell";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { QueryStateBlock } from "@/components/ui/page-shell";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import {
  aiProviderQueryKeys,
  createAiProviderConnection,
  createAiProviderGrant,
  createAiProviderPool,
  deleteAiProviderGrant,
  fetchAiProviderAuthFlow,
  fetchAiProviderCatalog,
  fetchAiProviderConnections,
  fetchAiProviderPools,
  fetchAiProviderPreferences,
  fetchAiProviderPrincipals,
  fetchAuthSession,
  clearAiProviderPreference,
  revokeAiProviderConnection,
  saveAiProviderPreference,
  startAiProviderAuth,
  updateAiProviderConnection,
  updateAiProviderGrant,
  verifyAiProviderConnection,
  type AiProviderConnection,
  type AiProviderGrant,
  type AiReasoningEffort,
  type AiPurpose,
  type AiSubscriptionTarget,
  type ProviderBinding,
} from "@/lib/api";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { localize, useI18n } from "@/lib/i18n";

const terminalAuthStatuses = new Set(["completed", "failed", "expired", "cancelled", "revoked"]);
const CONCURRENCY_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8] as const;

function clampConcurrency(value: number | undefined): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 1;
  return Math.max(1, Math.min(8, Math.trunc(n)));
}

function bindingKey(binding: ProviderBinding | undefined): string {
  if (!binding) return "";
  if (binding.connection_id) return `connection:${binding.connection_id}`;
  if (binding.pool_id) return `pool:${binding.pool_id}`;
  return `target:${binding.target_id}`;
}

function statusTone(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "connected" || status === "completed") return "default";
  if (["revoked", "failed", "expired", "auth_required"].includes(status)) return "destructive";
  if (["pending_auth", "pending", "disabled"].includes(status)) return "secondary";
  return "outline";
}

function targetLabel(target: string): string {
  if (target === "codex_subscription") return "Codex CLI";
  if (target === "grok_subscription") return "Grok CLI";
  if (target === "cursor_subscription") return "Cursor CLI";
  if (target === "antigravity_subscription") return "Gemini Antigravity";
  return target;
}

type ConfirmationTarget =
  | { kind: "connection"; id: number; label: string }
  | { kind: "grant"; id: number; label: string };

export default function SettingsAIConnectionsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();
  const text = useCallback((ru: string, en: string) => localize(lang, ru, en), [lang]);

  const authQuery = useQuery({ queryKey: ["auth", "session"], queryFn: fetchAuthSession, staleTime: 60_000, retry: false });
  const canAdmin = hasFeatureAccess(authQuery.data?.user, "ai_connections_admin");
  const runtimeEnabled = authQuery.data?.user?.ai_cli_runtime_enabled === true;
  const connectionsQuery = useQuery({
    queryKey: aiProviderQueryKeys.connections,
    queryFn: fetchAiProviderConnections,
    enabled: runtimeEnabled,
    retry: false,
  });
  const poolsQuery = useQuery({
    queryKey: aiProviderQueryKeys.pools,
    queryFn: fetchAiProviderPools,
    enabled: runtimeEnabled && canAdmin,
    retry: false,
  });
  const preferencesQuery = useQuery({
    queryKey: aiProviderQueryKeys.preferences,
    queryFn: fetchAiProviderPreferences,
    enabled: runtimeEnabled,
    retry: false,
  });
  const catalogQuery = useQuery({
    queryKey: aiProviderQueryKeys.catalog,
    queryFn: fetchAiProviderCatalog,
    enabled: runtimeEnabled,
    retry: false,
  });
  const connections = useMemo(() => connectionsQuery.data?.connections ?? [], [connectionsQuery.data?.connections]);
  const canShareConnections = useMemo(
    () => connections.some((item) => item.manageable && item.status !== "revoked"),
    [connections],
  );
  const principalsQuery = useQuery({
    queryKey: [...aiProviderQueryKeys.all, "principals"],
    queryFn: fetchAiProviderPrincipals,
    enabled: runtimeEnabled && canShareConnections,
    retry: false,
  });

  const [name, setName] = useState("");
  const [target, setTarget] = useState<AiSubscriptionTarget>("codex_subscription");
  const [scope, setScope] = useState<"personal" | "workspace">("personal");
  const [concurrencyLimit, setConcurrencyLimit] = useState(1);
  const [authFlowId, setAuthFlowId] = useState("");
  const [draftPreferences, setDraftPreferences] = useState<Partial<Record<AiPurpose, string>>>({});
  const [draftModels, setDraftModels] = useState<Partial<Record<AiPurpose, string>>>({});
  const [draftReasoning, setDraftReasoning] = useState<Partial<Record<AiPurpose, AiReasoningEffort>>>({});
  const [poolName, setPoolName] = useState("");
  const [poolTarget, setPoolTarget] = useState<AiSubscriptionTarget>("codex_subscription");
  const [poolMembers, setPoolMembers] = useState<number[]>([]);
  const [grantConnectionId, setGrantConnectionId] = useState("");
  const [grantPrincipalKind, setGrantPrincipalKind] = useState<"user" | "group">("user");
  const [grantUserId, setGrantUserId] = useState("");
  const [grantGroupId, setGrantGroupId] = useState("");
  const [grantInteractive, setGrantInteractive] = useState(true);
  const [grantUnattended, setGrantUnattended] = useState(false);
  const [grantMaxSlots, setGrantMaxSlots] = useState<string>("unlimited");
  const [grantAssignDefault, setGrantAssignDefault] = useState(true);
  const [grantAssignPurposes, setGrantAssignPurposes] = useState<AiPurpose[]>(["assistant"]);
  const [grantAssignDrafts, setGrantAssignDrafts] = useState<Record<number, { source: string; purposes: AiPurpose[] }>>({});
  const [showRevoked, setShowRevoked] = useState(false);
  const [confirmation, setConfirmation] = useState<ConfirmationTarget | null>(null);
  const handledFlowState = useRef("");

  const authFlowQuery = useQuery({
    queryKey: aiProviderQueryKeys.authFlow(authFlowId),
    queryFn: () => fetchAiProviderAuthFlow(authFlowId),
    enabled: Boolean(authFlowId),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.auth_flow.status;
      return status && terminalAuthStatuses.has(status) ? false : 1_500;
    },
  });

  const refresh = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: aiProviderQueryKeys.connections }),
      queryClient.invalidateQueries({ queryKey: aiProviderQueryKeys.pools }),
      queryClient.invalidateQueries({ queryKey: aiProviderQueryKeys.preferences }),
    ]);
  }, [queryClient]);

  const mutation = useMutation({
    mutationFn: async (action: () => Promise<unknown>) => action(),
    onSuccess: refresh,
    onError: (error) => toast({
      title: text("Операция не выполнена", "Operation failed"),
      description: error instanceof Error ? error.message : String(error),
      variant: "destructive",
    }),
  });

  const activeFlow = authFlowQuery.data?.auth_flow;
  useEffect(() => {
    if (!activeFlow || !terminalAuthStatuses.has(activeFlow.status)) return;
    const stateKey = `${activeFlow.id}:${activeFlow.status}`;
    if (handledFlowState.current === stateKey) return;
    handledFlowState.current = stateKey;
    void refresh();
    if (activeFlow.status === "completed") {
      toast({ title: text("Подключение готово", "Connection ready") });
    }
  }, [activeFlow, refresh, text, toast]);

  const revokedConnections = connections.filter((item) => item.status === "revoked");
  const visibleConnections = showRevoked
    ? connections
    : connections.filter((item) => item.status !== "revoked");
  const shareableConnections = connections.filter((item) => item.manageable && item.status !== "revoked");
  const pools = useMemo(() => poolsQuery.data?.pools ?? [], [poolsQuery.data?.pools]);
  const preferences = useMemo(() => preferencesQuery.data?.preferences ?? [], [preferencesQuery.data?.preferences]);
  const platformTargets = useMemo(
    () => (catalogQuery.data?.targets ?? []).filter((item) => item.kind === "platform"),
    [catalogQuery.data?.targets],
  );
  const purposeLabels: Record<AiPurpose, string> = {
    assistant: text("Ассистент и чаты", "Assistant and chats"),
    agents: text("Агенты и расписания", "Agents and schedules"),
    terminal: text("AI в терминале", "Terminal AI"),
    internal: text("Внутренние AI-задачи", "Internal AI tasks"),
  };
  const reasoningLabels: Record<AiReasoningEffort, string> = {
    low: text("low · быстро", "low · fast"),
    medium: text("medium · баланс", "medium · balanced"),
    high: text("high · глубоко", "high · deep"),
    xhigh: text("xhigh · очень глубоко", "xhigh · extra deep"),
    max: text("max · максимум", "max · maximum"),
    ultra: text("ultra · максимум + делегирование", "ultra · maximum + delegation"),
  };
  const bindingOptions = useMemo(() => [
    ...connections.filter((item) => item.access.interactive).map((item) => ({
      key: `connection:${item.id}`,
      label: `${item.name} · ${targetLabel(item.target_id)}`,
      binding: { target_id: item.target_id, connection_id: item.id } as ProviderBinding,
    })),
    ...pools.map((item) => ({
      key: `pool:${item.id}`,
      label: `${item.name} · ${text("пул", "pool")}`,
      binding: { target_id: item.target_id, pool_id: item.id } as ProviderBinding,
    })),
    ...platformTargets.map((item) => ({
      key: `target:${item.id}`,
      label: `${item.label} · ${text("платформа", "platform")}`,
      binding: { target_id: item.id } as ProviderBinding,
    })),
  ], [connections, platformTargets, pools, text]);

  const createConnection = () => mutation.mutate(async () => {
    const response = await createAiProviderConnection({
      target_id: target,
      scope: canAdmin ? scope : "personal",
      name: name.trim(),
      concurrency_limit: clampConcurrency(concurrencyLimit),
    });
    setName("");
    setConcurrencyLimit(1);
    const auth = await startAiProviderAuth(response.connection.id);
    setAuthFlowId(auth.auth_flow.id);
  });

  const saveConcurrency = (connectionId: number, nextLimit: number) => mutation.mutate(async () => {
    await updateAiProviderConnection(connectionId, { concurrency_limit: clampConcurrency(nextLimit) });
    toast({
      title: text("Параллельность сохранена", "Concurrency saved"),
      description: text(
        `До ${clampConcurrency(nextLimit)} одновременных запросов к этому подключению.`,
        `Up to ${clampConcurrency(nextLimit)} concurrent requests on this connection.`,
      ),
    });
  });

  const saveScope = (connectionId: number, nextScope: "personal" | "workspace") => mutation.mutate(async () => {
    await updateAiProviderConnection(connectionId, { scope: nextScope });
    toast({
      title: text("Область сохранена", "Scope saved"),
      description: nextScope === "workspace"
        ? text(
          "Подключение стало workspace. Бывшему владельцу выдан грант; остальных добавьте ниже.",
          "Connection is now workspace. The former owner got a grant; add others below.",
        )
        : text(
          "Подключение стало личным. Гранты и участие в пулах сняты.",
          "Connection is now personal. Grants and pool memberships were cleared.",
        ),
    });
  });

  const parseGrantSlots = (value: string): number | null => {
    if (value === "unlimited") return null;
    return clampConcurrency(Number(value));
  };

  const createGrant = () => mutation.mutate(async () => {
    if (!grantConnectionId) throw new Error(text("Выберите подключение", "Select a connection"));
    if (!grantInteractive && !grantUnattended) {
      throw new Error(text("Включите interactive и/или расписания", "Enable interactive and/or schedules"));
    }
    if (grantPrincipalKind === "user" && !grantUserId) {
      throw new Error(text("Выберите пользователя", "Select a user"));
    }
    if (grantPrincipalKind === "group" && !grantGroupId) {
      throw new Error(text("Выберите группу", "Select a group"));
    }
    if (grantPrincipalKind === "user" && grantAssignDefault && !grantAssignPurposes.length) {
      throw new Error(text("Выберите хотя бы одно назначение", "Pick at least one purpose"));
    }
    const payload = {
      connection_id: Number(grantConnectionId),
      allow_interactive: grantInteractive,
      allow_unattended: grantUnattended,
      max_slots: parseGrantSlots(grantMaxSlots),
      ...(grantPrincipalKind === "user"
        ? { user_id: Number(grantUserId) }
        : { group_id: Number(grantGroupId) }),
      ...(grantPrincipalKind === "user" && grantAssignDefault
        ? { assign_preferences: { purposes: grantAssignPurposes, project_scoped: true } }
        : {}),
    };
    await createAiProviderGrant(payload);
    setGrantUserId("");
    setGrantGroupId("");
    setGrantMaxSlots("unlimited");
    setGrantInteractive(true);
    setGrantUnattended(false);
    setGrantAssignDefault(true);
    setGrantAssignPurposes(["assistant"]);
    toast({
      title: text("Доступ выдан", "Access granted"),
      description: grantAssignDefault && grantPrincipalKind === "user"
        ? text(
          "Grant выдан и провайдер назначен вместо дефолтного Grok API.",
          "Grant issued and provider assigned instead of default Grok API.",
        )
        : text(
          "Если подключение было личным — оно стало workspace.",
          "If the connection was personal, it is now workspace.",
        ),
    });
  });

  const saveGrantSlots = (grant: AiProviderGrant, next: string) => mutation.mutate(async () => {
    await updateAiProviderGrant(grant.id, { max_slots: parseGrantSlots(next) });
    toast({ title: text("Лимит слотов сохранён", "Slot limit saved") });
  });

  const platformAssignOptions = useMemo(
    () => (catalogQuery.data?.targets ?? []).filter((item) => item.kind === "platform"),
    [catalogQuery.data?.targets],
  );

  const resolveAssignBinding = (source: string, connection: AiProviderConnection): ProviderBinding => {
    if (source.startsWith("connection:")) {
      return { target_id: connection.target_id, connection_id: connection.id };
    }
    if (source.startsWith("platform:")) {
      return { target_id: source.slice("platform:".length) };
    }
    throw new Error(text("Выберите CLI или API", "Select CLI or API"));
  };

  const saveAssignedPreferences = (
    grant: AiProviderGrant,
    connection: AiProviderConnection,
  ) => mutation.mutate(async () => {
    if (!grant.user) throw new Error(text("Назначение только для пользователей", "Assignment is only for users"));
    const draft = grantAssignDrafts[grant.id] || {
      source: `connection:${connection.id}`,
      purposes: ["assistant"] as AiPurpose[],
    };
    if (!draft.purposes.length) throw new Error(text("Выберите назначения", "Pick purposes"));
    const binding = resolveAssignBinding(draft.source, connection);
    if (binding.connection_id == null && !canAdmin) {
      throw new Error(text("Platform API может назначить только admin", "Only admins can assign platform API"));
    }
    await saveAiProviderPreference({
      purposes: draft.purposes,
      target_user_id: grant.user.id,
      project_scoped: true,
      binding,
      require_unattended: draft.purposes.some((purpose) => purpose === "agents" || purpose === "internal"),
    });
    await queryClient.invalidateQueries({ queryKey: [...aiProviderQueryKeys.all, "assigned-prefs"] });
    toast({ title: text("Провайдер назначен", "Provider assigned") });
  });

  const clearAssignedPreferences = (grant: AiProviderGrant) => mutation.mutate(async () => {
    if (!grant.user) throw new Error(text("Сброс только для пользователей", "Clear is only for users"));
    const draft = grantAssignDrafts[grant.id];
    const purposes = draft?.purposes?.length
      ? draft.purposes
      : (["assistant", "agents", "terminal", "internal"] as AiPurpose[]);
    await clearAiProviderPreference({
      purposes,
      target_user_id: grant.user.id,
      project_scoped: true,
    });
    await queryClient.invalidateQueries({ queryKey: [...aiProviderQueryKeys.all, "assigned-prefs"] });
    toast({ title: text("Назначение сброшено", "Assignment cleared") });
  });

  const savePreference = (purpose: AiPurpose) => mutation.mutate(async () => {
    const savedPreference = preferences.find((item) => item.purpose === purpose);
    const selected = draftPreferences[purpose] || bindingKey(savedPreference?.binding);
    const option = bindingOptions.find((item) => item.key === selected);
    if (!option) throw new Error(text("Выберите доступное подключение", "Select an available connection"));
    const models = catalogQuery.data?.models_by_target?.[option.binding.target_id] ?? [];
    const modelId = models.length ? (draftModels[purpose] || savedPreference?.binding.model_id || models[0].id) : undefined;
    const model = models.find((item) => item.id === modelId);
    const supportsReasoning = Boolean(model?.reasoning_efforts?.length);
    const reasoningEffort = supportsReasoning
      ? (draftReasoning[purpose] || savedPreference?.binding.reasoning_effort || model?.default_reasoning_effort || undefined)
      : undefined;
    await saveAiProviderPreference({
      purpose,
      binding: {
        ...option.binding,
        model_id: modelId,
        ...(supportsReasoning && reasoningEffort ? { reasoning_effort: reasoningEffort } : {}),
      },
      project_scoped: true,
      require_unattended: purpose === "agents" || purpose === "internal",
    });
    toast({ title: text("Значение сохранено", "Preference saved"), description: purposeLabels[purpose] });
  });

  const confirmDestructiveAction = () => {
    const targetToDelete = confirmation;
    if (!targetToDelete) return;
    setConfirmation(null);
    mutation.mutate(() => targetToDelete.kind === "connection"
      ? revokeAiProviderConnection(targetToDelete.id)
      : deleteAiProviderGrant(targetToDelete.id));
  };

  const workspaceConnections = connections.filter((item) => item.scope === "workspace");
  const loading = connectionsQuery.isLoading || (canAdmin && poolsQuery.isLoading) || preferencesQuery.isLoading || catalogQuery.isLoading;
  const loadError = connectionsQuery.error || (canAdmin ? poolsQuery.error : null) || preferencesQuery.error || catalogQuery.error;

  if (!authQuery.isLoading && !runtimeEnabled) {
    return (
      <SettingsPageShell width="wide">
        <SettingsPageHeader
          icon={KeyRound}
          title={text("CLI-подписки", "CLI subscriptions")}
          description={text(
            "Codex CLI, Grok CLI и Cursor CLI работают через изолированные подключения без скрытого fallback.",
            "Codex CLI, Grok CLI, and Cursor CLI use isolated connections with no hidden fallback.",
          )}
          actions={<Badge variant="secondary">{text("Runtime не настроен", "Runtime not configured")}</Badge>}
        />
        <section className="rounded-sm border border-warning/40 bg-warning/5 p-5" role="status">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden />
            <div>
              <h2 className="font-semibold text-foreground">
                {text("Раздел доступен, но CLI-runtime ещё не запущен", "The page is available, but the CLI runtime is not running")}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                {text(
                  "Для безопасного входа в Codex CLI, Grok CLI или Cursor CLI платформе нужен отдельный изолированный процесс с закреплённой версией. Сейчас он выключен, поэтому создание подключений и вход временно недоступны. Остальные функции WebTrerm продолжают работать.",
                  "Secure Codex CLI, Grok CLI, or Cursor CLI sign-in requires an isolated runtime with a pinned version. It is currently disabled, so creating connections and signing in are temporarily unavailable. Other WebTrerm features continue to work.",
                )}
              </p>
            </div>
          </div>
        </section>
      </SettingsPageShell>
    );
  }

  return (
    <SettingsPageShell width="wide">
      <SettingsPageHeader
        icon={KeyRound}
        title={text("CLI-подписки", "CLI subscriptions")}
        description={text(
          "Codex CLI, Grok CLI и Cursor CLI работают через изолированные подключения без скрытого fallback.",
          "Codex CLI, Grok CLI, and Cursor CLI use isolated connections with no hidden fallback.",
        )}
        actions={<Badge variant="secondary">{text(`${connections.filter((item) => item.status === "connected").length} подключено`, `${connections.filter((item) => item.status === "connected").length} connected`)}</Badge>}
      />

      <QueryStateBlock
        loading={loading}
        error={loadError}
        loadingText={text("Загрузка подключений…", "Loading connections…")}
        errorText={text("Не удалось загрузить AI-подключения.", "Could not load AI connections.")}
        onRetry={() => void Promise.all([
          connectionsQuery.refetch(),
          ...(canAdmin ? [poolsQuery.refetch()] : []),
          preferencesQuery.refetch(),
          catalogQuery.refetch(),
        ])}
      >
        <div className="space-y-5">
          <SettingsSectionCard title={text("Новое подключение", "New connection")} icon={Plus}>
            <div className="grid gap-3 md:grid-cols-[1fr_200px_160px_140px_auto]">
              <div>
                <Label htmlFor="ai-connection-name" className="sr-only">{text("Название подключения", "Connection name")}</Label>
                <Input id="ai-connection-name" value={name} onChange={(event) => setName(event.target.value)} placeholder={text("Например, Мой Codex", "e.g. My Codex")} />
              </div>
              <Select value={target} onValueChange={(value) => setTarget(value as AiSubscriptionTarget)}>
                <SelectTrigger aria-label={text("CLI-провайдер", "CLI provider")}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="codex_subscription">Codex CLI</SelectItem><SelectItem value="grok_subscription">Grok CLI</SelectItem><SelectItem value="cursor_subscription">Cursor CLI</SelectItem><SelectItem value="antigravity_subscription">Gemini Antigravity</SelectItem></SelectContent>
              </Select>
              <Select value={scope} onValueChange={(value) => setScope(value as "personal" | "workspace")} disabled={!canAdmin}>
                <SelectTrigger aria-label={text("Область подключения", "Connection scope")}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="personal">{text("Личное", "Personal")}</SelectItem>{canAdmin ? <SelectItem value="workspace">Workspace</SelectItem> : null}</SelectContent>
              </Select>
              <Select
                value={String(concurrencyLimit)}
                onValueChange={(value) => setConcurrencyLimit(clampConcurrency(Number(value)))}
              >
                <SelectTrigger aria-label={text("Параллельные запросы", "Concurrent requests")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONCURRENCY_OPTIONS.map((value) => (
                    <SelectItem key={value} value={String(value)}>
                      {text(`${value} слот${value === 1 ? "" : value < 5 ? "а" : "ов"}`, `${value} slot${value === 1 ? "" : "s"}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button disabled={!name.trim() || mutation.isPending} onClick={createConnection}>{text("Подключить", "Connect")}</Button>
            </div>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              {text(
                "Параллельные запросы — сколько LLM-вызовов одновременно может держать это подключение (чат, Telegram, агенты). При нехватке слотов будет «no free execution slot».",
                "Concurrent requests — how many LLM calls this connection can hold at once (chat, Telegram, agents). When full you get “no free execution slot”.",
              )}
            </p>
          </SettingsSectionCard>

          {activeFlow ? (
            <section className="rounded-sm border border-primary/40 bg-primary/5 p-4" role="status" aria-live="polite" aria-labelledby="auth-flow-title">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 id="auth-flow-title" className="font-semibold">{text("Вход в CLI", "CLI sign-in")}: {activeFlow.status}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {activeFlow.status === "completed"
                      ? text("Авторизация завершена. Список подключений обновлён.", "Authorization completed. Connections were refreshed.")
                      : activeFlow.status === "failed" || activeFlow.status === "expired"
                        ? text("Авторизация не завершена. Запустите вход повторно.", "Authorization did not complete. Start sign-in again.")
                        : text("Откройте страницу входа и введите показанный код.", "Open the sign-in page and enter the displayed code.")}
                  </p>
                  {activeFlow.error_code ? <p className="mt-1 text-sm text-destructive">{activeFlow.error_code}</p> : null}
                </div>
                <div className="flex items-center gap-2">
                  {activeFlow.user_code ? <Badge variant="outline" className="font-mono text-base">{activeFlow.user_code}</Badge> : <Badge variant="secondary">{text("Ожидаем код…", "Waiting for code…")}</Badge>}
                  {activeFlow.verification_uri ? <Button asChild><a href={activeFlow.verification_uri} target="_blank" rel="noreferrer"><Link2 className="mr-2 h-4 w-4" aria-hidden />{text("Открыть вход", "Open sign-in")}</a></Button> : null}
                </div>
              </div>
            </section>
          ) : null}

          <section className="rounded-sm border border-border bg-card" aria-labelledby="connections-title">
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <h2 id="connections-title" className="text-base font-semibold">{text("Подключения", "Connections")}</h2>
              {revokedConnections.length ? (
                <Button variant="ghost" size="sm" onClick={() => setShowRevoked((current) => !current)}>
                  {showRevoked
                    ? text("Скрыть отозванные", "Hide revoked")
                    : text(`Показать отозванные (${revokedConnections.length})`, `Show revoked (${revokedConnections.length})`)}
                </Button>
              ) : null}
            </div>
            {visibleConnections.length ? visibleConnections.map((connection) => (
              <ConnectionRow
                key={connection.id}
                connection={connection}
                lang={lang}
                busy={mutation.isPending}
                canAdmin={canAdmin}
                onAuth={(id) => mutation.mutate(async () => { const result = await startAiProviderAuth(id); setAuthFlowId(result.auth_flow.id); })}
                onVerify={(id) => mutation.mutate(async () => {
                  const result = await verifyAiProviderConnection(id);
                  setAuthFlowId(result.auth_flow.id);
                })}
                onConcurrencyChange={saveConcurrency}
                onScopeChange={saveScope}
                onRevoke={(item) => setConfirmation({ kind: "connection", id: item.id, label: item.name })}
              />
            )) : <p className="px-4 py-8 text-center text-sm text-muted-foreground">{text("Активных подключений пока нет.", "No active connections yet.")}</p>}
          </section>

          <section className="rounded-sm border border-border bg-card p-4" aria-labelledby="purpose-title">
            <div className="mb-4"><div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" aria-hidden /><h2 id="purpose-title" className="text-base font-semibold">{text("Модель и режим по назначению", "Model and reasoning by purpose")}</h2></div><p className="mt-1 text-sm leading-6 text-muted-foreground">{text("Выберите подключение, модель Codex и глубину размышления отдельно для каждого сценария.", "Choose a connection, Codex model, and reasoning depth separately for each scenario.")}</p></div>
            <div className="grid gap-3">
              {(Object.keys(purposeLabels) as AiPurpose[]).map((purpose) => {
                const savedPreference = preferences.find((item) => item.purpose === purpose);
                const saved = bindingKey(savedPreference?.binding);
                const selectedKey = draftPreferences[purpose] ?? saved;
                const selectedBinding = bindingOptions.find((item) => item.key === selectedKey)?.binding;
                const models = catalogQuery.data?.models_by_target?.[selectedBinding?.target_id ?? ""] ?? [];
                const selectedModelId = draftModels[purpose] || savedPreference?.binding.model_id || models[0]?.id || "";
                const selectedModel = models.find((item) => item.id === selectedModelId);
                const supportsReasoning = Boolean(selectedModel?.reasoning_efforts?.length);
                const selectedReasoning = supportsReasoning
                  ? (draftReasoning[purpose]
                    || savedPreference?.binding.reasoning_effort
                    || selectedModel?.default_reasoning_effort
                    || "")
                  : "";
                return <div key={purpose} className="rounded-sm border border-border/70 p-3">
                  <Label id={`purpose-${purpose}`}>{purposeLabels[purpose]}</Label>
                  <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_160px_auto]">
                    <Select value={draftPreferences[purpose] ?? saved} onValueChange={(value) => {
                      setDraftPreferences((current) => ({ ...current, [purpose]: value }));
                      setDraftModels((current) => {
                        const { [purpose]: _removed, ...rest } = current;
                        return rest;
                      });
                      setDraftReasoning((current) => {
                        const { [purpose]: _removed, ...rest } = current;
                        return rest;
                      });
                    }}>
                      <SelectTrigger aria-labelledby={`purpose-${purpose}`} className="min-w-0 flex-1"><SelectValue placeholder={text("Наследовать настройку workspace", "Inherit workspace setting")} /></SelectTrigger>
                      <SelectContent>{bindingOptions.map((option) => <SelectItem key={option.key} value={option.key}>{option.label}</SelectItem>)}</SelectContent>
                    </Select>
                    {models.length ? <Select
                      value={selectedModelId}
                      onValueChange={(value) => {
                        const nextModel = models.find((item) => item.id === value);
                        setDraftModels((current) => ({ ...current, [purpose]: value }));
                        if (nextModel?.reasoning_efforts?.length && nextModel.default_reasoning_effort) {
                          setDraftReasoning((current) => ({ ...current, [purpose]: nextModel.default_reasoning_effort }));
                        } else {
                          setDraftReasoning((current) => {
                            const { [purpose]: _removed, ...rest } = current;
                            return rest;
                          });
                        }
                      }}
                    >
                      <SelectTrigger aria-label={`${purposeLabels[purpose]} · ${text("модель", "model")}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{models.map((model) => <SelectItem key={model.id} value={model.id}>{model.label}{model.deprecated ? ` · ${text("устаревает", "deprecated")}` : ""}</SelectItem>)}</SelectContent>
                    </Select> : <div className="hidden sm:block" />}
                    {supportsReasoning && selectedModel ? <Select value={selectedReasoning} onValueChange={(value) => setDraftReasoning((current) => ({ ...current, [purpose]: value as AiReasoningEffort }))}>
                      <SelectTrigger aria-label={`${purposeLabels[purpose]} · ${text("размышление", "reasoning")}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{selectedModel.reasoning_efforts.map((effort) => <SelectItem key={effort} value={effort}>{reasoningLabels[effort]}</SelectItem>)}</SelectContent>
                    </Select> : <div className="hidden sm:block" />}
                    <Button variant="outline" disabled={mutation.isPending} onClick={() => savePreference(purpose)}>{text("Сохранить", "Save")}</Button>
                  </div>
                </div>;
              })}
            </div>
          </section>

          {canShareConnections ? (
            <SettingsSectionCard
              icon={ShieldCheck}
              title={text("Доступ", "Access")}
              description={text(
                "Grant даёт право пользоваться CLI. Отдельно назначьте CLI или API — иначе у пользователя останется дефолтный Grok API.",
                "A grant unlocks CLI access. Separately assign CLI or API — otherwise the user keeps the default Grok API.",
              )}
            >
              <div className="grid gap-3 md:grid-cols-[1fr_140px_1fr_140px]">
                <Select value={grantConnectionId} onValueChange={setGrantConnectionId}>
                  <SelectTrigger aria-label={text("Подключение", "Connection")}>
                    <SelectValue placeholder={text("Подключение", "Connection")} />
                  </SelectTrigger>
                  <SelectContent>
                    {shareableConnections.map((item) => (
                      <SelectItem key={item.id} value={String(item.id)}>
                        {item.name}
                        {item.scope === "personal" ? ` · ${text("личное", "personal")}` : " · workspace"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={grantPrincipalKind}
                  onValueChange={(value) => {
                    setGrantPrincipalKind(value as "user" | "group");
                    setGrantUserId("");
                    setGrantGroupId("");
                  }}
                >
                  <SelectTrigger aria-label={text("Кому выдать", "Grant to")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="user">{text("Пользователь", "User")}</SelectItem>
                    <SelectItem value="group">{text("Группа", "Group")}</SelectItem>
                  </SelectContent>
                </Select>
                {grantPrincipalKind === "user" ? (
                  <Select value={grantUserId || undefined} onValueChange={setGrantUserId}>
                    <SelectTrigger aria-label={text("Пользователь", "User")}>
                      <SelectValue placeholder={
                        principalsQuery.isLoading
                          ? text("Загрузка…", "Loading…")
                          : principalsQuery.isError
                            ? text("Не удалось загрузить", "Failed to load")
                            : text("Выберите пользователя", "Select user")
                      } />
                    </SelectTrigger>
                    <SelectContent>
                      {(principalsQuery.data?.users ?? []).map((user) => (
                        <SelectItem key={user.id} value={String(user.id)}>{user.username}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Select value={grantGroupId || undefined} onValueChange={setGrantGroupId}>
                    <SelectTrigger aria-label={text("Группа", "Group")}>
                      <SelectValue placeholder={
                        principalsQuery.isLoading
                          ? text("Загрузка…", "Loading…")
                          : principalsQuery.isError
                            ? text("Не удалось загрузить", "Failed to load")
                            : text("Выберите группу", "Select group")
                      } />
                    </SelectTrigger>
                    <SelectContent>
                      {(principalsQuery.data?.groups ?? []).map((group) => (
                        <SelectItem key={group.id} value={String(group.id)}>{group.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <Select value={grantMaxSlots} onValueChange={setGrantMaxSlots}>
                  <SelectTrigger aria-label={text("Лимит слотов", "Slot limit")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="unlimited">{text("Без лимита", "Unlimited")}</SelectItem>
                    {CONCURRENCY_OPTIONS.map((value) => (
                      <SelectItem key={value} value={String(value)}>
                        {text(`${value} слот${value === 1 ? "" : value < 5 ? "а" : "ов"}`, `${value} slot${value === 1 ? "" : "s"}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={grantInteractive} onCheckedChange={(checked) => setGrantInteractive(Boolean(checked))} />
                  {text("Чат / interactive", "Chat / interactive")}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={grantUnattended} onCheckedChange={(checked) => setGrantUnattended(Boolean(checked))} />
                  {text("Расписания / unattended", "Schedules / unattended")}
                </label>
                {grantPrincipalKind === "user" ? (
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={grantAssignDefault}
                      onCheckedChange={(checked) => setGrantAssignDefault(Boolean(checked))}
                    />
                    {text("Назначить провайдером", "Assign as provider")}
                  </label>
                ) : null}
                <Button
                  disabled={
                    !grantConnectionId
                    || mutation.isPending
                    || principalsQuery.isError
                    || (grantPrincipalKind === "user" ? !grantUserId : !grantGroupId)
                  }
                  onClick={createGrant}
                >
                  {text("Выдать доступ", "Grant access")}
                </Button>
              </div>
              {grantPrincipalKind === "user" && grantAssignDefault ? (
                <div className="mt-3 flex flex-wrap gap-3 text-sm">
                  {(Object.keys(purposeLabels) as AiPurpose[]).map((purpose) => (
                    <label key={purpose} className="flex items-center gap-2">
                      <Checkbox
                        checked={grantAssignPurposes.includes(purpose)}
                        onCheckedChange={(checked) => {
                          setGrantAssignPurposes((current) => (
                            checked
                              ? [...new Set([...current, purpose])]
                              : current.filter((item) => item !== purpose)
                          ));
                        }}
                      />
                      {purposeLabels[purpose]}
                    </label>
                  ))}
                </div>
              ) : null}
              {principalsQuery.isError ? (
                <p className="mt-3 text-sm text-destructive">
                  {text(
                    "Не удалось загрузить список пользователей и групп. Обновите страницу.",
                    "Could not load users and groups. Refresh the page.",
                  )}
                </p>
              ) : null}
              {connections.flatMap((item) => item.grants ?? []).length ? (
                <div className="mt-4 space-y-2 border-t border-border pt-4">
                  {connections.flatMap((item) => (item.grants ?? []).map((grant) => {
                    const label = grant.user?.username || grant.group?.name || grant.project?.name || `#${grant.id}`;
                    const kind = grant.user ? text("пользователь", "user") : grant.group ? text("группа", "group") : "project";
                    const modes = [
                      grant.allow_interactive ? "interactive" : null,
                      grant.allow_unattended ? "unattended" : null,
                    ].filter(Boolean).join(" + ") || "—";
                    const slotsValue = grant.max_slots == null ? "unlimited" : String(grant.max_slots);
                    const draft = grantAssignDrafts[grant.id] || {
                      source: `connection:${item.id}`,
                      purposes: ["assistant"] as AiPurpose[],
                    };
                    return (
                      <div
                        key={grant.id}
                        className="space-y-2 rounded-sm border border-border/60 px-3 py-2 text-sm"
                      >
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <div className="min-w-0">
                            <div className="font-medium">{label}</div>
                            <div className="text-xs text-muted-foreground">
                              {item.name} · {kind} · {modes}
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Select
                              value={slotsValue}
                              onValueChange={(value) => {
                                if (value === slotsValue) return;
                                saveGrantSlots(grant, value);
                              }}
                              disabled={mutation.isPending}
                            >
                              <SelectTrigger
                                className="h-8 w-[140px]"
                                aria-label={text(`Слоты · ${label}`, `Slots · ${label}`)}
                              >
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="unlimited">{text("Без лимита", "Unlimited")}</SelectItem>
                                {CONCURRENCY_OPTIONS.map((value) => (
                                  <SelectItem key={value} value={String(value)}>
                                    {text(`${value} слот${value === 1 ? "" : value < 5 ? "а" : "ов"}`, `${value} slot${value === 1 ? "" : "s"}`)}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <Button variant="ghost" size="sm" onClick={() => setConfirmation({ kind: "grant", id: grant.id, label })}>
                              {text("Удалить", "Delete")}
                            </Button>
                          </div>
                        </div>
                        {grant.user ? (
                          <div className="flex flex-col gap-2 border-t border-border/40 pt-2">
                            <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                              <Select
                                value={draft.source}
                                onValueChange={(value) => {
                                  setGrantAssignDrafts((current) => ({
                                    ...current,
                                    [grant.id]: { ...draft, source: value },
                                  }));
                                }}
                              >
                                <SelectTrigger aria-label={text(`Источник · ${label}`, `Source · ${label}`)}>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value={`connection:${item.id}`}>
                                    {text(`CLI · ${item.name}`, `CLI · ${item.name}`)}
                                  </SelectItem>
                                  {canAdmin
                                    ? platformAssignOptions.map((target) => (
                                      <SelectItem key={target.id} value={`platform:${target.id}`}>
                                        {text(`API · ${target.label}`, `API · ${target.label}`)}
                                      </SelectItem>
                                    ))
                                    : null}
                                </SelectContent>
                              </Select>
                              <div className="flex flex-wrap gap-2">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  disabled={mutation.isPending}
                                  onClick={() => saveAssignedPreferences(grant, item)}
                                >
                                  {text("Сохранить назначение", "Save assignment")}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={mutation.isPending}
                                  onClick={() => clearAssignedPreferences(grant)}
                                >
                                  {text("Сбросить", "Clear")}
                                </Button>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-3">
                              {(Object.keys(purposeLabels) as AiPurpose[]).map((purpose) => (
                                <label key={`${grant.id}-${purpose}`} className="flex items-center gap-2 text-xs">
                                  <Checkbox
                                    checked={draft.purposes.includes(purpose)}
                                    onCheckedChange={(checked) => {
                                      setGrantAssignDrafts((current) => ({
                                        ...current,
                                        [grant.id]: {
                                          ...draft,
                                          purposes: checked
                                            ? [...new Set([...draft.purposes, purpose])]
                                            : draft.purposes.filter((itemPurpose) => itemPurpose !== purpose),
                                        },
                                      }));
                                    }}
                                  />
                                  {purposeLabels[purpose]}
                                </label>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground">
                            {text(
                              "Назначение CLI/API доступно только для пользователей (не для групп).",
                              "CLI/API assignment is available for users only (not groups).",
                            )}
                          </p>
                        )}
                      </div>
                    );
                  }))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-muted-foreground">
                  {text("Пока никому не выдано. Выберите подключение и пользователя или группу.", "No grants yet. Pick a connection and a user or group.")}
                </p>
              )}
            </SettingsSectionCard>
          ) : null}

          {canAdmin ? (
            <section className="space-y-4 rounded-sm border border-border bg-card p-4" aria-labelledby="workspace-ai-title">
              <div><h2 id="workspace-ai-title" className="text-base font-semibold">{text("Workspace: пулы", "Workspace pools")}</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">{text("Несколько workspace-подключений одного провайдера в одном пуле.", "Several workspace connections for one provider in a single pool.")}</p></div>
              <div className="grid gap-3 md:grid-cols-[1fr_220px_auto]">
                <Input aria-label={text("Название пула", "Pool name")} value={poolName} onChange={(event) => setPoolName(event.target.value)} placeholder={text("Название пула", "Pool name")} />
                <Select value={poolTarget} onValueChange={(value) => { setPoolTarget(value as AiSubscriptionTarget); setPoolMembers([]); }}><SelectTrigger aria-label={text("Провайдер пула", "Pool provider")}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="codex_subscription">Codex CLI</SelectItem><SelectItem value="grok_subscription">Grok CLI</SelectItem><SelectItem value="cursor_subscription">Cursor CLI</SelectItem><SelectItem value="antigravity_subscription">Gemini Antigravity</SelectItem></SelectContent></Select>
                <Button disabled={!poolName.trim() || !poolMembers.length || mutation.isPending} onClick={() => mutation.mutate(async () => { await createAiProviderPool({ name: poolName.trim(), target_id: poolTarget, connection_ids: poolMembers }); setPoolName(""); setPoolMembers([]); })}>{text("Создать пул", "Create pool")}</Button>
              </div>
              <div className="flex flex-wrap gap-3">{workspaceConnections.filter((item) => item.target_id === poolTarget).map((item) => <label key={item.id} className="flex items-center gap-2 text-sm"><Checkbox checked={poolMembers.includes(item.id)} onCheckedChange={(checked) => setPoolMembers((current) => checked ? [...new Set([...current, item.id])] : current.filter((id) => id !== item.id))} />{item.name}</label>)}</div>
              {pools.length ? <div className="flex flex-wrap gap-2">{pools.map((pool) => <Badge key={pool.id} variant="outline">{pool.name}: {pool.members.length}</Badge>)}</div> : null}
            </section>
          ) : null}
        </div>
      </QueryStateBlock>

      <AlertDialog open={Boolean(confirmation)} onOpenChange={(open) => { if (!open) setConfirmation(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmation?.kind === "connection" ? text("Удалить подключение?", "Delete connection?") : text("Удалить грант?", "Delete grant?")}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmation?.kind === "connection"
                ? text(`«${confirmation.label}» будет отозвано и удалено без возможности восстановления.`, `“${confirmation.label}” will be revoked and permanently deleted.`)
                : text(`Доступ «${confirmation?.label ?? ""}» будет удалён.`, `Access for “${confirmation?.label ?? ""}” will be removed.`)}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{text("Отмена", "Cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDestructiveAction} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">{text("Удалить", "Delete")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsPageShell>
  );
}

function ConnectionRow({
  connection,
  lang,
  busy,
  canAdmin,
  onAuth,
  onVerify,
  onConcurrencyChange,
  onScopeChange,
  onRevoke,
}: {
  connection: AiProviderConnection;
  lang: string;
  busy: boolean;
  canAdmin: boolean;
  onAuth: (id: number) => void;
  onVerify: (id: number) => void;
  onConcurrencyChange: (connectionId: number, limit: number) => void;
  onScopeChange: (connectionId: number, scope: "personal" | "workspace") => void;
  onRevoke: (connection: AiProviderConnection) => void;
}) {
  const text = (ru: string, en: string) => localize(lang, ru, en);
  const limit = clampConcurrency(connection.concurrency_limit);
  return (
    <div className="flex flex-col gap-3 border-b border-border/60 px-4 py-4 last:border-b-0 md:flex-row md:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-base font-medium">{connection.name}</span>
          <Badge variant={statusTone(connection.status)}>{connection.status}</Badge>
          <Badge variant="outline">{connection.scope === "personal" ? text("личное", "personal") : "workspace"}</Badge>
          <Badge variant="secondary">
            {text(`${limit} слот${limit === 1 ? "" : limit < 5 ? "а" : "ов"}`, `${limit} slot${limit === 1 ? "" : "s"}`)}
          </Badge>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {targetLabel(connection.target_id)} · interactive: {connection.access.interactive ? text("да", "yes") : text("нет", "no")} · unattended: {connection.access.unattended ? text("да", "yes") : text("нет", "no")}
        </p>
        {connection.last_error_code ? <p className="mt-1 text-sm text-destructive">{connection.last_error_code}</p> : null}
      </div>
      {connection.manageable ? (
        <div className="flex flex-wrap items-center gap-2">
          {canAdmin ? (
            <Select
              value={connection.scope}
              onValueChange={(value) => {
                const next = value as "personal" | "workspace";
                if (next === connection.scope) return;
                onScopeChange(connection.id, next);
              }}
              disabled={busy || connection.status === "revoked"}
            >
              <SelectTrigger
                className="h-8 w-[140px]"
                aria-label={text(`Область · ${connection.name}`, `Scope · ${connection.name}`)}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="personal">{text("Личное", "Personal")}</SelectItem>
                <SelectItem value="workspace">Workspace</SelectItem>
              </SelectContent>
            </Select>
          ) : null}
          <Select
            value={String(limit)}
            onValueChange={(value) => {
              const next = clampConcurrency(Number(value));
              if (next === limit) return;
              onConcurrencyChange(connection.id, next);
            }}
            disabled={busy || connection.status === "revoked"}
          >
            <SelectTrigger
              className="h-8 w-[132px]"
              aria-label={text(`Параллельность · ${connection.name}`, `Concurrency · ${connection.name}`)}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CONCURRENCY_OPTIONS.map((value) => (
                <SelectItem key={value} value={String(value)}>
                  {text(`${value} слот${value === 1 ? "" : value < 5 ? "а" : "ов"}`, `${value} slot${value === 1 ? "" : "s"}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => onAuth(connection.id)}>{text("Войти", "Sign in")}</Button>
          <Button variant="outline" size="sm" disabled={busy || !["connected", "auth_required"].includes(connection.status)} onClick={() => onVerify(connection.id)}><RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden />{text("Проверить", "Verify")}</Button>
          <Button variant="destructive" size="sm" disabled={busy || connection.status === "revoked"} onClick={() => onRevoke(connection)}><Trash2 className="mr-2 h-3.5 w-3.5" aria-hidden />{text("Удалить", "Delete")}</Button>
        </div>
      ) : null}
    </div>
  );
}
