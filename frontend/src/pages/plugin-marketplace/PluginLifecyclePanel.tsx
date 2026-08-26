import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, RotateCcw, ShieldAlert, Trash2 } from "lucide-react";

import { fetchPluginLifecycleImpact, rollbackPlugin, softUninstallPlugin } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";

function tone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "enabled" || status === "verified" || status === "signed" || status === "builtin") return "success";
  if (status === "blocked" || status === "quarantined" || status === "invalid" || status === "rejected") return "danger";
  if (status === "pending" || status === "unsigned") return "warning";
  return "neutral";
}

function surfaceLabel(lang: string, kind: string) {
  const labels: Record<string, [string, string]> = {
    pages: ["страницы", "pages"],
    dashboard_widgets: ["виджеты обзора", "dashboard widgets"],
    connectors: ["подключения", "connectors"],
    studio_nodes: ["шаги Студии", "Studio nodes"],
    agent_tools: ["инструменты агентов", "agent tools"],
    terminal_actions: ["действия терминала", "terminal actions"],
    hooks: ["обработчики", "hooks"],
  };
  const label = labels[kind];
  return label ? localize(lang, label[0], label[1]) : kind.replaceAll("_", " ");
}

function providerLabel(lang: string, provider: string) {
  const labels: Record<string, [string, string]> = {
    disabled: ["отключена", "disabled"],
    local_subprocess: ["локальный процесс", "local process"],
    docker_runner: ["изолированный контейнер", "isolated container"],
    external_worker: ["внешний исполнитель", "external worker"],
  };
  const label = labels[provider];
  return label ? localize(lang, label[0], label[1]) : provider.replaceAll("_", " ");
}

function lifecycleStatusLabel(lang: string, status: string) {
  const labels: Record<string, [string, string]> = {
    enabled: ["включён", "enabled"],
    verified: ["проверен", "verified"],
    signed: ["подписан", "signed"],
    builtin: ["встроенный", "built in"],
    blocked: ["заблокирован", "blocked"],
    quarantined: ["в карантине", "quarantined"],
    invalid: ["некорректен", "invalid"],
    rejected: ["отклонён", "rejected"],
    pending: ["ожидает", "pending"],
    unsigned: ["без подписи", "unsigned"],
  };
  const label = labels[status];
  return label ? localize(lang, label[0], label[1]) : status.replaceAll("_", " ");
}

function CountGrid({ counts, lang }: { counts: Record<string, number>; lang: string }) {
  const entries = Object.entries(counts).filter(([, count]) => count > 0);
  if (!entries.length) {
    return <p className="text-xs text-muted-foreground">{localize(lang, "Точки интерфейса не заявлены.", "No interface surfaces declared.")}</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([kind, count]) => (
        <Badge key={kind} variant="outline">{surfaceLabel(lang, kind)}: {count}</Badge>
      ))}
    </div>
  );
}

export function PluginLifecyclePanel({ installationId }: { installationId: number | null }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();
  const impactQuery = useQuery({
    queryKey: ["plugins", "impact", installationId],
    queryFn: () => fetchPluginLifecycleImpact(installationId as number),
    enabled: Boolean(installationId),
  });
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plugins", "catalog"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "installed"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "impact"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "surfaces"] }),
    ]);
  };
  const softUninstall = useMutation({
    mutationFn: () => softUninstallPlugin(installationId as number),
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Плагин отключён и помечен удалённым.", "Plugin soft-uninstalled.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const rollback = useMutation({
    mutationFn: () => rollbackPlugin(installationId as number),
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Плагин возвращён к предыдущему пакету.", "Plugin rolled back to the previous package.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const impact = impactQuery.data?.impact;
  const sandboxPolicy = impact?.package.sandbox_policy as {
    required?: boolean;
    allowed?: boolean;
    blockers?: string[];
    requirements?: Array<Record<string, unknown>>;
    settings?: { backend_execution_provider?: string };
  } | undefined;
  const backendExecutionProvider = sandboxPolicy?.settings?.backend_execution_provider ?? "disabled";
  const privilegedLocalExecution = backendExecutionProvider === "local_subprocess";

  return (
    <SectionCard
      title={localize(lang, "Изменения при отключении", "Lifecycle impact")}
      description={localize(lang, "Показывает блокировки, исчезающие разделы и обратимые действия.", "Enable blockers, disappearing surfaces, missing permissions, and reversible operations.")}
      icon={<History className="h-4 w-4" />}
    >
      <QueryStateBlock loading={impactQuery.isLoading} error={impactQuery.error}>
        {!installationId || !impact ? (
          <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
            {localize(lang, "Выберите установленный плагин.", "Select an installation to inspect lifecycle impact.")}
          </p>
        ) : (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-3">
              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-foreground">{impact.plugin_id}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{localize(lang, "Пакет", "Package")} {impact.package.version}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge label={lifecycleStatusLabel(lang, impact.status)} tone={tone(impact.status)} />
                    <StatusBadge label={impact.package.ready_to_enable ? localize(lang, "готов", "ready") : localize(lang, "заблокирован", "blocked")} tone={impact.package.ready_to_enable ? "success" : "warning"} />
                  </div>
                </div>
                {impact.package.enable_blockers.length ? (
                  <div className="mt-3 space-y-2">
                    {impact.package.enable_blockers.map((blocker) => (
                      <div key={blocker} className="flex items-start gap-2 rounded-lg border border-border/60 bg-secondary/15 px-3 py-2 text-xs text-muted-foreground">
                        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                        {blocker}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">{localize(lang, "Что исчезнет после отключения", "Surfaces removed on disable/uninstall")}</div>
                <CountGrid counts={impact.surfaces.counts} lang={lang} />
              </div>
            </div>

            <div className="space-y-3">
              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">{localize(lang, "Разрешения", "Permission review")}</div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{localize(lang, "заявлено", "declared")}: {impact.permissions.declared.length}</Badge>
                  <Badge variant="outline">{localize(lang, "выдано", "granted")}: {impact.permissions.granted.length}</Badge>
                  <Badge variant="outline">{localize(lang, "не хватает", "missing")}: {impact.permissions.missing.length}</Badge>
                </div>
              </div>
              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">{localize(lang, "Секреты", "Secrets")}</div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{localize(lang, "заявлено", "declared")}: {impact.secrets.declared.length}</Badge>
                  <Badge variant="outline">{localize(lang, "подключено", "bound")}: {impact.secrets.bound.length}</Badge>
                  <Badge variant={impact.secrets.missing_required.length ? "destructive" : "outline"}>
                    {localize(lang, "нет обязательных", "missing required")}: {impact.secrets.missing_required.length}
                  </Badge>
                </div>
              </div>
              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">{localize(lang, "Запуск кода плагина", "Plugin code execution")}</div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge
                    label={privilegedLocalExecution
                      ? localize(lang, "локальный процесс с полным доступом", "privileged local process — full application access")
                      : sandboxPolicy?.required
                        ? (sandboxPolicy.allowed ? localize(lang, "изолированный запуск готов", "isolated runner ready") : localize(lang, "запуск кода заблокирован", "code execution blocked"))
                        : localize(lang, "исполняемого кода нет", "no executable code")}
                    tone={privilegedLocalExecution ? "danger" : sandboxPolicy?.required ? (sandboxPolicy.allowed ? "success" : "danger") : "neutral"}
                  />
                  <Badge variant="outline">{localize(lang, "среда", "provider")}: {providerLabel(lang, backendExecutionProvider)}</Badge>
                  <Badge variant="outline">{localize(lang, "требования", "requirements")}: {sandboxPolicy?.requirements?.length ?? 0}</Badge>
                  <Badge variant={sandboxPolicy?.blockers?.length ? "destructive" : "outline"}>{localize(lang, "блокировки", "blockers")}: {sandboxPolicy?.blockers?.length ?? 0}</Badge>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => softUninstall.mutate()} disabled={softUninstall.isPending}>
                  <Trash2 className="h-4 w-4" />
                  {localize(lang, "Отключить и удалить", "Soft uninstall")}
                </Button>
                <Button size="sm" variant="outline" onClick={() => rollback.mutate()} disabled={rollback.isPending || !impact.uninstall.reversible}>
                  <RotateCcw className="h-4 w-4" />
                  {localize(lang, "Вернуть версию", "Rollback")}
                </Button>
              </div>
            </div>
          </div>
        )}
      </QueryStateBlock>
    </SectionCard>
  );
}
