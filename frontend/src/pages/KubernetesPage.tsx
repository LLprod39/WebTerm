import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Boxes,
  GitBranch,
  Layers3,
  MessageSquare,
  Package,
  Rocket,
  Settings2,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
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
  QueryStateBlock,
  SectionCard,
  StatusBadge,
} from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import {
  AppRow,
  ClusterCard,
  FleetRow,
  statusTone,
} from "@/pages/kubernetes-page/kubernetesPageSections";
import { KubernetesActionRequestPanel } from "@/pages/kubernetes-page/KubernetesActionRequestPanel";
import {
  AskAgentBar,
  CockpitChip,
  countHealth,
  HealthDonut,
  HealthLegend,
  KpiTile,
  QuickLinkTile,
} from "@/pages/kubernetes-page/KubernetesCockpitPrimitives";
import { KubernetesAgentDrawer } from "@/pages/kubernetes-page/KubernetesAgentDrawer";
import { KubernetesHelmWizard } from "@/pages/kubernetes-page/KubernetesHelmWizard";
import { KubernetesMetricsStrip } from "@/pages/kubernetes-page/KubernetesMetricsStrip";
import {
  K8sRefreshButton,
  KubernetesPageHeader,
  KubernetesShell,
} from "@/pages/kubernetes-page/KubernetesShell";
import { useKubernetesDeepLinkAudit } from "@/pages/kubernetes-page/useKubernetesDeepLinkAudit";

type FocusFilter = "all" | "problems" | "rollouts";

export default function KubernetesPage() {
  const { lang } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const auditDeepLink = useKubernetesDeepLinkAudit();
  const [diagnosisAppId, setDiagnosisAppId] = useState<string | null>(null);
  const [actionRequestTargetId, setActionRequestTargetId] = useState("");
  const [actionRequestResult, setActionRequestResult] = useState<KubernetesActionRequestRecord | null>(null);
  const [agentPrompt, setAgentPrompt] = useState("");
  const [focus, setFocus] = useState<FocusFilter>("all");
  const [agentOpen, setAgentOpen] = useState(false);
  const [helmOpen, setHelmOpen] = useState(false);

  const overviewQuery = useQuery({
    queryKey: ["kubernetes", "overview"],
    queryFn: fetchKubernetesOverview,
    staleTime: 15_000,
  });
  const data = overviewQuery.data;
  const summary = data?.summary;
  const readiness = data?.readiness;

  const healthItems = useMemo(
    () => [...(data?.workloads || []), ...(data?.apps || [])],
    [data?.workloads, data?.apps],
  );
  const healthBuckets = useMemo(() => countHealth(healthItems), [healthItems]);
  const healthSlices = useMemo(
    () => [
      {
        key: "healthy",
        label: localize(lang, "Healthy", "Healthy"),
        value: healthBuckets.healthy,
        color: "#34d399",
      },
      {
        key: "warning",
        label: localize(lang, "Warning", "Warning"),
        value: healthBuckets.warning,
        color: "#fbbf24",
      },
      {
        key: "degraded",
        label: localize(lang, "Degraded", "Degraded"),
        value: healthBuckets.degraded,
        color: "#f87171",
      },
      {
        key: "unknown",
        label: localize(lang, "Unknown", "Unknown"),
        value: healthBuckets.unknown,
        color: "#64748b",
      },
    ],
    [healthBuckets, lang],
  );

  const problemApps = (data?.apps || []).filter((app) => ["warning", "degraded"].includes(app.health)).slice(0, 6);
  const problemWorkloads = (data?.workloads || [])
    .filter((workload) => ["warning", "degraded"].includes(workload.health))
    .slice(0, 6);
  const attentionRows = [...problemWorkloads, ...problemApps].slice(0, 6);
  const visibleApps = focus === "problems" ? problemApps : data?.apps || [];
  const visibleRollouts =
    focus === "problems"
      ? (data?.fleet_rollouts || []).filter((b) => ["degraded", "paused", "rolling"].includes(String(b.status)))
      : data?.fleet_rollouts || [];

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

  const freeformDiagnosisMutation = useMutation({
    mutationFn: async (prompt: string) => {
      const firstProblem = attentionRows[0] || (data?.apps || [])[0];
      if (!firstProblem || !String(firstProblem.id || "").startsWith("app_")) {
        throw new Error(
          localize(
            lang,
            "Нет app target для диагностики. Выберите приложение ниже или откройте Agents.",
            "No app target for diagnosis. Pick an app below or open Agents.",
          ),
        );
      }
      // Backend diagnosis draft is app-scoped; free-text is stored in UI history
      // and the draft title/context comes from the selected problem app.
      return createKubernetesDiagnosisDraft({ app_id: firstProblem.id });
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      const url = result.target_url || `/studio/drafts?draft=${result.draft.id}`;
      // Preserve operator intent in query for Studio draft UX if supported later.
      const withPrompt = agentPrompt.trim()
        ? `${url}${url.includes("?") ? "&" : "?"}intent=${encodeURIComponent(agentPrompt.trim().slice(0, 200))}`
        : url;
      navigate(withPrompt);
      setAgentPrompt("");
    },
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

  const totalHealth = healthItems.length || 1;
  const healthyPct = Math.round((healthBuckets.healthy / totalHealth) * 100);
  const sidebarOpen = Boolean(readiness?.ready_for_sidebar);
  const pilotMode = Boolean((readiness as { pilot_sidebar?: boolean } | undefined)?.pilot_sidebar);

  return (
    <KubernetesShell>
      <KubernetesPageHeader
        kicker={localize(lang, "Kubernetes Ops", "Kubernetes Ops")}
        title={localize(lang, "Кластерный пульт", "Cluster cockpit")}
        description={localize(
          lang,
          "Здоровье, проблемы, выкатки, GitOps и агент — без шума. Ручной fix и AI в одном пульте.",
          "Health, issues, rollouts, GitOps and agent — no clutter. Hands-on fix and AI in one cockpit.",
        )}
        meta={
          <StatusBadge
            label={
              overviewQuery.isLoading
                ? localize(lang, "Проверка", "Checking")
                : overviewQuery.error
                  ? localize(lang, "Backend недоступен", "Backend unavailable")
                  : sidebarOpen
                    ? pilotMode
                      ? localize(lang, "Pilot · в меню", "Pilot · in menu")
                      : localize(lang, "В меню", "In menu")
                    : localize(lang, "Sidebar выкл.", "Sidebar off")
            }
            tone={overviewQuery.error ? "danger" : sidebarOpen ? "success" : statusTone(readiness?.status || "not_configured")}
          />
        }
        actions={
          <>
            <Button type="button" variant="outline" size="sm" className="h-10 gap-2" onClick={() => setAgentOpen(true)}>
              <MessageSquare className="h-4 w-4" />
              {localize(lang, "Агент", "Agent")}
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-10 gap-2" onClick={() => setHelmOpen(true)}>
              <Package className="h-4 w-4" />
              Helm
            </Button>
            {readiness?.access_policy?.can_admin_read ? (
              <Button asChild variant="outline" size="sm" className="h-10 gap-2">
                <Link to="/kubernetes/admin">
                  <ShieldCheck className="h-4 w-4" />
                  Admin
                </Link>
              </Button>
            ) : null}
            <Button asChild variant="outline" size="sm" className="h-10 gap-2">
              <Link to="/settings/kubernetes">
                <Settings2 className="h-4 w-4" />
                {localize(lang, "Настройка", "Setup")}
              </Link>
            </Button>
            <K8sRefreshButton onClick={refreshOverview} label={localize(lang, "Обновить", "Refresh")} />
          </>
        }
      />

      <QueryStateBlock
        loading={overviewQuery.isLoading}
        error={
          overviewQuery.error ||
          (!overviewQuery.isLoading && data && !data.success ? new Error("Kubernetes overview failed") : undefined)
        }
        errorText={localize(lang, "Не удалось загрузить Kubernetes overview", "Failed to load Kubernetes overview")}
        onRetry={refreshOverview}
      >
        {summary && readiness ? (
          <>
            {/* Ask agent + focus chips */}
            <AskAgentBar
              lang={lang}
              value={agentPrompt}
              onChange={setAgentPrompt}
              pending={freeformDiagnosisMutation.isPending}
              onSubmit={() => {
                const prompt = agentPrompt.trim();
                if (!prompt) return;
                freeformDiagnosisMutation.mutate(prompt);
              }}
            />
            {freeformDiagnosisMutation.error ? (
              <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {freeformDiagnosisMutation.error instanceof Error
                  ? freeformDiagnosisMutation.error.message
                  : localize(lang, "Не удалось запустить диагностику", "Failed to start diagnosis")}
                <Button asChild variant="link" className="ml-2 h-auto p-0 text-destructive">
                  <Link to="/agents">{localize(lang, "Открыть Agents", "Open Agents")}</Link>
                </Button>
              </div>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <CockpitChip active={focus === "all"} onClick={() => setFocus("all")}>
                {localize(lang, "Всё", "All")}
              </CockpitChip>
              <CockpitChip active={focus === "problems"} onClick={() => setFocus("problems")}>
                {localize(lang, "Только проблемы", "Problems only")} · {summary.incidents}
              </CockpitChip>
              <CockpitChip active={focus === "rollouts"} onClick={() => setFocus("rollouts")}>
                {localize(lang, "Выкатки", "Rollouts")} · {summary.fleet_rollouts}
              </CockpitChip>
            </div>

            <KubernetesMetricsStrip
              lang={lang}
              clusterId={data.clusters[0]?.id}
              healthy={healthBuckets.healthy}
              warning={healthBuckets.warning}
              degraded={healthBuckets.degraded}
            />

            {/* Health + KPI strip */}
            <div className="grid gap-4 xl:grid-cols-[auto_minmax(0,1fr)_minmax(0,1.1fr)]">
              <SectionCard
                title={localize(lang, "Здоровье", "Health")}
                description={localize(lang, "Сводка inventory без лишних виджетов.", "Inventory summary without clutter.")}
                icon={<Sparkles className="h-4 w-4" />}
              >
                <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
                  <HealthDonut
                    slices={healthSlices}
                    centerValue={`${healthyPct}%`}
                    centerLabel={localize(lang, "healthy", "healthy")}
                  />
                  <HealthLegend slices={healthSlices} lang={lang} />
                </div>
              </SectionCard>

              <SectionCard
                title={localize(lang, "Сейчас", "Now")}
                description={localize(lang, "Ключевые цифры за один взгляд.", "Key numbers at a glance.")}
                icon={<Boxes className="h-4 w-4" />}
              >
                <div className="grid grid-cols-2 gap-3">
                  <KpiTile label={localize(lang, "Кластеры", "Clusters")} value={summary.clusters} tone="info" />
                  <KpiTile label={localize(lang, "Приложения", "Apps")} value={summary.apps} />
                  <KpiTile
                    label={localize(lang, "Выкатки", "Rollouts")}
                    value={summary.fleet_rollouts}
                    hint={localize(lang, `${summary.rolling} идёт`, `${summary.rolling} rolling`)}
                    tone={summary.rolling ? "warning" : "success"}
                  />
                  <KpiTile
                    label={localize(lang, "Проблемы", "Issues")}
                    value={summary.incidents}
                    hint={localize(lang, `${summary.warnings} warn`, `${summary.warnings} warn`)}
                    tone={summary.incidents ? "danger" : "success"}
                  />
                </div>
                {(summary.stale || summary.provider_issues) ? (
                  <div className="mt-3 rounded-sm border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">
                    {localize(
                      lang,
                      "Данные частично устарели — экран показывает last known state.",
                      "Some data is stale — showing last known state.",
                    )}
                  </div>
                ) : null}
              </SectionCard>

              <SectionCard
                title={localize(lang, "Быстрые действия", "Quick actions")}
                description={localize(lang, "Развернуть, проверить, администрировать.", "Deploy, inspect, administer.")}
                icon={<Rocket className="h-4 w-4" />}
              >
                <div className="grid gap-2 sm:grid-cols-2">
                  <QuickLinkTile
                    href="/kubernetes/fleet"
                    icon={<GitBranch className="h-4 w-4" />}
                    title={localize(lang, "Fleet / GitOps", "Fleet / GitOps")}
                    description={localize(lang, "Выкатки и bundles", "Rollouts and bundles")}
                  />
                  <QuickLinkTile
                    href="/kubernetes/devtron"
                    icon={<Package className="h-4 w-4" />}
                    title={localize(lang, "Devtron / apps", "Devtron / apps")}
                    description={localize(lang, "Приложения и версии", "Apps and versions")}
                  />
                  <button
                    type="button"
                    onClick={() => setHelmOpen(true)}
                    className="group flex min-h-[92px] flex-col justify-between rounded-sm border border-border bg-surface-0 p-3 text-left shadow-elev-1 transition hover:border-primary hover:bg-primary/5"
                  >
                    <div className="flex items-center gap-2 text-muted-foreground group-hover:text-primary">
                      <Rocket className="h-4 w-4" />
                      <span className="font-display text-sm font-semibold text-foreground">Helm</span>
                    </div>
                    <p className="mt-2 text-2xs leading-snug text-muted-foreground">
                      {localize(lang, "Ownership + request install", "Ownership + request install")}
                    </p>
                  </button>
                  <QuickLinkTile
                    href="/kubernetes/admin"
                    icon={<Wrench className="h-4 w-4" />}
                    title={localize(lang, "Ручной fix", "Hands-on fix")}
                    description={localize(lang, "YAML, logs, resources", "YAML, logs, resources")}
                  />
                </div>
              </SectionCard>
            </div>

            {diagnosisMutation.error ? (
              <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {localize(lang, "Не удалось создать Studio draft:", "Failed to create Studio draft:")}{" "}
                {diagnosisMutation.error instanceof Error
                  ? diagnosisMutation.error.message
                  : localize(lang, "неизвестная ошибка", "unknown error")}
              </div>
            ) : null}

            {/* Attention + clusters */}
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
              <SectionCard
                title={localize(lang, "Кластеры", "Clusters")}
                description={localize(lang, "Окружения и состояние сервисов.", "Environments and service health.")}
                icon={<Boxes className="h-4 w-4" />}
              >
                {data.clusters.length ? (
                  <div className="space-y-3">
                    {data.clusters.map((cluster) => (
                      <ClusterCard
                        key={cluster.id}
                        cluster={cluster}
                        lang={lang}
                        href={`/kubernetes/clusters/${cluster.id}`}
                        onOpenLink={auditDeepLink}
                      />
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
                description={localize(lang, "Сначала чините это.", "Fix these first.")}
                icon={<AlertTriangle className="h-4 w-4" />}
              >
                {attentionRows.length ? (
                  <div className="space-y-2">
                    {attentionRows.map((app) => (
                      <AppRow
                        key={app.id}
                        app={app}
                        lang={lang}
                        onDiagnose={
                          String(app.id || "").startsWith("app_")
                            ? (targetApp) => diagnosisMutation.mutate(targetApp.id)
                            : undefined
                        }
                        onRequestRestart={
                          String(app.id || "").startsWith("workload_")
                            ? (targetApp) => actionRequestMutation.mutate(targetApp)
                            : undefined
                        }
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
                    description={localize(
                      lang,
                      "Проблемные приложения появятся здесь первыми.",
                      "Problem applications will appear here first.",
                    )}
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

            {focus !== "rollouts" ? (
              <div className="grid gap-5 xl:grid-cols-2">
                <SectionCard
                  title={localize(lang, "Приложения", "Applications")}
                  description={localize(
                    lang,
                    "Где запущено, кто отвечает и какая версия стоит.",
                    "Where it runs, who owns it, and which version is deployed.",
                  )}
                  icon={<Layers3 className="h-4 w-4" />}
                  actions={
                    <Button asChild variant="outline" size="sm">
                      <Link to="/kubernetes/devtron">{localize(lang, "Открыть", "Open")}</Link>
                    </Button>
                  }
                >
                  {visibleApps.length ? (
                    <div className="space-y-2">
                      {visibleApps.map((app) => (
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
                      description={localize(
                        lang,
                        "Список появится после первого обновления данных.",
                        "The list will appear after the first data refresh.",
                      )}
                    />
                  )}
                </SectionCard>

                <SectionCard
                  title={localize(lang, "Выкатки", "Rollouts")}
                  description={localize(
                    lang,
                    "Что сейчас выкатывается и насколько готово.",
                    "What is rolling out now and how ready it is.",
                  )}
                  icon={<GitBranch className="h-4 w-4" />}
                  actions={
                    <Button asChild variant="outline" size="sm">
                      <Link to="/kubernetes/fleet">{localize(lang, "Открыть", "Open")}</Link>
                    </Button>
                  }
                >
                  {visibleRollouts.length ? (
                    <div className="space-y-3">
                      {visibleRollouts.map((bundle) => (
                        <FleetRow key={bundle.id} bundle={bundle} lang={lang} onOpenLink={auditDeepLink} />
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      icon={<GitBranch className="h-5 w-5" />}
                      title={localize(lang, "Выкатки не найдены", "No rollouts found")}
                      description={localize(
                        lang,
                        "Данные появятся после обновления источников.",
                        "Data will appear after source refresh.",
                      )}
                    />
                  )}
                </SectionCard>
              </div>
            ) : (
              <SectionCard
                title={localize(lang, "Выкатки", "Rollouts")}
                description={localize(lang, "Фокус на GitOps / Fleet.", "Focus on GitOps / Fleet.")}
                icon={<GitBranch className="h-4 w-4" />}
              >
                {visibleRollouts.length ? (
                  <div className="space-y-3">
                    {visibleRollouts.map((bundle) => (
                      <FleetRow key={bundle.id} bundle={bundle} lang={lang} onOpenLink={auditDeepLink} />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<GitBranch className="h-5 w-5" />}
                    title={localize(lang, "Выкатки не найдены", "No rollouts found")}
                    description={localize(lang, "Нет активных rollouts.", "No active rollouts.")}
                  />
                )}
              </SectionCard>
            )}
          </>
        ) : null}
      </QueryStateBlock>

      <KubernetesAgentDrawer
        open={agentOpen}
        onClose={() => setAgentOpen(false)}
        contextHint={
          data
            ? `clusters=${data.summary?.clusters ?? 0}, apps=${data.summary?.apps ?? 0}, incidents=${data.summary?.incidents ?? 0}`
            : undefined
        }
      />
      <KubernetesHelmWizard open={helmOpen} onClose={() => setHelmOpen(false)} clusters={data?.clusters || []} />
    </KubernetesShell>
  );
}
