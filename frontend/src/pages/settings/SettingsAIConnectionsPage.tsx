import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, KeyRound, Link2, Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";

import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
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
  fetchAccessUsers,
  fetchAiProviderAuthFlow,
  fetchAiProviderCatalog,
  fetchAiProviderConnections,
  fetchAiProviderPools,
  fetchAiProviderPreferences,
  fetchAuthSession,
  revokeAiProviderConnection,
  saveAiProviderPreference,
  startAiProviderAuth,
  verifyAiProviderConnection,
  type AiProviderConnection,
  type AiPurpose,
  type AiSubscriptionTarget,
  type ProviderBinding,
} from "@/lib/api";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { localize, useI18n } from "@/lib/i18n";

const terminalAuthStatuses = new Set(["completed", "failed", "expired", "cancelled", "revoked"]);

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
  const usersQuery = useQuery({
    queryKey: ["access", "users"],
    queryFn: fetchAccessUsers,
    enabled: runtimeEnabled && canAdmin,
    retry: false,
  });

  const [name, setName] = useState("");
  const [target, setTarget] = useState<AiSubscriptionTarget>("codex_subscription");
  const [scope, setScope] = useState<"personal" | "workspace">("personal");
  const [authFlowId, setAuthFlowId] = useState("");
  const [draftPreferences, setDraftPreferences] = useState<Partial<Record<AiPurpose, string>>>({});
  const [poolName, setPoolName] = useState("");
  const [poolTarget, setPoolTarget] = useState<AiSubscriptionTarget>("codex_subscription");
  const [poolMembers, setPoolMembers] = useState<number[]>([]);
  const [grantConnectionId, setGrantConnectionId] = useState("");
  const [grantUserId, setGrantUserId] = useState("");
  const [grantUnattended, setGrantUnattended] = useState(false);
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

  const connections = useMemo(() => connectionsQuery.data?.connections ?? [], [connectionsQuery.data?.connections]);
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
    const response = await createAiProviderConnection({ target_id: target, scope: canAdmin ? scope : "personal", name: name.trim(), concurrency_limit: 1 });
    setName("");
    const auth = await startAiProviderAuth(response.connection.id);
    setAuthFlowId(auth.auth_flow.id);
  });

  const savePreference = (purpose: AiPurpose) => mutation.mutate(async () => {
    const selected = draftPreferences[purpose] || bindingKey(preferences.find((item) => item.purpose === purpose)?.binding);
    const option = bindingOptions.find((item) => item.key === selected);
    if (!option) throw new Error(text("Выберите доступное подключение", "Select an available connection"));
    await saveAiProviderPreference({
      purpose,
      binding: option.binding,
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
      <div className="space-y-5 pb-10">
        <SettingsPageHeader
          icon={KeyRound}
          title={text("CLI-подписки", "CLI subscriptions")}
          description={text(
            "Codex CLI и Grok CLI работают через изолированные подключения без скрытого fallback.",
            "Codex CLI and Grok CLI use isolated connections with no hidden fallback.",
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
                  "Для безопасного входа в Codex CLI или Grok CLI платформе нужен отдельный изолированный процесс с закреплённой версией. Сейчас он выключен, поэтому создание подключений и вход временно недоступны. Остальные функции WebTrerm продолжают работать.",
                  "Secure Codex CLI or Grok CLI sign-in requires an isolated runtime with a pinned version. It is currently disabled, so creating connections and signing in are temporarily unavailable. Other WebTrerm features continue to work.",
                )}
              </p>
            </div>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-5 pb-10">
      <SettingsPageHeader
        icon={KeyRound}
        title={text("CLI-подписки", "CLI subscriptions")}
        description={text(
          "Codex CLI и Grok CLI работают через изолированные подключения без скрытого fallback.",
          "Codex CLI and Grok CLI use isolated connections with no hidden fallback.",
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
          <section className="rounded-sm border border-border bg-card p-4" aria-labelledby="new-ai-connection-title">
            <div className="mb-4 flex items-center gap-2">
              <Plus className="h-4 w-4 text-primary" aria-hidden />
              <h2 id="new-ai-connection-title" className="font-semibold">{text("Новое подключение", "New connection")}</h2>
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_220px_180px_auto]">
              <div>
                <Label htmlFor="ai-connection-name" className="sr-only">{text("Название подключения", "Connection name")}</Label>
                <Input id="ai-connection-name" value={name} onChange={(event) => setName(event.target.value)} placeholder={text("Например, Мой Codex", "e.g. My Codex")} />
              </div>
              <Select value={target} onValueChange={(value) => setTarget(value as AiSubscriptionTarget)}>
                <SelectTrigger aria-label={text("CLI-провайдер", "CLI provider")}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="codex_subscription">Codex CLI</SelectItem><SelectItem value="grok_subscription">Grok CLI</SelectItem></SelectContent>
              </Select>
              <Select value={scope} onValueChange={(value) => setScope(value as "personal" | "workspace")} disabled={!canAdmin}>
                <SelectTrigger aria-label={text("Область подключения", "Connection scope")}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="personal">{text("Личное", "Personal")}</SelectItem>{canAdmin ? <SelectItem value="workspace">Workspace</SelectItem> : null}</SelectContent>
              </Select>
              <Button disabled={!name.trim() || mutation.isPending} onClick={createConnection}>{text("Подключить", "Connect")}</Button>
            </div>
          </section>

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
            <div className="border-b border-border px-4 py-3"><h2 id="connections-title" className="font-semibold">{text("Подключения", "Connections")}</h2></div>
            {connections.length ? connections.map((connection) => (
              <ConnectionRow
                key={connection.id}
                connection={connection}
                lang={lang}
                busy={mutation.isPending}
                onAuth={(id) => mutation.mutate(async () => { const result = await startAiProviderAuth(id); setAuthFlowId(result.auth_flow.id); })}
                onVerify={(id) => mutation.mutate(async () => {
                  const result = await verifyAiProviderConnection(id);
                  setAuthFlowId(result.auth_flow.id);
                })}
                onRevoke={(item) => setConfirmation({ kind: "connection", id: item.id, label: item.name })}
              />
            )) : <p className="px-4 py-8 text-center text-sm text-muted-foreground">{text("Подключений пока нет.", "No connections yet.")}</p>}
          </section>

          <section className="rounded-sm border border-border bg-card p-4" aria-labelledby="purpose-title">
            <div className="mb-4 flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" aria-hidden /><h2 id="purpose-title" className="font-semibold">{text("Провайдеры по назначению", "Providers by purpose")}</h2></div>
            <div className="grid gap-3 lg:grid-cols-2">
              {(Object.keys(purposeLabels) as AiPurpose[]).map((purpose) => {
                const saved = bindingKey(preferences.find((item) => item.purpose === purpose)?.binding);
                return <div key={purpose} className="rounded-sm border border-border/70 p-3">
                  <Label id={`purpose-${purpose}`}>{purposeLabels[purpose]}</Label>
                  <div className="mt-2 flex gap-2">
                    <Select value={draftPreferences[purpose] ?? saved} onValueChange={(value) => setDraftPreferences((current) => ({ ...current, [purpose]: value }))}>
                      <SelectTrigger aria-labelledby={`purpose-${purpose}`} className="min-w-0 flex-1"><SelectValue placeholder={text("Наследовать настройку workspace", "Inherit workspace setting")} /></SelectTrigger>
                      <SelectContent>{bindingOptions.map((option) => <SelectItem key={option.key} value={option.key}>{option.label}</SelectItem>)}</SelectContent>
                    </Select>
                    <Button variant="outline" disabled={mutation.isPending} onClick={() => savePreference(purpose)}>{text("Сохранить", "Save")}</Button>
                  </div>
                </div>;
              })}
            </div>
          </section>

          {canAdmin ? (
            <section className="space-y-4 rounded-sm border border-border bg-card p-4" aria-labelledby="workspace-ai-title">
              <div><h2 id="workspace-ai-title" className="font-semibold">{text("Workspace: пулы и явные гранты", "Workspace pools and explicit grants")}</h2><p className="mt-1 text-sm text-muted-foreground">{text("Workspace-подключение недоступно без явного гранта.", "A workspace connection is unavailable without an explicit grant.")}</p></div>
              <div className="grid gap-3 md:grid-cols-[1fr_220px_auto]">
                <Input aria-label={text("Название пула", "Pool name")} value={poolName} onChange={(event) => setPoolName(event.target.value)} placeholder={text("Название пула", "Pool name")} />
                <Select value={poolTarget} onValueChange={(value) => { setPoolTarget(value as AiSubscriptionTarget); setPoolMembers([]); }}><SelectTrigger aria-label={text("Провайдер пула", "Pool provider")}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="codex_subscription">Codex CLI</SelectItem><SelectItem value="grok_subscription">Grok CLI</SelectItem></SelectContent></Select>
                <Button disabled={!poolName.trim() || !poolMembers.length || mutation.isPending} onClick={() => mutation.mutate(async () => { await createAiProviderPool({ name: poolName.trim(), target_id: poolTarget, connection_ids: poolMembers }); setPoolName(""); setPoolMembers([]); })}>{text("Создать пул", "Create pool")}</Button>
              </div>
              <div className="flex flex-wrap gap-3">{workspaceConnections.filter((item) => item.target_id === poolTarget).map((item) => <label key={item.id} className="flex items-center gap-2 text-sm"><Checkbox checked={poolMembers.includes(item.id)} onCheckedChange={(checked) => setPoolMembers((current) => checked ? [...new Set([...current, item.id])] : current.filter((id) => id !== item.id))} />{item.name}</label>)}</div>
              {pools.length ? <div className="flex flex-wrap gap-2">{pools.map((pool) => <Badge key={pool.id} variant="outline">{pool.name}: {pool.members.length}</Badge>)}</div> : null}
              <div className="grid gap-3 border-t border-border pt-4 md:grid-cols-[1fr_1fr_auto_auto]">
                <Select value={grantConnectionId} onValueChange={setGrantConnectionId}><SelectTrigger aria-label={text("Workspace-подключение", "Workspace connection")}><SelectValue placeholder={text("Workspace-подключение", "Workspace connection")} /></SelectTrigger><SelectContent>{workspaceConnections.map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.name}</SelectItem>)}</SelectContent></Select>
                <Select value={grantUserId} onValueChange={setGrantUserId}><SelectTrigger aria-label={text("Пользователь", "User")}><SelectValue placeholder={text("Пользователь", "User")} /></SelectTrigger><SelectContent>{(usersQuery.data?.users ?? []).map((user) => <SelectItem key={user.id} value={String(user.id)}>{user.username}</SelectItem>)}</SelectContent></Select>
                <label className="flex items-center gap-2 text-sm"><Checkbox checked={grantUnattended} onCheckedChange={(checked) => setGrantUnattended(Boolean(checked))} />{text("Расписания", "Schedules")}</label>
                <Button disabled={!grantConnectionId || !grantUserId || mutation.isPending} onClick={() => mutation.mutate(() => createAiProviderGrant({ connection_id: Number(grantConnectionId), user_id: Number(grantUserId), allow_interactive: true, allow_unattended: grantUnattended }))}>{text("Выдать доступ", "Grant access")}</Button>
              </div>
              {workspaceConnections.flatMap((item) => item.grants ?? []).length ? <div className="space-y-2">{workspaceConnections.flatMap((item) => item.grants ?? []).map((grant) => {
                const label = grant.user?.username || grant.group?.name || grant.project?.name || `#${grant.id}`;
                return <div key={grant.id} className="flex items-center justify-between rounded-sm border border-border/60 px-3 py-2 text-sm"><span>{label} · {grant.allow_unattended ? "interactive + unattended" : "interactive"}</span><Button variant="ghost" size="sm" onClick={() => setConfirmation({ kind: "grant", id: grant.id, label })}>{text("Удалить", "Delete")}</Button></div>;
              })}</div> : null}
            </section>
          ) : null}
        </div>
      </QueryStateBlock>

      <AlertDialog open={Boolean(confirmation)} onOpenChange={(open) => { if (!open) setConfirmation(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmation?.kind === "connection" ? text("Отозвать подключение?", "Revoke connection?") : text("Удалить грант?", "Delete grant?")}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmation?.kind === "connection"
                ? text(`«${confirmation.label}» перестанет принимать новые запуски.`, `“${confirmation.label}” will stop accepting new runs.`)
                : text(`Доступ «${confirmation?.label ?? ""}» будет удалён.`, `Access for “${confirmation?.label ?? ""}” will be removed.`)}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{text("Отмена", "Cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDestructiveAction} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">{confirmation?.kind === "connection" ? text("Отозвать", "Revoke") : text("Удалить", "Delete")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function ConnectionRow({
  connection,
  lang,
  busy,
  onAuth,
  onVerify,
  onRevoke,
}: {
  connection: AiProviderConnection;
  lang: string;
  busy: boolean;
  onAuth: (id: number) => void;
  onVerify: (id: number) => void;
  onRevoke: (connection: AiProviderConnection) => void;
}) {
  const text = (ru: string, en: string) => localize(lang, ru, en);
  return (
    <div className="flex flex-col gap-3 border-b border-border/60 px-4 py-4 last:border-b-0 md:flex-row md:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{connection.name}</span><Badge variant={statusTone(connection.status)}>{connection.status}</Badge><Badge variant="outline">{connection.scope === "personal" ? text("личное", "personal") : "workspace"}</Badge></div>
        <p className="mt-1 text-sm text-muted-foreground">{targetLabel(connection.target_id)} · interactive: {connection.access.interactive ? text("да", "yes") : text("нет", "no")} · unattended: {connection.access.unattended ? text("да", "yes") : text("нет", "no")}</p>
        {connection.last_error_code ? <p className="mt-1 text-sm text-destructive">{connection.last_error_code}</p> : null}
      </div>
      {connection.manageable ? <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => onAuth(connection.id)}>{text("Войти", "Sign in")}</Button>
        <Button variant="outline" size="sm" disabled={busy || !["connected", "auth_required"].includes(connection.status)} onClick={() => onVerify(connection.id)}><RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden />{text("Проверить", "Verify")}</Button>
        <Button variant="destructive" size="sm" disabled={busy || connection.status === "revoked"} onClick={() => onRevoke(connection)}><Trash2 className="mr-2 h-3.5 w-3.5" aria-hidden />{text("Отозвать", "Revoke")}</Button>
      </div> : null}
    </div>
  );
}
