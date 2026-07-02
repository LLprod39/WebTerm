import {
  AlertTriangle,
  CheckCircle2,
  CircleX,
  CloudCog,
  FileText,
  GitBranch,
  RotateCcw,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import { Link } from "react-router-dom";

import type {
  KubernetesAppRef,
  KubernetesCluster,
  KubernetesFleetBundle,
  KubernetesHealth,
  KubernetesReadinessCheck,
  KubernetesReadinessStatus,
  KubernetesWorkloadRef,
  KubernetesWorkerState,
} from "@/api";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import { DeepLinkButtons, type OnOpenDeepLink } from "@/pages/kubernetes-page/kubernetesDeepLinks";

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";
export type MetricTone = "default" | "success" | "warning" | "danger" | "info";

export function checkTitle(id: string, lang: string) {
  const labels: Record<string, { ru: string; en: string }> = {
    architecture_guard: { ru: "Architecture guard", en: "Architecture guard" },
    rancher_provider: { ru: "Rancher provider", en: "Rancher provider" },
    devtron_provider: { ru: "Devtron provider", en: "Devtron provider" },
    read_only_sync: { ru: "Read-only sync", en: "Read-only sync" },
    sync_worker: { ru: "Sync worker", en: "Sync worker" },
    provider_health: { ru: "Provider health", en: "Provider health" },
    identity_runtime: { ru: "OIDC/Keycloak runtime", en: "OIDC/Keycloak runtime" },
    sidebar_release_scope: { ru: "Sidebar release scope", en: "Sidebar release scope" },
    release_evidence_artifact: { ru: "Release evidence artifact", en: "Release evidence artifact" },
    studio_automation: { ru: "Studio automation", en: "Studio automation" },
    frontend_e2e: { ru: "Frontend e2e", en: "Frontend e2e" },
  };
  const item = labels[id];
  return item ? localize(lang, item.ru, item.en) : id.replace(/_/g, " ");
}

export function statusTone(status: string): StatusTone {
  if (status === "ready" || status === "healthy" || status === "running") return "success";
  if (status === "rolling" || status === "manual" || status === "configured") return "info";
  if (status === "warning" || status === "paused" || status === "missing" || status === "not_configured" || status === "stopped" || status === "stale") return "warning";
  if (status === "degraded" || status === "critical" || status === "error") return "danger";
  return "neutral";
}

export function metricToneForHealth(value: number, warningValue = 0): MetricTone {
  if (value > 0) return "danger";
  if (warningValue > 0) return "warning";
  return "success";
}

export function readinessLabel(lang: string, status?: KubernetesReadinessStatus, readyForSidebar?: boolean) {
  if (readyForSidebar) return localize(lang, "Открыто в меню", "Sidebar enabled");
  if (status === "configured") return localize(lang, "Данные подключены", "Data connected");
  if (status === "ready") return localize(lang, "Готово", "Ready");
  return localize(lang, "Внутренний режим", "Internal mode");
}

export function statusLabel(lang: string, status: string) {
  const labels: Record<string, { ru: string; en: string }> = {
    ready: { ru: "Готово", en: "Ready" },
    healthy: { ru: "Healthy", en: "Healthy" },
    warning: { ru: "Внимание", en: "Warning" },
    degraded: { ru: "Проблема", en: "Degraded" },
    missing: { ru: "Нет", en: "Missing" },
    manual: { ru: "Manual", en: "Manual" },
    rolling: { ru: "Идёт", en: "Rolling" },
    paused: { ru: "Пауза", en: "Paused" },
    unknown: { ru: "Unknown", en: "Unknown" },
    configured: { ru: "Configured", en: "Configured" },
    not_configured: { ru: "Not configured", en: "Not configured" },
    running: { ru: "Running", en: "Running" },
    idle: { ru: "Idle", en: "Idle" },
    stopped: { ru: "Stopped", en: "Stopped" },
    fresh: { ru: "Свежие", en: "Fresh" },
    stale: { ru: "Устарело", en: "Stale" },
    disabled: { ru: "Disabled", en: "Disabled" },
    error: { ru: "Error", en: "Error" },
  };
  const item = labels[status];
  return item ? localize(lang, item.ru, item.en) : status;
}

function summaryValue(summary: Record<string, unknown>, key: string) {
  const value = summary[key];
  if (typeof value === "number" || typeof value === "string" || typeof value === "boolean") return String(value);
  return "0";
}

export function WorkerStateCard({ worker, lang }: { worker: KubernetesWorkerState; lang: string }) {
  const summary = worker.last_summary || {};
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
      <div className="flex flex-col gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <CloudCog className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{worker.worker_kind}</h3>
            <StatusBadge label={statusLabel(lang, worker.status)} tone={worker.is_stale ? "warning" : statusTone(worker.status)} />
            {worker.is_stale ? <StatusBadge label={localize(lang, "Stale", "Stale")} tone="warning" /> : null}
          </div>
          <div className="mt-2 break-all font-mono text-xs text-muted-foreground">
            {worker.command || "python manage.py run_kubernetes_ops_sync_worker --daemon"}
          </div>
        </div>
        <div className="shrink-0 text-xs text-muted-foreground lg:text-right">
          <div>{localize(lang, "Heartbeat:", "Heartbeat:")} {formatSync(lang, worker.heartbeat_at)}</div>
          <div>{localize(lang, "Last cycle:", "Last cycle:")} {formatSync(lang, worker.last_cycle_finished_at)}</div>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs md:grid-cols-4 xl:grid-cols-8">
        {[
          ["matched", summaryValue(summary, "matched")],
          ["ok", summaryValue(summary, "ok")],
          ["failed", summaryValue(summary, "failed")],
          ["clusters", summaryValue(summary, "clusters")],
          ["namespaces", summaryValue(summary, "namespaces")],
          ["workloads", summaryValue(summary, "workloads")],
          ["pods", summaryValue(summary, "pods")],
          ["services", summaryValue(summary, "services")],
          ["ingresses", summaryValue(summary, "ingresses")],
          ["events", summaryValue(summary, "events")],
          ["apps", summaryValue(summary, "apps")],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md bg-secondary/30 px-3 py-2">
            <div className="font-semibold text-foreground">{value}</div>
            <div className="text-muted-foreground">{label}</div>
          </div>
        ))}
      </div>
      {worker.last_error ? <div className="mt-3 text-xs text-destructive">{worker.last_error}</div> : null}
    </div>
  );
}

export function formatSync(lang: string, value?: string | null) {
  if (!value) return localize(lang, "Синхронизация ещё не запускалась", "Sync has not run yet");
  return value.replace("T", " ").slice(0, 16);
}

export function healthIcon(health: KubernetesHealth) {
  if (health === "healthy") return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
  if (health === "degraded") return <CircleX className="h-4 w-4 text-red-400" />;
  if (health === "warning") return <AlertTriangle className="h-4 w-4 text-amber-400" />;
  return <CloudCog className="h-4 w-4 text-muted-foreground" />;
}

export function ReadinessCard({ check, lang }: { check: KubernetesReadinessCheck; lang: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        {check.status === "ready" ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
        ) : check.status === "missing" ? (
          <AlertTriangle className="h-4 w-4 text-amber-400" />
        ) : (
          <CloudCog className="h-4 w-4 text-primary" />
        )}
        <h3 className="text-sm font-semibold text-foreground">{checkTitle(check.id, lang)}</h3>
        <StatusBadge label={statusLabel(lang, check.status)} tone={statusTone(check.status)} />
        {!check.required ? <StatusBadge label={localize(lang, "Optional", "Optional")} tone="neutral" /> : null}
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{check.detail}</p>
    </div>
  );
}

export function ClusterCard({
  cluster,
  lang,
  href,
  onOpenLink,
}: {
  cluster: KubernetesCluster;
  lang: string;
  href?: string;
  onOpenLink?: OnOpenDeepLink;
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {healthIcon(cluster.health)}
            <h3 className="text-sm font-semibold text-foreground">{cluster.name}</h3>
            <StatusBadge label={cluster.environment || "env"} tone="neutral" />
            <StatusBadge label={statusLabel(lang, cluster.health)} tone={statusTone(cluster.health)} />
            {cluster.is_stale ? <StatusBadge label={statusLabel(lang, cluster.sync_status)} tone="warning" /> : null}
          </div>
          <div className="mt-2 text-xs text-muted-foreground">
            {localize(lang, "Синхронизация:", "Sync:")} {formatSync(lang, cluster.last_sync_at)}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2 text-xs text-muted-foreground sm:items-end">
          <div className="text-left sm:text-right">
            <div className="font-semibold text-foreground">{cluster.nodes_ready}/{cluster.nodes_total}</div>
            <div>{localize(lang, "нод готово", "nodes ready")}</div>
          </div>
          {href ? (
            <Button asChild size="xs" variant="outline">
              <Link to={href}>{localize(lang, "Открыть", "Open")}</Link>
            </Button>
          ) : null}
          <DeepLinkButtons
            links={cluster.links}
            lang={lang}
            target={{
              target_type: "cluster",
              target_id: cluster.id,
              target_name: cluster.name,
              cluster_id: cluster.id,
              provider: cluster.provider,
            }}
            onOpenLink={onOpenLink}
            limit={2}
          />
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
        {[
          [localize(lang, "пространства", "namespaces"), cluster.namespaces],
          [localize(lang, "нагрузки", "workloads"), cluster.workloads],
          [localize(lang, "приложения", "apps"), cluster.apps],
          [localize(lang, "из Devtron", "from Devtron"), cluster.devtron_apps],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md bg-secondary/30 px-3 py-2">
            <div className="font-semibold text-foreground">{value}</div>
            <div className="text-muted-foreground">{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AppRow({
  app,
  lang,
  onDescribe,
  onDiagnose,
  onRequestRestart,
  onOpenLink,
  describePending = false,
  diagnosePending = false,
  restartPending = false,
}: {
  app: KubernetesAppRef;
  lang: string;
  onDescribe?: (app: KubernetesAppRef) => void;
  onDiagnose?: (app: KubernetesAppRef) => void;
  onRequestRestart?: (app: KubernetesAppRef) => void;
  onOpenLink?: OnOpenDeepLink;
  describePending?: boolean;
  diagnosePending?: boolean;
  restartPending?: boolean;
}) {
  const workload = app as Partial<KubernetesWorkloadRef>;
  const hasWorkloadInventory = typeof workload.kind === "string" || typeof workload.desired === "number";
  const canRequestRestart = hasWorkloadInventory && ["deployment", "statefulset", "daemonset"].includes(String(workload.kind || ""));
  const targetType = String(app.id || "").startsWith("workload_") ? "workload" : "app";
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-3 text-sm">
      <div className="flex flex-col gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            {healthIcon(app.health)}
            <span className="truncate font-semibold text-foreground">{app.name}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge label={app.owner} tone={app.owner === "devtron" ? "info" : "neutral"} />
            <StatusBadge label={statusLabel(lang, app.health)} tone={statusTone(app.health)} />
            {hasWorkloadInventory && workload.kind ? <StatusBadge label={workload.kind} tone="neutral" /> : null}
            {app.is_stale ? <StatusBadge label={statusLabel(lang, app.sync_status)} tone="warning" /> : null}
          </div>
          <div className="mt-1 truncate text-xs text-muted-foreground">{app.cluster_name} / {app.namespace}</div>
          <div className="mt-2 grid gap-x-4 gap-y-1 text-xs text-muted-foreground md:grid-cols-2">
            <div>{localize(lang, "Команда:", "Team:")} {app.team || localize(lang, "не задана", "not set")}</div>
            <div className="truncate">{localize(lang, "Версия:", "Version:")} {app.version || localize(lang, "нет", "none")}</div>
            {hasWorkloadInventory ? (
              <div>{localize(lang, "Готово:", "Ready:")} {Number(workload.ready || 0)}/{Number(workload.desired || 0)}</div>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <DeepLinkButtons
            links={app.links}
            lang={lang}
            target={{
              target_type: targetType,
              target_id: app.id,
              target_name: app.name,
              cluster_id: app.cluster_id,
              provider: app.owner,
            }}
            onOpenLink={onOpenLink}
          />
          {onDescribe ? (
            <Button
              size="xs"
              variant="outline"
              className="h-8 gap-1.5"
              disabled={describePending}
              aria-label={localize(lang, `Описать ${app.name}`, `Describe ${app.name}`)}
              onClick={() => onDescribe(app)}
            >
              <FileText className="h-3.5 w-3.5" />
              {describePending ? localize(lang, "Читаю", "Loading") : localize(lang, "Описание", "Describe")}
            </Button>
          ) : null}
          {onDiagnose ? (
            <Button
              size="xs"
              variant="outline"
              className="h-8 gap-1.5"
              disabled={diagnosePending}
              aria-label={localize(lang, `Создать диагностику ${app.name}`, `Create diagnosis for ${app.name}`)}
              onClick={() => onDiagnose(app)}
            >
              <Stethoscope className="h-3.5 w-3.5" />
              {diagnosePending ? localize(lang, "Готовлю", "Drafting") : localize(lang, "Диагностика", "Diagnose")}
            </Button>
          ) : null}
          {onRequestRestart && canRequestRestart ? (
            <Button
              size="xs"
              variant="outline"
              className="h-8 gap-1.5"
              disabled={restartPending}
              aria-label={localize(lang, `Запросить restart ${app.name}`, `Request restart for ${app.name}`)}
              onClick={() => onRequestRestart(app)}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              {restartPending ? localize(lang, "Заявка", "Requesting") : localize(lang, "Запрос restart", "Request restart")}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function FleetRow({ bundle, lang, onOpenLink }: { bundle: KubernetesFleetBundle; lang: string; onOpenLink?: OnOpenDeepLink }) {
  const progress = bundle.desired > 0 ? Math.round((bundle.ready / bundle.desired) * 100) : 0;
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{bundle.name}</h3>
            <StatusBadge label={statusLabel(lang, bundle.status)} tone={statusTone(bundle.status)} />
            {bundle.is_stale ? <StatusBadge label={statusLabel(lang, bundle.sync_status)} tone="warning" /> : null}
          </div>
          <div className="mt-2 truncate text-xs text-muted-foreground">
            {bundle.source}
            {" -> "}
            {bundle.target}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground sm:justify-end">
          <span><span className="font-semibold text-foreground">{bundle.ready}/{bundle.desired}</span> {localize(lang, "готово", "ready")}</span>
          <DeepLinkButtons
            links={bundle.links}
            lang={lang}
            target={{
              target_type: "fleet_bundle",
              target_id: bundle.id,
              target_name: bundle.name,
              provider: "rancher",
            }}
            onOpenLink={onOpenLink}
            limit={2}
          />
        </div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
      </div>
      <div className="mt-2 text-xs text-muted-foreground">{formatSync(lang, bundle.last_sync_at)}</div>
    </div>
  );
}
