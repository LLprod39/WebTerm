import { json } from "./apiHarness";
import type { ApiRequest } from "./apiHarness";
import type { PlatformMockOptions } from "./platformFixtureTypes";

const FIXED_SYNC = "2026-06-29T19:00:00.000Z";

function freshness(status = "fresh") {
  return {
    sync_status: status,
    is_stale: status !== "fresh",
    sync_age_seconds: status === "missing" ? null : 60,
    sync_stale_after_seconds: 900,
  };
}

function workerState(state: PlatformMockOptions["kubernetesState"]) {
  const running = state !== "empty";
  return {
    worker_kind: "kubernetes_ops_sync",
    worker_key: "default",
    status: running ? "running" : "missing",
    is_stale: !running,
    hostname: running ? "webterm-worker-1" : "",
    pid: running ? 4242 : null,
    command: "python manage.py run_kubernetes_ops_sync_worker --daemon --interval 60",
    heartbeat_at: running ? FIXED_SYNC : null,
    lease_expires_at: running ? "2026-06-29T19:03:00.000Z" : null,
    last_started_at: running ? FIXED_SYNC : null,
    last_stopped_at: null,
    last_cycle_started_at: running ? FIXED_SYNC : null,
    last_cycle_finished_at: running ? FIXED_SYNC : null,
    last_summary: running
      ? {
          matched: 2,
          ok: state === "degraded" ? 1 : 2,
          failed: state === "degraded" ? 1 : 0,
          clusters: 1,
          namespaces: 2,
          workloads: 8,
          events: state === "degraded" ? 1 : 0,
          apps: 2,
          fleet_bundles: 2,
        }
      : {},
    last_error: state === "degraded" ? "Devtron sync returned degraded apps." : "",
  };
}

const providers = [
  {
    id: 1,
    name: "rancher-main",
    kind: "rancher",
    base_url: "https://rancher.example.test",
    enabled: true,
    auth_mode: "secret_ref",
    has_secret_ref: true,
    secret_storage: "external",
    labels: {},
    last_sync_at: FIXED_SYNC,
    last_error: "",
    provider_health: "healthy",
    ...freshness(),
    created_at: FIXED_SYNC,
    updated_at: FIXED_SYNC,
  },
  {
    id: 2,
    name: "devtron-main",
    kind: "devtron",
    base_url: "https://devtron.example.test",
    enabled: true,
    auth_mode: "secret_ref",
    has_secret_ref: true,
    secret_storage: "external",
    labels: {},
    last_sync_at: FIXED_SYNC,
    last_error: "",
    provider_health: "healthy",
    ...freshness(),
    created_at: FIXED_SYNC,
    updated_at: FIXED_SYNC,
  },
];

function cluster(state: PlatformMockOptions["kubernetesState"]) {
  const degraded = state === "degraded";
  return {
    id: "cluster_1",
    database_id: 1,
    name: degraded ? "prod-eu-1" : "prod-kz-1",
    environment: "prod",
    provider: "rancher",
    health: degraded ? "degraded" : "healthy",
    nodes_ready: degraded ? 2 : 3,
    nodes_total: 3,
    namespaces: 2,
    workloads: 8,
    apps: 2,
    fleet_bundles: 2,
    devtron_apps: 2,
    labels: { team: "platform" },
    links: { rancher: "https://rancher.example.test/dashboard/c/prod-kz-1" },
    last_sync_at: FIXED_SYNC,
    ...freshness(),
    created_at: FIXED_SYNC,
    updated_at: FIXED_SYNC,
  };
}

function apps(state: PlatformMockOptions["kubernetesState"]) {
  const degraded = state === "degraded";
  const clusterRow = cluster(state);
  return [
    {
      id: "app_1",
      database_id: 1,
      name: "payments-api",
      cluster_id: clusterRow.id,
      cluster_name: clusterRow.name,
      namespace: "payments",
      environment: "prod",
      owner: "devtron",
      team: "payments",
      health: degraded ? "degraded" : "healthy",
      version: degraded ? "2026.06.30-rollback-candidate" : "2026.06.30-1",
      links: {
        devtron_app: "https://devtron.example.test/app/payments-api",
        logs: "https://devtron.example.test/app/payments-api/logs",
        history: "https://devtron.example.test/app/payments-api/history",
      },
      labels: {},
      last_sync_at: FIXED_SYNC,
      ...freshness(),
    },
    {
      id: "app_2",
      database_id: 2,
      name: "billing-worker",
      cluster_id: clusterRow.id,
      cluster_name: clusterRow.name,
      namespace: "billing",
      environment: "prod",
      owner: "devtron",
      team: "billing",
      health: degraded ? "warning" : "healthy",
      version: "2026.06.29-4",
      links: {
        devtron_app: "https://devtron.example.test/app/billing-worker",
        logs: "https://devtron.example.test/app/billing-worker/logs",
      },
      labels: {},
      last_sync_at: FIXED_SYNC,
      ...freshness(),
    },
  ];
}

function bundles(state: PlatformMockOptions["kubernetesState"]) {
  const degraded = state === "degraded";
  return [
    {
      id: "fleet_1",
      database_id: 1,
      name: "fleet-default/ingress-nginx",
      source: "gitrepo/platform",
      target: "prod",
      status: degraded ? "rolling" : "ready",
      ready: degraded ? 1 : 2,
      desired: 2,
      partitions: [],
      links: { rancher_fleet: "https://rancher.example.test/fleet/bundles/ingress-nginx" },
      labels: {},
      last_sync_at: FIXED_SYNC,
      ...freshness(),
    },
    {
      id: "fleet_2",
      database_id: 2,
      name: "fleet-default/observability",
      source: "gitrepo/observability",
      target: "prod",
      status: degraded ? "degraded" : "ready",
      ready: degraded ? 1 : 3,
      desired: 3,
      partitions: [],
      links: { rancher_fleet: "https://rancher.example.test/fleet/bundles/observability" },
      labels: {},
      last_sync_at: FIXED_SYNC,
      ...freshness(),
    },
  ];
}

function readiness(state: PlatformMockOptions["kubernetesState"]) {
  const configured = state !== "empty";
  const syncWorker = workerState(state);
  return {
    success: true,
    status: configured ? "configured" : "not_configured",
    ready_for_sidebar: false,
    summary: configured ? { ready: 9, missing: 1, manual: 1, total: 11 } : { ready: 3, missing: 7, manual: 1, total: 11 },
    checks: [
      { id: "architecture_guard", status: "ready", detail: "Repository guard is green.", required: true },
      { id: "rancher_provider", status: configured ? "ready" : "missing", detail: configured ? "Rancher provider configured: 1" : "Rancher provider is not configured.", required: true },
      { id: "devtron_provider", status: configured ? "ready" : "missing", detail: configured ? "Devtron provider configured: 1" : "Devtron provider is not configured.", required: true },
      { id: "provider_health", status: configured ? "ready" : "missing", detail: configured ? "Enabled providers have fresh sync metadata: 2." : "No enabled Kubernetes providers are configured.", required: true },
      { id: "read_only_sync", status: configured ? "ready" : "missing", detail: configured ? "Normalized inventory rows are available." : "No normalized inventory rows are available yet.", required: true },
      { id: "sync_worker", status: configured ? "ready" : "missing", detail: configured ? "Kubernetes sync worker is running." : "Kubernetes periodic sync worker is not running.", required: true },
      { id: "identity_runtime", status: "ready", detail: "Production SSO gate is not blocking this local visual fixture.", required: true },
      { id: "release_evidence_artifact", status: "ready", detail: "Fresh local release evidence artifact is present and safe.", required: true },
      {
        id: "sidebar_release_scope",
        status: "missing",
        detail: configured
          ? "Sidebar stays locked because this fixture uses local/test Kubernetes endpoints."
          : "Sidebar stays locked until production release evidence is approved.",
        required: true,
      },
      { id: "studio_automation", status: configured ? "ready" : "missing", detail: configured ? "Studio diagnosis draft can bind Kubernetes MCP with kubernetes-safety." : "Studio diagnosis draft is not launch-ready.", required: false },
      { id: "frontend_e2e", status: "manual", detail: "Frontend e2e evidence is captured in visual snapshots.", required: false },
    ],
    worker_state: syncWorker,
  };
}

function overview(state: PlatformMockOptions["kubernetesState"]) {
  if (state === "empty") {
    return {
      success: true,
      readiness: readiness(state),
      summary: { clusters: 0, apps: 0, fleet_rollouts: 0, incidents: 0, warnings: 0, rolling: 0, paused: 0, stale: 0, provider_issues: 0 },
      providers: [],
      clusters: [],
      apps: [],
      fleet_rollouts: [],
    };
  }
  const appRows = apps(state);
  const bundleRows = bundles(state);
  return {
    success: true,
    readiness: readiness(state),
    summary: {
      clusters: 1,
      apps: appRows.length,
      fleet_rollouts: bundleRows.length,
      incidents: state === "degraded" ? 2 : 0,
      warnings: state === "degraded" ? 1 : 0,
      rolling: bundleRows.filter((bundle) => bundle.status === "rolling").length,
      paused: 0,
      stale: 0,
      provider_issues: 0,
    },
    providers,
    clusters: [cluster(state)],
    apps: appRows,
    fleet_rollouts: bundleRows,
  };
}

function namespaces(state: PlatformMockOptions["kubernetesState"]) {
  const degraded = state === "degraded";
  return [
    {
      id: "1:payments",
      name: "payments",
      environment: "prod",
      apps: 1,
      healthy: degraded ? 0 : 1,
      warning: 0,
      degraded: degraded ? 1 : 0,
      unknown: 0,
      owners: ["devtron"],
      teams: ["payments"],
      last_sync_at: FIXED_SYNC,
    },
    {
      id: "1:billing",
      name: "billing",
      environment: "prod",
      apps: 1,
      healthy: degraded ? 0 : 1,
      warning: degraded ? 1 : 0,
      degraded: 0,
      unknown: 0,
      owners: ["devtron"],
      teams: ["billing"],
      last_sync_at: FIXED_SYNC,
    },
  ];
}

export function handleKubernetesMockRequest(req: ApiRequest, options: PlatformMockOptions) {
  const state = options.kubernetesState || "empty";
  if (req.path === "/api/kubernetes/readiness/" && req.method === "GET") return json(readiness(state));
  if (req.path === "/api/kubernetes/overview/" && req.method === "GET") return json(overview(state));
  if (req.path === "/api/kubernetes/audit/deeplink/" && req.method === "POST") {
    return json({ success: true, event: { id: 99, action: "k8s.deeplink.open", username: "admin", provider: "mock", cluster: "", payload: {}, created_at: FIXED_SYNC } });
  }
  if (req.path.match(/^\/api\/kubernetes\/providers\/\d+\/probe\/$/) && req.method === "POST") {
    return json({
      success: true,
      probe: {
        provider_id: 1,
        provider_name: "rancher-main",
        provider_kind: "rancher",
        success: true,
        status: "ready",
        path: "/v3/clusters",
        item_count: state === "empty" ? 0 : 1,
        payload_keys: ["data"],
        duration_ms: 24,
        checked_at: FIXED_SYNC,
        error: "",
      },
    });
  }
  if (req.path === "/api/kubernetes/providers/" && req.method === "GET") return json({ success: true, providers: state === "empty" ? [] : providers });
  if (req.path === "/api/kubernetes/clusters/" && req.method === "GET") return json({ success: true, clusters: state === "empty" ? [] : [cluster(state)] });
  if (req.path.match(/^\/api\/kubernetes\/clusters\/[^/]+\/$/) && req.method === "GET") return json({ success: true, cluster: cluster(state) });
  if (req.path.match(/^\/api\/kubernetes\/clusters\/[^/]+\/namespaces\/$/) && req.method === "GET") return json({ success: true, cluster: cluster(state), namespaces: namespaces(state) });
  if (req.path.match(/^\/api\/kubernetes\/clusters\/[^/]+\/workloads\/$/) && req.method === "GET") return json({ success: true, cluster: cluster(state), workloads: apps(state) });
  if (req.path.match(/^\/api\/kubernetes\/clusters\/[^/]+\/events\/$/) && req.method === "GET") {
    return json({
      success: true,
      cluster: cluster(state),
      events: state === "empty" ? [] : [
        {
          id: "event_1",
          source: "rancher",
          severity: state === "degraded" ? "warning" : "info",
          reason: state === "degraded" ? "Unhealthy" : "Pulled",
          message: state === "degraded" ? "Readiness probe failed for payments-api" : "Provider sync observed healthy workloads",
          username: "system",
          namespace: "payments",
          involved_kind: "Deployment",
          involved_name: "payments-api",
          count: state === "degraded" ? 3 : 1,
          payload: { namespace: "payments", involved_kind: "Deployment", involved_name: "payments-api" },
          created_at: FIXED_SYNC,
        },
      ],
    });
  }
  if (req.path === "/api/kubernetes/fleet/bundles/" && req.method === "GET") return json({ success: true, bundles: state === "empty" ? [] : bundles(state) });
  if (req.path === "/api/kubernetes/devtron/apps/" && req.method === "GET") return json({ success: true, apps: state === "empty" ? [] : apps(state) });
  if (req.path === "/api/kubernetes/audit/" && req.method === "GET") return json({ success: true, events: [] });
  return null;
}
