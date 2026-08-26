import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  CheckCircle2,
  LockKeyhole,
  PackageCheck,
  Plug,
  Power,
  PowerOff,
  Puzzle,
  RefreshCw,
  Send,
  ShieldCheck,
  Users,
} from "lucide-react";

import {
  disablePlugin,
  enablePlugin,
  fetchAuthSession,
  fetchInstalledPlugins,
  fetchPluginInstallationScope,
  fetchPluginCatalog,
  fetchPluginPermissions,
  grantPluginPermission,
  revokePluginPermission,
  runDemoPluginAction,
  updatePluginInstallationScope,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  MetricCard,
  MetricGrid,
  QueryStateBlock,
  SectionCard,
  StatusBadge,
} from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { PluginCatalogItem, PluginInstallation, PluginManifestSurfaceMap, PluginPermission } from "@/plugins/types";
import { PrivateCatalogPanel } from "./PrivateCatalogPanel";
import { PluginSettingsPanel } from "./PluginSettingsPanel";
import { PluginConnectorsPanel } from "./PluginConnectorsPanel";
import { PluginExtensionSurfacesPanel } from "./PluginExtensionSurfacesPanel";
import { PluginLifecyclePanel } from "./PluginLifecyclePanel";
import { PluginReviewQueuePanel } from "./PluginReviewQueuePanel";
import { LocalPackageInstallPanel } from "./LocalPackageInstallPanel";
import { PluginInstallationHealthBadge, PluginInstallationHealthNotice } from "./PluginInstallationHealth";

const DEMO_PLUGIN_ID = "webtrerm.demo-dashboard";

function riskTone(risk: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (risk === "dangerous" || risk === "secret_read") return "danger";
  if (risk.includes("write")) return "warning";
  if (risk === "read") return "success";
  return "info";
}

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "enabled" || status === "verified" || status === "builtin") return "success";
  if (status === "blocked" || status === "quarantined" || status === "invalid" || status === "rejected") return "danger";
  if (status === "pending" || status === "unsigned") return "warning";
  return "neutral";
}

function surfaceEntries(surfaces: PluginManifestSurfaceMap) {
  return Object.entries(surfaces || {})
    .map(([kind, items]) => ({ kind, count: Array.isArray(items) ? items.length : 0 }))
    .filter((item) => item.count > 0);
}

function PluginCard({
  installation,
  lang,
  selected,
  busy,
  onSelect,
  onEnable,
  onDisable,
}: {
  installation: PluginInstallation;
  lang: string;
  selected: boolean;
  busy: boolean;
  onSelect: () => void;
  onEnable: () => void;
  onDisable: () => void;
}) {
  const enabled = installation.status === "enabled";
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border bg-card px-4 py-4 text-left transition-colors hover:border-primary/50",
        selected ? "border-primary/45 ring-1 ring-primary/25" : "border-border/70",
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-foreground">{installation.package.name}</h3>
            <StatusBadge label={installation.status} tone={statusTone(installation.status)} />
          </div>
          <p className="text-xs text-muted-foreground">{installation.plugin_id}@{installation.package.version}</p>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{installation.package.source}</Badge>
            <Badge variant="outline">{installation.package.signature_status}</Badge>
            <Badge variant="secondary">{installation.package.publisher.name}</Badge>
            <Badge variant={installation.scope?.mode === "groups" ? "default" : "outline"}>
              {installation.scope?.mode === "groups"
                ? localize(lang, `${installation.scope.groups.length} групп`, `${installation.scope.groups.length} groups`)
                : localize(lang, "для всех", "global")}
            </Badge>
            <PluginInstallationHealthBadge installation={installation} />
          </div>
          <PluginInstallationHealthNotice installation={installation} />
        </div>
        <div className="flex shrink-0 flex-wrap gap-2" onClick={(event) => event.stopPropagation()}>
          {enabled ? (
            <Button size="sm" variant="secondary" onClick={onDisable} disabled={busy}>
              <PowerOff className="h-4 w-4" />
              {localize(lang, "Выключить", "Disable")}
            </Button>
          ) : (
            <Button size="sm" onClick={onEnable} disabled={busy}>
              <Power className="h-4 w-4" />
              {localize(lang, "Включить", "Enable")}
            </Button>
          )}
        </div>
      </div>
    </button>
  );
}

function PermissionRow({
  permission,
  lang,
  busy,
  onGrant,
  onRevoke,
}: {
  permission: PluginPermission;
  lang: string;
  busy: boolean;
  onGrant: () => void;
  onRevoke: () => void;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border/70 bg-secondary/15 px-4 py-3 md:flex-row md:items-center md:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="break-all font-mono text-xs font-semibold text-foreground">{permission.scope}</span>
          <StatusBadge label={permission.risk_tier} tone={riskTone(permission.risk_tier)} dot={false} />
          {permission.granted
            ? <StatusBadge label={localize(lang, "разрешено", "granted")} tone="success" />
            : <StatusBadge label={localize(lang, "не разрешено", "not granted")} tone="neutral" />}
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{permission.reason}</p>
      </div>
      {permission.granted ? (
        <Button size="sm" variant="secondary" onClick={onRevoke} disabled={busy}>
          <LockKeyhole className="h-4 w-4" />
          {localize(lang, "Отозвать", "Revoke")}
        </Button>
      ) : (
        <Button size="sm" variant="outline" onClick={onGrant} disabled={busy}>
          <ShieldCheck className="h-4 w-4" />
          {localize(lang, "Разрешить", "Grant")}
        </Button>
      )}
    </div>
  );
}

function AccessScopePanel({
  installation,
  lang,
  scope,
  availableGroups,
  busy,
  onGlobal,
  onToggleGroup,
}: {
  installation: PluginInstallation | null;
  lang: string;
  scope: PluginInstallation["scope"] | null;
  availableGroups: Array<{ id: number; name: string }>;
  busy: boolean;
  onGlobal: () => void;
  onToggleGroup: (groupId: number) => void;
}) {
  const groupIds = scope?.group_ids ?? [];
  return (
    <SectionCard
      title={localize(lang, "Доступ", "Access")}
      description={installation ? installation.plugin_id : localize(lang, "Выберите плагин.", "Select a plugin.")}
      icon={<Users className="h-4 w-4" />}
      actions={
        <Button size="sm" variant={groupIds.length ? "outline" : "secondary"} onClick={onGlobal} disabled={!installation || busy}>
          {localize(lang, "Для всех", "Global")}
        </Button>
      }
    >
      {!installation ? (
        <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
          {localize(lang, "Выберите плагин, чтобы настроить доступ.", "Select a plugin to configure access.")}
        </p>
      ) : availableGroups.length ? (
        <div className="grid gap-2 md:grid-cols-2">
          {availableGroups.map((group) => {
            const checked = groupIds.includes(group.id);
            return (
              <label
                key={group.id}
                className="flex min-h-11 items-center gap-3 rounded-lg border border-border/70 bg-secondary/15 px-3 py-2 text-sm"
              >
                <Checkbox checked={checked} onCheckedChange={() => onToggleGroup(group.id)} disabled={busy} />
                <span className="min-w-0 truncate text-foreground">{group.name}</span>
              </label>
            );
          })}
        </div>
      ) : (
        <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
          {localize(lang, "Групп доступа нет. Плагин доступен всем.", "No access groups exist. The plugin is available to everyone.")}
        </p>
      )}
    </SectionCard>
  );
}

function CatalogCard({ plugin, lang }: { plugin: PluginCatalogItem; lang: string }) {
  const surfaces = surfaceEntries(plugin.surfaces);
  return (
    <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{plugin.name}</h3>
            <StatusBadge label={plugin.enabled ? localize(lang, "включён", "enabled") : localize(lang, "выключен", "disabled")} tone={plugin.enabled ? "success" : "neutral"} />
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{plugin.summary}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <StatusBadge label={plugin.review_status} tone={statusTone(plugin.review_status)} />
          <StatusBadge label={plugin.signature_status} tone={statusTone(plugin.signature_status)} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {plugin.categories.map((category) => <Badge key={category} variant="secondary">{category}</Badge>)}
        <Badge variant="outline">{plugin.publisher.name}</Badge>
        <Badge variant="outline">{plugin.version}</Badge>
      </div>
      <div className="mt-3 rounded-lg border border-border/60 bg-secondary/15 px-3 py-2">
        {surfaces.length ? (
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {surfaces.map((surface) => (
              <span key={surface.kind} className="rounded-md bg-background/70 px-2 py-1">
                {surface.kind}: {surface.count}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">{localize(lang, "Доступные функции появятся после включения плагина.", "Available features will appear after the plugin is enabled.")}</p>
        )}
      </div>
    </div>
  );
}

export default function InstalledPluginsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const sessionQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = Boolean(sessionQuery.data?.user?.is_staff);

  const catalogQuery = useQuery({
    queryKey: ["plugins", "catalog"],
    queryFn: fetchPluginCatalog,
    enabled: isAdmin,
  });
  const installedQuery = useQuery({
    queryKey: ["plugins", "installed"],
    queryFn: fetchInstalledPlugins,
    enabled: isAdmin,
  });

  const installations = installedQuery.data?.installations ?? [];
  const activeInstallationId = selectedId ?? installations[0]?.id ?? null;
  const selectedInstallation = installations.find((item) => item.id === activeInstallationId) ?? null;

  const permissionsQuery = useQuery({
    queryKey: ["plugins", "permissions", activeInstallationId],
    queryFn: () => fetchPluginPermissions(activeInstallationId as number),
    enabled: isAdmin && Boolean(activeInstallationId),
  });
  const scopeQuery = useQuery({
    queryKey: ["plugins", "scope", activeInstallationId],
    queryFn: () => fetchPluginInstallationScope(activeInstallationId as number),
    enabled: isAdmin && Boolean(activeInstallationId),
  });

  const invalidatePlugins = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plugins", "catalog"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "installed"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "scope"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "surfaces"] }),
    ]);
  };

  const enableMutation = useMutation({
    mutationFn: enablePlugin,
    onSuccess: () => {
      invalidatePlugins();
      toast({ description: localize(lang, "Плагин включён.", "Plugin enabled.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const disableMutation = useMutation({
    mutationFn: disablePlugin,
    onSuccess: () => {
      invalidatePlugins();
      toast({ description: localize(lang, "Плагин выключен.", "Plugin disabled.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const grantMutation = useMutation({
    mutationFn: ({ installationId, scope }: { installationId: number; scope: string }) => grantPluginPermission(installationId, scope),
    onSuccess: () => {
      invalidatePlugins();
      toast({ description: localize(lang, "Разрешение выдано.", "Plugin permission granted.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const revokeMutation = useMutation({
    mutationFn: ({ installationId, scope }: { installationId: number; scope: string }) => revokePluginPermission(installationId, scope),
    onSuccess: () => {
      invalidatePlugins();
      toast({ description: localize(lang, "Разрешение отозвано.", "Plugin permission revoked.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const scopeMutation = useMutation({
    mutationFn: ({ installationId, groupIds }: { installationId: number; groupIds: number[] }) =>
      updatePluginInstallationScope(installationId, groupIds),
    onSuccess: () => {
      invalidatePlugins();
      toast({ description: localize(lang, "Доступ обновлён.", "Plugin access updated.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const demoMutation = useMutation({
    mutationFn: runDemoPluginAction,
    onSuccess: () => toast({ description: localize(lang, "Тестовое действие выполнено.", "Test action completed.") }),
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const permissions = permissionsQuery.data?.permissions ?? [];
  const demoPlugin = installations.find((item) => item.plugin_id === DEMO_PLUGIN_ID);
  const demoPermissionGranted = permissions.some((item) => item.scope === "demo.alerts.send" && item.granted);
  const summary = catalogQuery.data?.summary ?? { registered: 0, enabled: 0, disabled: 0 };
  const permissionCount = permissions.filter((item) => item.granted).length;
  const isBusy = enableMutation.isPending || disableMutation.isPending || grantMutation.isPending || revokeMutation.isPending || scopeMutation.isPending;

  const catalogPlugins = useMemo(() => catalogQuery.data?.plugins ?? [], [catalogQuery.data?.plugins]);
  const scope = scopeQuery.data?.scope ?? selectedInstallation?.scope ?? null;
  const availableGroups = scopeQuery.data?.available_groups ?? [];
  const scopeGroupIds = scope?.group_ids ?? [];

  if (sessionQuery.isLoading) return <QueryStateBlock loading>{null}</QueryStateBlock>;
  if (!isAdmin) return <Navigate to="/settings/ai" replace />;

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Puzzle className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">{localize(lang, "Плагины", "Plugins")}</h1>
            <p className="text-sm leading-6 text-muted-foreground">{localize(lang, "Установка, доступ и настройки расширений.", "Install, configure, and manage extension access.")}</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => invalidatePlugins()}>
          <RefreshCw className="h-4 w-4" />
          {localize(lang, "Обновить", "Refresh")}
        </Button>
      </div>

      <MetricGrid className="xl:grid-cols-3">
        <MetricCard label={localize(lang, "Установлено", "Installed")} value={summary.registered} icon={<Box className="h-5 w-5" />} />
        <MetricCard label={localize(lang, "Включено", "Enabled")} value={summary.enabled} tone="success" icon={<CheckCircle2 className="h-5 w-5" />} />
        <MetricCard label={localize(lang, "Разрешений", "Permissions")} value={permissionCount} tone="info" icon={<ShieldCheck className="h-5 w-5" />} />
      </MetricGrid>

      <QueryStateBlock loading={catalogQuery.isLoading || installedQuery.isLoading} error={catalogQuery.error || installedQuery.error}>
        <LocalPackageInstallPanel />

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <SectionCard title={localize(lang, "Установленные плагины", "Installed plugins")} description={localize(lang, "Новые плагины выключены по умолчанию. Разрешения выдаются отдельно.", "New plugins are disabled by default. Permissions are granted separately.")} icon={<PackageCheck className="h-4 w-4" />}>
            <div className="space-y-3">
              {installations.map((installation) => (
                <PluginCard
                  key={installation.id}
                  installation={installation}
                  lang={lang}
                  selected={installation.id === activeInstallationId}
                  busy={isBusy}
                  onSelect={() => setSelectedId(installation.id)}
                  onEnable={() => enableMutation.mutate(installation.id)}
                  onDisable={() => disableMutation.mutate(installation.id)}
                />
              ))}
            </div>
          </SectionCard>

          <SectionCard
            title={localize(lang, "Разрешения", "Permissions")}
            description={selectedInstallation ? selectedInstallation.plugin_id : localize(lang, "Выберите плагин.", "Select a plugin.")}
            icon={<LockKeyhole className="h-4 w-4" />}
            actions={
              <Button
                size="sm"
                onClick={() => demoMutation.mutate()}
                disabled={!demoPlugin || demoPlugin.status !== "enabled" || !demoPermissionGranted || demoMutation.isPending}
              >
                <Send className="h-4 w-4" />
                {localize(lang, "Проверить", "Test")}
              </Button>
            }
          >
            <QueryStateBlock loading={permissionsQuery.isLoading} error={permissionsQuery.error}>
              <div className="space-y-3">
                {permissions.length ? permissions.map((permission) => (
                  <PermissionRow
                    key={permission.scope}
                    permission={permission}
                    lang={lang}
                    busy={isBusy}
                    onGrant={() => selectedInstallation && grantMutation.mutate({ installationId: selectedInstallation.id, scope: permission.scope })}
                    onRevoke={() => selectedInstallation && revokeMutation.mutate({ installationId: selectedInstallation.id, scope: permission.scope })}
                  />
                )) : (
                  <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
                    {localize(lang, "Плагин не запрашивает дополнительных разрешений.", "This plugin does not request additional permissions.")}
                  </p>
                )}
              </div>
            </QueryStateBlock>
          </SectionCard>
        </div>

        <QueryStateBlock loading={scopeQuery.isLoading} error={scopeQuery.error}>
          <AccessScopePanel
            installation={selectedInstallation}
            lang={lang}
            scope={scope}
            availableGroups={availableGroups}
            busy={isBusy}
            onGlobal={() => selectedInstallation && scopeMutation.mutate({ installationId: selectedInstallation.id, groupIds: [] })}
            onToggleGroup={(groupId) => {
              if (!selectedInstallation) return;
              const nextGroupIds = scopeGroupIds.includes(groupId)
                ? scopeGroupIds.filter((item) => item !== groupId)
                : [...scopeGroupIds, groupId];
              scopeMutation.mutate({ installationId: selectedInstallation.id, groupIds: nextGroupIds });
            }}
          />
        </QueryStateBlock>

        <SectionCard title={localize(lang, "Функции плагинов", "Plugin features")} description={localize(lang, "Функции доступны только у включённых плагинов.", "Features are available only for enabled plugins.")} icon={<Plug className="h-4 w-4" />}>
          <div className="grid gap-3 lg:grid-cols-2">
            {catalogPlugins.map((plugin) => <CatalogCard key={plugin.id} plugin={plugin} lang={lang} />)}
          </div>
        </SectionCard>

        <PluginSettingsPanel installationId={activeInstallationId} />

        <PluginLifecyclePanel installationId={activeInstallationId} />

        <PluginConnectorsPanel />

        <PluginExtensionSurfacesPanel />

        <PluginReviewQueuePanel />

        <PrivateCatalogPanel />
      </QueryStateBlock>
    </div>
  );
}
