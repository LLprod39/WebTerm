import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, CloudCog, RefreshCcw, ShieldCheck } from "lucide-react";

import { fetchAuthSession, fetchKubernetesOverview, type KubernetesReadinessResponse } from "@/api";
import { Button } from "@/components/ui/button";
import { MetricCard, MetricGrid, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { KubernetesProviderAdminPanel } from "@/pages/kubernetes-page/KubernetesProviderAdminPanel";
import {
  ReadinessCard,
  WorkerStateCard,
  checkTitle,
  readinessLabel,
  statusLabel,
  statusTone,
} from "@/pages/kubernetes-page/kubernetesPageSections";

const RELEASE_GATE_CHECK_IDS = new Set(["identity_runtime", "sidebar_release_scope", "release_evidence_artifact"]);

function ruCount(value: number, one: string, few: string, many: string) {
  const lastTwo = value % 100;
  const last = value % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return `${value} ${many}`;
  if (last === 1) return `${value} ${one}`;
  if (last >= 2 && last <= 4) return `${value} ${few}`;
  return `${value} ${many}`;
}

function releaseGateStatusLabel(readiness: KubernetesReadinessResponse, releaseCheckCount: number, blockerCount: number) {
  if (readiness.ready_for_sidebar) return "Готово к sidebar";
  if (!releaseCheckCount) return "Нет данных";
  return ruCount(blockerCount, "блокер", "блокера", "блокеров");
}

function ProductionReleaseGate({
  readiness,
}: {
  readiness: KubernetesReadinessResponse;
}) {
  const releaseChecks = readiness.checks.filter((check) => RELEASE_GATE_CHECK_IDS.has(check.id));
  const blockers = releaseChecks.filter((check) => check.status !== "ready");
  return (
    <SectionCard
      title="Production release gate"
      description="Что именно мешает включить Kubernetes в sidebar для пользователей."
      icon={<ShieldCheck className="h-4 w-4" />}
      actions={
        <StatusBadge
          label={releaseGateStatusLabel(readiness, releaseChecks.length, blockers.length)}
          tone={readiness.ready_for_sidebar ? "success" : "warning"}
        />
      }
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <div className="space-y-3">
          {releaseChecks.length ? (
            releaseChecks.map((check) => (
              <div key={check.id} className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-foreground">{checkTitle(check.id, "ru")}</div>
                  <StatusBadge label={statusLabel("ru", check.status)} tone={statusTone(check.status)} />
                </div>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">{check.detail}</p>
              </div>
            ))
          ) : (
            <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-4 text-sm text-amber-100">
              Release gate checks ещё не пришли из backend readiness.
            </div>
          )}
        </div>
        <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
          <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Production enablement</div>
          <div className="mt-3 space-y-3 text-xs leading-5 text-muted-foreground">
            <div>
              <div className="font-semibold text-foreground">1. Preflight artifact</div>
              <code className="mt-1 block overflow-auto rounded-md bg-secondary/30 px-3 py-2 text-foreground">
                python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json
              </code>
            </div>
            <div>
              <div className="font-semibold text-foreground">2. Production release evidence</div>
              <code className="mt-1 block overflow-auto rounded-md bg-secondary/30 px-3 py-2 text-foreground">
                python manage.py verify_kubernetes_ops_release --username &lt;staff-user&gt; --output artifacts/kubernetes_ops_release_evidence.json
              </code>
            </div>
            <div>
              <div className="font-semibold text-foreground">3. Production env only after evidence</div>
              <code className="mt-1 block overflow-auto rounded-md bg-secondary/30 px-3 py-2 text-foreground">
                KUBERNETES_OPS_RELEASE_ENVIRONMENT=production{"\n"}
                KUBERNETES_OPS_PRODUCTION_APPROVAL_REF=&lt;approval-id&gt;{"\n"}
                KUBERNETES_OPS_READY_FOR_SIDEBAR=true
              </code>
            </div>
            <div>
              <div className="font-semibold text-foreground">Pilot (closed 15–20) — без full production evidence</div>
              <code className="mt-1 block overflow-auto rounded-md bg-secondary/30 px-3 py-2 text-foreground">
                KUBERNETES_OPS_PILOT_SIDEBAR=true{"\n"}
                KUBERNETES_OPS_READY_FOR_SIDEBAR=true
              </code>
              <p className="mt-2 text-[11px] text-muted-foreground">
                Waives only production-scope release evidence. Runtime inventory, providers, and safety checks still required.
              </p>
            </div>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

export default function SettingsKubernetesPage() {
  const queryClient = useQueryClient();
  const { data: authData, isLoading: authLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;
  const overviewQuery = useQuery({
    queryKey: ["kubernetes", "overview"],
    queryFn: fetchKubernetesOverview,
    staleTime: 15_000,
    enabled: isAdmin,
  });
  const data = overviewQuery.data;
  const readiness = data?.readiness;
  const summary = data?.summary;
  const requiredProblems = (readiness?.checks || []).filter((check) => check.required && check.status !== "ready");

  if (!authLoading && !isAdmin) {
    return <Navigate to="/settings/readiness" replace />;
  }

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["kubernetes", "overview"] });

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-secondary text-foreground">
            <Boxes className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-foreground">Kubernetes Ops</h1>
            <p className="text-xs text-muted-foreground">
              Rancher, Devtron, read-only sync worker и release gates для модуля Kubernetes.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {readiness ? (
            <StatusBadge
              label={readinessLabel("ru", readiness.status, readiness.ready_for_sidebar)}
              tone={statusTone(readiness.status)}
            />
          ) : null}
          {requiredProblems.length ? <StatusBadge label={ruCount(requiredProblems.length, "блокер", "блокера", "блокеров")} tone="warning" /> : null}
          <Button variant="outline" size="sm" className="gap-2" onClick={refresh}>
            <RefreshCcw className="h-4 w-4" />
            Обновить
          </Button>
        </div>
      </div>

      <QueryStateBlock
        loading={authLoading || overviewQuery.isLoading}
        error={overviewQuery.error || (!overviewQuery.isLoading && data && !data.success ? new Error("Kubernetes overview failed") : undefined)}
        errorText="Не удалось загрузить Kubernetes настройки"
        onRetry={refresh}
      >
        {summary && readiness && data ? (
          <>
            <MetricGrid>
              <MetricCard
                label="Провайдеры"
                value={data.providers.length}
                description="Rancher и Devtron"
                tone={summary.provider_issues ? "warning" : "success"}
                icon={<CloudCog className="h-4 w-4" />}
              />
              <MetricCard
                label="Инвентарь"
                value={summary.clusters}
                description={`${summary.apps} apps, ${summary.fleet_rollouts} Fleet`}
                tone={summary.stale ? "warning" : "info"}
                icon={<Boxes className="h-4 w-4" />}
              />
              <MetricCard
                label="Provider issues"
                value={summary.provider_issues}
                description={`${summary.stale} stale rows`}
                tone={summary.provider_issues || summary.stale ? "warning" : "success"}
                icon={<RefreshCcw className="h-4 w-4" />}
              />
              <MetricCard
                label="Required gates"
                value={requiredProblems.length}
                description={requiredProblems.length ? "Нужно закрыть" : "Все готовы"}
                tone={requiredProblems.length ? "warning" : "success"}
                icon={<ShieldCheck className="h-4 w-4" />}
              />
            </MetricGrid>

            <ProductionReleaseGate readiness={readiness} />

            <KubernetesProviderAdminPanel providers={data.providers} isAdmin={isAdmin} lang="ru" />

            <SectionCard
              title="Sync worker"
              description="Read-only background worker должен регулярно обновлять provider inventory."
              icon={<RefreshCcw className="h-4 w-4" />}
              actions={
                <StatusBadge
                  label={statusLabel("ru", readiness.worker_state.status)}
                  tone={readiness.worker_state.is_stale ? "warning" : statusTone(readiness.worker_state.status)}
                />
              }
            >
              <WorkerStateCard worker={readiness.worker_state} lang="ru" />
            </SectionCard>

            <SectionCard
              title="Readiness gate"
              description="Проверки перед публичным включением Kubernetes Ops в sidebar."
              icon={<ShieldCheck className="h-4 w-4" />}
              actions={
                <StatusBadge
                  label={readiness.ready_for_sidebar ? "Можно включать" : "Заблокировано"}
                  tone={readiness.ready_for_sidebar ? "success" : "warning"}
                />
              }
            >
              <div className="grid gap-3 lg:grid-cols-2">
                {readiness.checks.map((check) => (
                  <ReadinessCard key={check.id} check={check} lang="ru" />
                ))}
              </div>
            </SectionCard>
          </>
        ) : null}
      </QueryStateBlock>
    </div>
  );
}
