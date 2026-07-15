import { DEMO_SESSION } from "./demo";
import { demoKubernetesAdminDiscovery } from "./api-demo-kubernetes-discovery";

export function demoKubernetesFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  if (path.includes("/api/kubernetes/readiness/")) return demoKubernetesReadiness() as T;
  if (path.includes("/api/kubernetes/sync/") || path.includes("/api/kubernetes/providers/") && path.includes("/sync/")) {
    return { success: true, results: [] } as T;
  }
  if (path.includes("/api/kubernetes/providers/") && path.includes("/probe/")) {
    return {
      success: true,
      probe: {
        provider_id: 0,
        provider_name: "demo-provider",
        provider_kind: "rancher",
        success: true,
        status: "ready",
        path: "/v3/clusters",
        item_count: 0,
        payload_keys: ["data"],
        duration_ms: 0,
        checked_at: new Date(0).toISOString(),
        error: "",
      },
    } as T;
  }
  if (path.includes("/api/kubernetes/admin/sessions/")) {
    if ((_options.method || "GET").toUpperCase() === "POST") {
      return { success: true, session: demoKubernetesAdminSession() } as T;
    }
    return { success: true, sessions: [demoKubernetesAdminSession()] } as T;
  }
  if (path.includes("/api/kubernetes/admin/clusters/") && path.includes("/discovery/")) {
    return demoKubernetesAdminDiscovery() as T;
  }
  if (path.includes("/api/kubernetes/admin/clusters/") && path.includes("/yaml/")) {
    return {
      success: true,
      mode: "admin_read_only",
      operation: "resource_yaml",
      cluster: { id: "cluster_demo", name: "demo-cluster", rancher_cluster_id: "demo" },
      provider: { id: 0, name: "demo-rancher", kind: "rancher" },
      target: { api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespace: "demo", name: "demo-workload" },
      path: "/k8s/clusters/demo/apis/apps/v1/namespaces/demo/deployments/demo-workload",
      policy: {
        mutates_state: false,
        requires_active_admin_session: true,
        blocked_actions: ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
      },
      resource: {
        apiVersion: "apps/v1",
        kind: "Deployment",
        metadata: { name: "demo-workload", namespace: "demo", labels: { app: "demo" } },
        spec: { replicas: 1 },
      },
      redacted: false,
      ownership: demoKubernetesAdminOwnership(),
    } as T;
  }
  if (path.includes("/api/kubernetes/admin/clusters/") && path.includes("/crds/")) {
    return {
      success: true,
      mode: "admin_read_only",
      operation: "crd_list",
      cluster: { id: "cluster_demo", name: "demo-cluster", rancher_cluster_id: "demo" },
      provider: { id: 0, name: "demo-rancher", kind: "rancher" },
      target: { api_version: "apiextensions.k8s.io/v1", kind: "CustomResourceDefinition", resource: "customresourcedefinitions", namespace: "", name: "" },
      path: "/k8s/clusters/demo/apis/apiextensions.k8s.io/v1/customresourcedefinitions",
      policy: {
        mutates_state: false,
        requires_active_admin_session: true,
        blocked_actions: ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
      },
      items: [],
      item_count: 0,
      truncated: false,
    } as T;
  }
  if (path.includes("/api/kubernetes/admin/clusters/") && path.includes("/logs/")) {
    return {
      success: true,
      mode: "admin_read_only",
      operation: "pod_logs_snapshot",
      cluster: { id: "cluster_demo", name: "demo-cluster", rancher_cluster_id: "demo" },
      provider: { id: 0, name: "demo-rancher", kind: "rancher" },
      target: { api_version: "v1", kind: "Pod", resource: "pods", namespace: "demo", name: "demo-pod", container: "" },
      path: "/v3/pods/demo:demo-pod/logs",
      available: true,
      source: "provider_snapshot",
      lines: ["demo boot ok", "token=[redacted]", "ready"],
      line_count: 3,
      truncated: false,
      message: "",
      policy: {
        mutates_state: false,
        requires_active_admin_session: true,
        streaming: false,
        source: "rancher_provider_json",
        requested_tail_lines: 120,
        max_tail_lines: 500,
        blocked_actions: ["exec", "attach", "logs_streaming", "follow_stream", "port_forward", "delete", "restart", "scale", "apply_yaml"],
      },
    } as T;
  }
  if (path.includes("/api/kubernetes/admin/clusters/") && path.includes("/watch/")) {
    return {
      success: true,
      mode: "admin_read_only",
      operation: "resource_watch_preview",
      cluster: { id: "cluster_demo", name: "demo-cluster", rancher_cluster_id: "demo" },
      provider: { id: 0, name: "demo-rancher", kind: "rancher" },
      target: { api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespace: "demo", name: "" },
      path: "/k8s/clusters/demo/apis/apps/v1/namespaces/demo/deployments",
      available: true,
      source: "provider_watch_preview",
      events: [{ type: "MODIFIED", resource_version: "42", redacted: false, object: { kind: "Deployment", metadata: { name: "demo-workload", namespace: "demo", resourceVersion: "42" } } }],
      event_count: 1,
      truncated: false,
      latest_resource_version: "42",
      message: "",
      policy: { mutates_state: false, requires_active_admin_session: true, streaming: false, future_stream_transport: "websocket_or_sse", max_events: 50, requested_limit: 20, timeout_seconds: 10, blocked_actions: ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"] },
    } as T;
  }
  if (path.includes("/api/kubernetes/admin/clusters/") && path.includes("/resources/")) {
    return {
      success: true,
      mode: "admin_read_only",
      operation: "resource_list",
      cluster: { id: "cluster_demo", name: "demo-cluster", rancher_cluster_id: "demo" },
      provider: { id: 0, name: "demo-rancher", kind: "rancher" },
      target: { api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespace: "demo", name: "" },
      path: "/k8s/clusters/demo/apis/apps/v1/namespaces/demo/deployments",
      policy: {
        mutates_state: false,
        requires_active_admin_session: true,
        blocked_actions: ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
      },
      items: [
        {
          apiVersion: "apps/v1",
          kind: "Deployment",
          metadata: { name: "demo-workload", namespace: "demo", labels: { app: "demo" } },
          spec: { replicas: 1 },
          webterm_ownership: demoKubernetesAdminOwnership(),
        },
      ],
      item_count: 1,
      truncated: false,
      ownership_summary: { owners: { devtron: 1 }, guarded_items: 1, total: 1 },
    } as T;
  }
  if (path.includes("/api/kubernetes/actions/diagnose/")) {
    return {
      success: true,
      target_url: "/studio/drafts?draft=0",
      draft: {
        id: 0,
        status: "needs_input",
        intent: "create",
        title: "Kubernetes diagnosis: demo",
        user_goal: "Create a read-only Kubernetes diagnosis workflow.",
        source_pipeline_id: null,
        applied_pipeline_id: null,
        selected_node_id: "inspect",
        created_at: new Date(0).toISOString(),
        updated_at: new Date(0).toISOString(),
        applied_at: null,
        latest_revision: null,
      },
    } as T;
  }
  if (path.includes("/api/kubernetes/actions/request-approval/")) {
    return {
      success: true,
      request: {
        id: "00000000-0000-0000-0000-000000000000",
        database_id: 0,
        action: "k8s.rollout.restart",
        status: "pending_approval",
        risk_tier: "high",
        cluster: "demo-cluster",
        target: { cluster_id: "cluster_demo", namespace: "demo", kind: "deployment", name: "demo-workload" },
        preview: {
          summary: "Request a rollout restart for one workload after approval and verification.",
          blast_radius: "single_workload",
          inventory_match: true,
          affected: [{ cluster_id: "cluster_demo", namespace: "demo", kind: "deployment", name: "demo-workload" }],
          expected_verification: ["workload rollout status", "pod readiness", "recent warning events"],
        },
        execution_policy: {
          approval_required: true,
          dry_run_required: true,
          verification_required: true,
          native_execution_enabled: false,
          native_execution_mode: "disabled",
          allowed_execution_modes: ["rancher", "fleet", "devtron", "gitops_merge_request"],
          lifecycle: ["request", "preflight", "diff/preview", "approval", "execute", "verify", "report", "audit"],
          blocked_reason: "Direct cluster mutation is disabled in demo mode.",
        },
        report: {},
        reason: "demo request",
        approval_ref: "",
        requested_by: DEMO_SESSION.user?.username ?? "demo-user",
        created_at: new Date(0).toISOString(),
        updated_at: new Date(0).toISOString(),
      },
    } as T;
  }
  if (path.includes("/api/kubernetes/audit/deeplink/")) {
    return {
      success: true,
      event: {
        id: 0,
        action: "k8s.deeplink.open",
        username: DEMO_SESSION.user?.username ?? "demo-user",
        provider: "demo",
        cluster: "",
        payload: {},
        created_at: new Date(0).toISOString(),
      },
    } as T;
  }
  if (path.match(/\/api\/kubernetes\/workloads\/[^/]+\/describe\//)) {
    return {
      success: true,
      target: {
        id: "workload_demo",
        database_id: 0,
        source: "workload",
        name: "demo-workload",
        cluster_id: "cluster_demo",
        cluster_name: "demo-cluster",
        namespace: "demo",
        environment: "demo",
        owner: "rancher",
        team: "",
        health: "unknown",
        kind: "deployment",
        ready: 0,
        desired: 0,
        version: "",
        links: {},
        labels: {},
        last_sync_at: null,
        sync_status: "missing",
        is_stale: true,
        sync_age_seconds: null,
        sync_stale_after_seconds: 900,
      },
      related_events: [],
      policy: {
        mode: "read_only",
        mutates_state: false,
        source: "normalized_inventory",
        blocked_actions: ["exec", "logs_streaming", "rollout_restart", "scale", "delete", "apply_yaml", "port_forward"],
      },
      manifest_preview: {
        apiVersion: "apps/v1",
        kind: "Deployment",
        metadata: { name: "demo-workload", namespace: "demo", labels: {} },
        spec_summary: { owner: "rancher", desired: 0 },
        status_summary: { health: "unknown", ready: 0, desired: 0, sync_status: "missing", last_sync_at: null },
      },
    } as T;
  }
  if (path.match(/\/api\/kubernetes\/pods\/[^/]+\/logs\//)) {
    return {
      success: true,
      available: false,
      source: "not_configured",
      target: {
        id: "pod_demo",
        database_id: 0,
        cluster_id: "cluster_demo",
        cluster_name: "demo-cluster",
        namespace: "demo",
        name: "demo-pod",
        environment: "demo",
        health: "unknown",
        phase: "",
        node_name: "",
        pod_ip: "",
        host_ip: "",
        owner_kind: "",
        owner_name: "",
        ready_containers: 0,
        total_containers: 0,
        restart_count: 0,
        images: [],
        links: {},
        labels: {},
        last_sync_at: null,
        sync_status: "missing",
        is_stale: true,
        sync_age_seconds: null,
        sync_stale_after_seconds: 900,
      },
      policy: {
        mode: "read_only",
        mutates_state: false,
        streaming: false,
        source: "rancher_provider_json",
        requested_tail_lines: 120,
        max_tail_lines: 500,
        blocked_actions: ["exec", "attach", "logs_streaming", "follow_stream", "port_forward", "delete", "restart", "scale", "apply_yaml"],
      },
      provider: null,
      lines: [],
      line_count: 0,
      truncated: false,
      message: "Provider pod_logs_path_template is not configured.",
    } as T;
  }
  if (path.includes("/api/kubernetes/overview/")) {
    return {
      success: true,
      readiness: demoKubernetesReadiness(),
      summary: { clusters: 0, apps: 0, fleet_rollouts: 0, incidents: 0, warnings: 0, rolling: 0, paused: 0, stale: 0, provider_issues: 0 },
      providers: [],
      clusters: [],
      apps: [],
      fleet_rollouts: [],
    } as T;
  }
  if (path.match(/\/api\/kubernetes\/clusters\/[^/]+\/namespaces\//)) {
    return { success: true, cluster: demoKubernetesCluster(), namespaces: [] } as T;
  }
  if (path.match(/\/api\/kubernetes\/clusters\/[^/]+\/workloads\//)) {
    return { success: true, cluster: demoKubernetesCluster(), workloads: [] } as T;
  }
  if (path.match(/\/api\/kubernetes\/clusters\/[^/]+\/pods\//)) {
    return { success: true, cluster: demoKubernetesCluster(), pods: [] } as T;
  }
  if (path.match(/\/api\/kubernetes\/clusters\/[^/]+\/network\//)) {
    return { success: true, cluster: demoKubernetesCluster(), network_refs: [] } as T;
  }
  if (path.match(/\/api\/kubernetes\/clusters\/[^/]+\/events\//)) {
    return { success: true, cluster: demoKubernetesCluster(), events: [] } as T;
  }
  if (path.match(/\/api\/kubernetes\/clusters\/?$/)) {
    return { success: true, clusters: [demoKubernetesCluster()] } as T;
  }
  if (path.match(/\/api\/kubernetes\/clusters\/[^/]+\/?$/)) {
    return { success: true, cluster: demoKubernetesCluster() } as T;
  }
  if (path.includes("/api/kubernetes/")) {
    return { success: true, providers: [], clusters: [], bundles: [], apps: [], events: [], namespaces: [], workloads: [] } as T;
  }
  return undefined;
}

function demoKubernetesCluster() {
  return {
    id: "cluster_demo",
    database_id: 0,
    name: "demo-cluster",
    environment: "demo",
    provider: "",
    health: "unknown",
    nodes_ready: 0,
    nodes_total: 0,
    namespaces: 0,
    workloads: 0,
    apps: 0,
    fleet_bundles: 0,
    devtron_apps: 0,
    labels: {},
    links: {},
    last_sync_at: null,
    sync_status: "missing",
    is_stale: true,
    sync_age_seconds: null,
    sync_stale_after_seconds: 900,
    created_at: null,
    updated_at: null,
  };
}

function demoKubernetesAdminSession() {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    database_id: 0,
    mode: "read",
    status: "active",
    risk_tier: "low",
    cluster_id: "cluster_demo",
    cluster_name: "demo-cluster",
    provider_id: 0,
    provider_name: "demo-rancher",
    namespace: "demo",
    reason: "",
    approval_ref: "",
    approved_by: "",
    approved_at: null,
    expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    closed_at: null,
    allowed_verbs: ["get", "list", "watch", "logs", "yaml"],
    allowed_kinds: ["*"],
    allowed_namespaces: ["*"],
    metadata: {},
    created_by: DEMO_SESSION.user?.username ?? "demo-user",
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
  };
}

function demoKubernetesAdminOwnership() {
  return {
    owner: "devtron",
    confidence: "normalized_inventory",
    change_path: "devtron_app_flow",
    direct_apply_policy: "blocked_by_default",
    current_mode: "read_only",
    warnings: ["Devtron-owned resource: prefer Devtron AppOps flow or audited rollback context."],
    evidence: ["matched_devtron_app"],
    workload: null,
    app: {
      id: "app_demo",
      name: "demo-workload",
      namespace: "demo",
      owner: "devtron",
      team: "platform",
      health: "healthy",
      version: "demo",
      labels: {},
      links: {},
    },
    fleet_bundle: null,
  };
}

function demoKubernetesReadiness() {
  return {
    success: true,
    status: "not_configured",
    ready_for_sidebar: false,
    summary: { ready: 1, missing: 6, manual: 1, total: 8 },
    checks: [
      { id: "architecture_guard", status: "ready", detail: "Repository guard must pass before enabling the module.", required: true },
      { id: "rancher_provider", status: "missing", detail: "Rancher provider is not configured.", required: true },
      { id: "devtron_provider", status: "missing", detail: "Devtron provider is not configured.", required: true },
      { id: "provider_health", status: "missing", detail: "No enabled providers are configured.", required: true },
      { id: "read_only_sync", status: "missing", detail: "No normalized inventory rows are available yet.", required: true },
      { id: "sync_worker", status: "missing", detail: "Kubernetes periodic sync worker is not running.", required: true },
      {
        id: "studio_automation",
        status: "missing",
        detail: "Studio diagnosis draft is not launch-ready: Studio MCP access, owned Kubernetes MCP server.",
        required: false,
      },
      { id: "frontend_e2e", status: "manual", detail: "Frontend e2e evidence must be produced by release pipeline.", required: false },
    ],
    access_policy: {
      can_read: true,
      can_admin_read: true,
      can_live_resource_get: true,
      can_view_full_yaml: true,
      can_stream_logs: true,
      can_admin_write: false,
      can_dry_run_apply: false,
      can_apply_yaml: false,
      can_scale: false,
      can_delete: false,
      can_exec: false,
      can_port_forward: false,
      can_break_glass: false,
      blocked_capabilities: ["pod.exec", "port_forward", "node_debug", "cluster_terminal", "scale", "delete", "apply_yaml"],
    },
    worker_state: {
      worker_kind: "kubernetes_ops_sync",
      worker_key: "default",
      status: "missing",
      is_stale: true,
      hostname: "",
      pid: null,
      command: "python manage.py run_kubernetes_ops_sync_worker --daemon",
      heartbeat_at: null,
      lease_expires_at: null,
      last_started_at: null,
      last_stopped_at: null,
      last_cycle_started_at: null,
      last_cycle_finished_at: null,
      last_summary: {},
      last_error: "",
    },
  };
}
