import {
  AlertTriangle,
  Boxes,
  GitBranch,
  Layers3,
  Package,
  Rocket,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { UseMutationResult } from "@tanstack/react-query";

import type {
  KubernetesActionRequestRecord,
  KubernetesAppRef,
  KubernetesOverviewResponse,
} from "@/api";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  SectionCard,
} from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import {
  AppRow,
  ClusterCard,
  FleetRow,
} from "@/pages/kubernetes-page/kubernetesPageSections";
import type { OnOpenDeepLink } from "@/pages/kubernetes-page/kubernetesDeepLinks";
import { KubernetesActionRequestPanel } from "@/pages/kubernetes-page/KubernetesActionRequestPanel";
import {
  AskAgentBar,
  CockpitChip,
  HealthDonut,
  HealthLegend,
  KpiTile,
  QuickLinkTile,
} from "@/pages/kubernetes-page/KubernetesCockpitPrimitives";
import { KubernetesMetricsStrip } from "@/pages/kubernetes-page/KubernetesMetricsStrip";

type FocusFilter = "all" | "problems" | "rollouts";

// Mutation result shapes stay loosely typed so the coordinator can pass
// react-query mutations without coupling this view to mutation generics.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type LooseMutation<TVars = any> = UseMutationResult<any, Error, TVars, unknown>;

export interface KubernetesCockpitBodyProps {
  lang: string;
  data: KubernetesOverviewResponse;
  summary: NonNullable<KubernetesOverviewResponse["summary"]>;
  readiness: NonNullable<KubernetesOverviewResponse["readiness"]>;
  focus: FocusFilter;
  setFocus: (focus: FocusFilter) => void;
  agentPrompt: string;
  setAgentPrompt: (value: string) => void;
  healthBuckets: { healthy: number; warning: number; degraded: number; unknown: number };
  healthSlices: Array<{ key: string; label: string; value: number; color: string }>;
  healthyPct: number;
  attentionRows: Array<KubernetesAppRef>;
  visibleApps: Array<KubernetesAppRef>;
  visibleRollouts: NonNullable<KubernetesOverviewResponse["fleet_rollouts"]>;
  diagnosisAppId: string | null;
  actionRequestTargetId: string;
  actionRequestResult: KubernetesActionRequestRecord | null;
  setActionRequestResult: (value: KubernetesActionRequestRecord | null) => void;
  setHelmOpen: (open: boolean) => void;
  auditDeepLink: OnOpenDeepLink;
  freeformDiagnosisMutation: LooseMutation<string>;
  diagnosisMutation: LooseMutation<string>;
  actionRequestMutation: LooseMutation<KubernetesAppRef>;
}

export function KubernetesCockpitBody({
  lang,
  data,
  summary,
  readiness: _readiness,
  focus,
  setFocus,
  agentPrompt,
  setAgentPrompt,
  healthBuckets,
  healthSlices,
  healthyPct,
  attentionRows,
  visibleApps,
  visibleRollouts,
  diagnosisAppId,
  actionRequestTargetId,
  actionRequestResult,
  setActionRequestResult,
  setHelmOpen,
  auditDeepLink,
  freeformDiagnosisMutation,
  diagnosisMutation,
  actionRequestMutation,
}: KubernetesCockpitBodyProps) {
  void _readiness;
  return (
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
            <Link to="/agents">{localize(lang, "Открыть агентов", "Open Agents")}</Link>
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
          title={localize(lang, "Состояние", "Health")}
          icon={<Sparkles className="h-4 w-4" />}
        >
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
            <HealthDonut
              slices={healthSlices}
              centerValue={`${healthyPct}%`}
              centerLabel={localize(lang, "в норме", "healthy")}
            />
            <HealthLegend slices={healthSlices} lang={lang} />
          </div>
        </SectionCard>

        <SectionCard
          title={localize(lang, "Сейчас", "Now")}
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
              hint={localize(lang, `${summary.warnings} предупреждений`, `${summary.warnings} warnings`)}
              tone={summary.incidents ? "danger" : "success"}
            />
          </div>
          {(summary.stale || summary.provider_issues) ? (
            <div className="mt-3 rounded-sm border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">
              {localize(
                lang,
                "Часть данных устарела. Показано последнее известное состояние.",
                "Some data is stale. Showing the last known state.",
              )}
            </div>
          ) : null}
        </SectionCard>

        <SectionCard
          title={localize(lang, "Быстрые действия", "Quick actions")}
          icon={<Rocket className="h-4 w-4" />}
        >
          <div className="grid gap-2 sm:grid-cols-2">
            <QuickLinkTile
              href="/kubernetes/fleet"
              icon={<GitBranch className="h-4 w-4" />}
              title={localize(lang, "Fleet / GitOps", "Fleet / GitOps")}
              description={localize(lang, "Выкатки и пакеты", "Rollouts and bundles")}
            />
            <QuickLinkTile
              href="/kubernetes/devtron"
              icon={<Package className="h-4 w-4" />}
              title={localize(lang, "Devtron", "Devtron")}
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
                {localize(lang, "Запрос на установку", "Request an installation")}
              </p>
            </button>
            <QuickLinkTile
              href="/kubernetes/admin"
              icon={<Wrench className="h-4 w-4" />}
              title={localize(lang, "Ресурсы", "Resources")}
              description={localize(lang, "YAML, логи и события", "YAML, logs, and events")}
            />
          </div>
        </SectionCard>
      </div>

      {diagnosisMutation.error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {localize(lang, "Не удалось подготовить диагностику:", "Failed to prepare the diagnosis:")}{" "}
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
              description={localize(lang, "Нет активных развёртываний.", "No active rollouts.")}
            />
          )}
        </SectionCard>
      )}
    </>
  );
}
