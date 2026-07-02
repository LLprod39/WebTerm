import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Boxes, GitBranch, Layers3, RefreshCcw, ShieldCheck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import {
  createKubernetesActionRequest,
  createKubernetesDiagnosisDraft,
  fetchKubernetesOverview,
  type KubernetesActionRequestRecord,
  type KubernetesAppRef,
} from "@/api";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  MetricCard,
  MetricGrid,
  PageHero,
  PageShell,
  QueryStateBlock,
  SectionCard,
  StatusBadge,
} from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import {
  AppRow,
  ClusterCard,
  FleetRow,
  metricToneForHealth,
  statusTone,
} from "@/pages/kubernetes-page/kubernetesPageSections";
import { KubernetesActionRequestPanel } from "@/pages/kubernetes-page/KubernetesActionRequestPanel";
import { useKubernetesDeepLinkAudit } from "@/pages/kubernetes-page/useKubernetesDeepLinkAudit";

function operatorModeLabel(lang: string, readyForSidebar?: boolean) {
  return readyForSidebar
    ? localize(lang, "Доступно в меню", "Available in menu")
    : localize(lang, "Только просмотр", "Read-only");
}

export default function KubernetesPage() {
  const { lang } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const auditDeepLink = useKubernetesDeepLinkAudit();
  const [diagnosisAppId, setDiagnosisAppId] = useState<string | null>(null);
  const [actionRequestTargetId, setActionRequestTargetId] = useState("");
  const [actionRequestResult, setActionRequestResult] = useState<KubernetesActionRequestRecord | null>(null);
  const overviewQuery = useQuery({
    queryKey: ["kubernetes", "overview"],
    queryFn: fetchKubernetesOverview,
    staleTime: 15_000,
  });
  const data = overviewQuery.data;
  const summary = data?.summary;
  const readiness = data?.readiness;
  const problemApps = (data?.apps || []).filter((app) => ["warning", "degraded"].includes(app.health)).slice(0, 4);
  const problemWorkloads = (data?.workloads || []).filter((workload) => ["warning", "degraded"].includes(workload.health)).slice(0, 4);
  const attentionRows = [...problemWorkloads, ...problemApps].slice(0, 4);
  const refreshOverview = () => queryClient.invalidateQueries({ queryKey: ["kubernetes", "overview"] });
  const diagnosisMutation = useMutation({
    mutationFn: (appId: string) => createKubernetesDiagnosisDraft({ app_id: appId }),
    onMutate: (appId) => setDiagnosisAppId(appId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      navigate(result.target_url || `/studio/drafts?draft=${result.draft.id}`);
    },
    onSettled: () => setDiagnosisAppId(null),
  });
  const actionRequestMutation = useMutation({
    mutationFn: (app: KubernetesAppRef) =>
      createKubernetesActionRequest({
        action: "k8s.rollout.restart",
        reason: `Operator requested restart approval for ${app.namespace}/${app.name}`,
        target: { workload_id: app.id },
      }),
    onMutate: (app) => {
      setActionRequestTargetId(app.id);
      setActionRequestResult(null);
    },
    onSuccess: (result) => setActionRequestResult(result.request),
    onSettled: () => setActionRequestTargetId(""),
  });

  return (
    <PageShell width="7xl" className="space-y-5">
      <PageHero
        kicker={localize(lang, "Инфраструктура", "Infrastructure")}
        title={localize(lang, "Kubernetes Ops", "Kubernetes Ops")}
        description={localize(
          lang,
          "Что запущено в кластерах, где есть проблемы и куда открыть детали. Пока только просмотр.",
          "What runs in clusters, where issues are, and where to open details. Read-only for now.",
        )}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              label={
                overviewQuery.isLoading
                  ? localize(lang, "Проверка", "Checking")
                  : overviewQuery.error
                    ? localize(lang, "Backend недоступен", "Backend unavailable")
                    : operatorModeLabel(lang, readiness?.ready_for_sidebar)
              }
              tone={overviewQuery.error ? "danger" : statusTone(readiness?.status || "not_configured")}
            />
            {readiness?.access_policy?.can_admin_read ? (
              <Button asChild variant="outline" size="sm" className="h-10 gap-2">
                <Link to="/kubernetes/admin">
                  <ShieldCheck className="h-4 w-4" />
                  Admin Mode
                </Link>
              </Button>
            ) : null}
            <Button variant="outline" size="sm" className="h-10 gap-2" onClick={refreshOverview}>
              <RefreshCcw className="h-4 w-4" />
              {localize(lang, "Обновить", "Refresh")}
            </Button>
          </div>
        }
      />

      <QueryStateBlock
        loading={overviewQuery.isLoading}
        error={overviewQuery.error || (!overviewQuery.isLoading && data && !data.success ? new Error("Kubernetes overview failed") : undefined)}
        errorText={localize(lang, "Не удалось загрузить Kubernetes overview", "Failed to load Kubernetes overview")}
        onRetry={refreshOverview}
      >
        {summary && readiness ? (
          <>
            <MetricGrid>
              <MetricCard
                label={localize(lang, "Кластеры", "Clusters")}
                value={summary.clusters}
                description={localize(lang, "Доступные окружения", "Available environments")}
                tone="info"
                icon={<Boxes className="h-4 w-4" />}
              />
              <MetricCard
                label={localize(lang, "Приложения", "Applications")}
                value={summary.apps}
                description={localize(lang, "Рабочие сервисы", "Running services")}
                tone="default"
                icon={<Layers3 className="h-4 w-4" />}
              />
              <MetricCard
                label={localize(lang, "Выкатки", "Rollouts")}
                value={summary.fleet_rollouts}
                description={localize(lang, `${summary.rolling} идёт, ${summary.paused} на паузе`, `${summary.rolling} rolling, ${summary.paused} paused`)}
                tone={summary.rolling || summary.paused ? "warning" : "success"}
                icon={<GitBranch className="h-4 w-4" />}
              />
              <MetricCard
                label={localize(lang, "Проблемы", "Issues")}
                value={summary.incidents}
                description={localize(lang, `${summary.warnings} предупреждений`, `${summary.warnings} warnings`)}
                tone={metricToneForHealth(summary.incidents, summary.warnings)}
                icon={<AlertTriangle className="h-4 w-4" />}
              />
              <MetricCard
                label={localize(lang, "Актуальность", "Freshness")}
                value={summary.stale}
                description={localize(lang, `${summary.provider_issues} ошибок обновления`, `${summary.provider_issues} refresh issues`)}
                tone={summary.stale || summary.provider_issues ? "warning" : "success"}
                icon={<RefreshCcw className="h-4 w-4" />}
              />
            </MetricGrid>

            {summary.stale || summary.provider_issues ? (
              <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                {localize(
                  lang,
                  "Есть предупреждения по обновлению данных. Экран показывает последнее известное состояние.",
                  "Data refresh warnings are present. The page shows the latest known state.",
                )}
              </div>
            ) : null}
            {diagnosisMutation.error ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {localize(lang, "Не удалось создать Studio draft:", "Failed to create Studio draft:")}{" "}
                {diagnosisMutation.error instanceof Error ? diagnosisMutation.error.message : localize(lang, "неизвестная ошибка", "unknown error")}
              </div>
            ) : null}

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
              <SectionCard
                title={localize(lang, "Кластеры", "Clusters")}
                description={localize(lang, "Окружения и состояние запущенных сервисов.", "Environments and running service health.")}
                icon={<Boxes className="h-4 w-4" />}
              >
                {data.clusters.length ? (
                  <div className="space-y-3">
                    {data.clusters.map((cluster) => (
                      <ClusterCard key={cluster.id} cluster={cluster} lang={lang} href={`/kubernetes/clusters/${cluster.id}`} onOpenLink={auditDeepLink} />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<Boxes className="h-5 w-5" />}
                    title={localize(lang, "Кластеры ещё не синхронизированы", "Clusters are not synced yet")}
                    description={localize(
                      lang,
                      "После первого обновления здесь появятся кластеры и их состояние.",
                      "Clusters and their state will appear here after the first refresh.",
                    )}
                  />
                )}
              </SectionCard>

              <SectionCard
                title={localize(lang, "Требует внимания", "Needs attention")}
                description={localize(lang, "Проблемные приложения и активные предупреждения.", "Problem applications and active warnings.")}
                icon={<AlertTriangle className="h-4 w-4" />}
              >
                {attentionRows.length ? (
                  <div className="space-y-2">
                    {attentionRows.map((app) => (
                      <AppRow
                        key={app.id}
                        app={app}
                        lang={lang}
                        onDiagnose={String(app.id || "").startsWith("app_") ? (targetApp) => diagnosisMutation.mutate(targetApp.id) : undefined}
                        onRequestRestart={String(app.id || "").startsWith("workload_") ? (targetApp) => actionRequestMutation.mutate(targetApp) : undefined}
                        onOpenLink={auditDeepLink}
                        diagnosePending={diagnosisMutation.isPending && diagnosisAppId === app.id}
                        restartPending={actionRequestMutation.isPending && actionRequestTargetId === app.id}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<ShieldCheck className="h-5 w-5" />}
                    title={localize(lang, "Критичных приложений нет", "No critical apps")}
                    description={localize(lang, "Проблемные приложения появятся здесь первыми.", "Problem applications will appear here first.")}
                  />
                )}
              </SectionCard>
            </div>

            {(actionRequestResult || actionRequestMutation.error) ? (
              <KubernetesActionRequestPanel
                lang={lang}
                request={actionRequestResult}
                error={actionRequestMutation.error}
                onClose={() => {
                  setActionRequestResult(null);
                  actionRequestMutation.reset();
                }}
              />
            ) : null}

            <div className="grid gap-5 xl:grid-cols-2">
              <SectionCard
                title={localize(lang, "Приложения", "Applications")}
                description={localize(lang, "Где запущено, кто отвечает и какая версия стоит.", "Where it runs, who owns it, and which version is deployed.")}
                icon={<Layers3 className="h-4 w-4" />}
                actions={
                  <Button asChild variant="outline" size="sm">
                    <Link to="/kubernetes/devtron">{localize(lang, "Открыть", "Open")}</Link>
                  </Button>
                }
              >
                {data.apps.length ? (
                  <div className="space-y-2">
                    {data.apps.map((app) => (
                      <AppRow
                        key={app.id}
                        app={app}
                        lang={lang}
                        onDiagnose={(targetApp) => diagnosisMutation.mutate(targetApp.id)}
                        onOpenLink={auditDeepLink}
                        diagnosePending={diagnosisMutation.isPending && diagnosisAppId === app.id}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<Layers3 className="h-5 w-5" />}
                    title={localize(lang, "Приложения не найдены", "No applications found")}
                    description={localize(lang, "Список появится после первого обновления данных.", "The list will appear after the first data refresh.")}
                  />
                )}
              </SectionCard>

              <SectionCard
                title={localize(lang, "Выкатки", "Rollouts")}
                description={localize(lang, "Что сейчас выкатывается и насколько готово.", "What is rolling out now and how ready it is.")}
                icon={<GitBranch className="h-4 w-4" />}
                actions={
                  <Button asChild variant="outline" size="sm">
                    <Link to="/kubernetes/fleet">{localize(lang, "Открыть", "Open")}</Link>
                  </Button>
                }
              >
                {data.fleet_rollouts.length ? (
                  <div className="space-y-3">
                    {data.fleet_rollouts.map((bundle) => (
                      <FleetRow key={bundle.id} bundle={bundle} lang={lang} onOpenLink={auditDeepLink} />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<GitBranch className="h-5 w-5" />}
                    title={localize(lang, "Выкатки не найдены", "No rollouts found")}
                    description={localize(lang, "Данные появятся после обновления источников.", "Data will appear after source refresh.")}
                  />
                )}
              </SectionCard>
            </div>
          </>
        ) : null}
      </QueryStateBlock>
    </PageShell>
  );
}
