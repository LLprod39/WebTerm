import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  approveExternalKubernetesAction,
  createKubernetesActionRequest,
  createKubernetesDiagnosisDraft,
  fetchAuthSession,
  fetchKubernetesActionReport,
  fetchKubernetesOverview,
  verifyExternalKubernetesAction,
} from "@/api";
import { I18nProvider } from "@/lib/i18n";
import KubernetesPage from "@/pages/KubernetesPage";
import { featureMap } from "@/test/featureFlags";

vi.mock("@/api", () => ({
  approveExternalKubernetesAction: vi.fn(),
  createKubernetesActionRequest: vi.fn(),
  createKubernetesDiagnosisDraft: vi.fn(),
  createKubernetesProvider: vi.fn(),
  deleteKubernetesProvider: vi.fn(),
  fetchAuthSession: vi.fn(),
  fetchKubernetesActionReport: vi.fn(),
  fetchKubernetesOverview: vi.fn(),
  probeKubernetesProvider: vi.fn(),
  recordKubernetesDeepLink: vi.fn(),
  syncKubernetesProvider: vi.fn(),
  updateKubernetesProvider: vi.fn(),
  verifyExternalKubernetesAction: vi.fn(),
}));

function overviewFixture() {
  return {
    success: true,
    readiness: {
      success: true,
      status: "not_configured",
      ready_for_sidebar: false,
      summary: { ready: 1, missing: 6, manual: 1, total: 8 },
      checks: [
        {
          id: "architecture_guard",
          status: "ready",
          detail: "Repository guard is checked outside request path.",
          required: true,
        },
        { id: "rancher_provider", status: "missing", detail: "Rancher provider is not configured.", required: true },
        { id: "devtron_provider", status: "missing", detail: "Devtron provider is not configured.", required: true },
        { id: "provider_health", status: "missing", detail: "No enabled providers are configured.", required: true },
        { id: "read_only_sync", status: "missing", detail: "No normalized rows yet.", required: true },
        { id: "sync_worker", status: "missing", detail: "Sync worker is not running.", required: true },
        { id: "studio_automation", status: "missing", detail: "Studio diagnosis draft is not launch-ready.", required: false },
        { id: "frontend_e2e", status: "manual", detail: "E2E evidence must be produced manually.", required: false },
      ],
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
    },
    summary: { clusters: 0, apps: 0, fleet_rollouts: 0, incidents: 0, warnings: 0, rolling: 0, paused: 0, stale: 0, provider_issues: 0 },
    providers: [],
    clusters: [],
    workloads: [],
    apps: [],
    fleet_rollouts: [],
  };
}

function appFixture() {
  return {
    id: "app_1",
    database_id: 1,
    name: "payments-api",
    cluster_id: "cluster_1",
    cluster_name: "prod-kz-1",
    namespace: "payments",
    environment: "prod",
    owner: "devtron",
    team: "payments",
    health: "warning",
    version: "2026.06.30-1",
    links: {},
    labels: {},
    last_sync_at: "2026-06-30T08:00:00Z",
    sync_status: "fresh",
    is_stale: false,
    sync_age_seconds: 30,
    sync_stale_after_seconds: 900,
  };
}

function workloadFixture() {
  return {
    ...appFixture(),
    id: "workload_1",
    database_id: 1,
    name: "broken-worker",
    namespace: "webterm-prod",
    owner: "rancher",
    health: "degraded",
    kind: "deployment",
    ready: 0,
    desired: 1,
  };
}

function actionRequestFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "request-1",
    database_id: 1,
    action: "k8s.rollout.restart",
    status: "pending_approval",
    risk_tier: "high",
    cluster: "prod-kz-1",
    target: { workload_id: "workload_1", namespace: "webterm-prod", name: "broken-worker" },
    preview: {
      blast_radius: "single_workload",
      affected: [{ namespace: "webterm-prod", name: "broken-worker" }],
      expected_verification: ["workload rollout status"],
    },
    execution_policy: {
      approval_required: true,
      dry_run_required: true,
      native_execution_enabled: false,
      blocked_reason: "Direct cluster mutation stays disabled.",
    },
    report: {},
    reason: "Operator requested restart approval for webterm-prod/broken-worker",
    approval_ref: "",
    requested_by: "admin",
    created_at: "2026-06-30T08:00:00Z",
    updated_at: "2026-06-30T08:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <KubernetesPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("KubernetesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        is_staff: true,
        features: featureMap({ kubernetes: true, studio_pipelines: true }),
      },
    });
    vi.mocked(fetchKubernetesOverview).mockResolvedValue(overviewFixture());
    vi.mocked(createKubernetesDiagnosisDraft).mockResolvedValue({
      success: true,
      target_url: "/studio/drafts?draft=5",
      draft: {
        id: 5,
        status: "ready",
        intent: "create",
        title: "Kubernetes diagnosis: payments/payments-api",
        user_goal: "Create a read-only Kubernetes diagnosis workflow.",
        source_pipeline_id: null,
        applied_pipeline_id: null,
        selected_node_id: "inspect",
        created_at: "2026-06-30T08:00:00Z",
        updated_at: "2026-06-30T08:00:00Z",
        applied_at: null,
        latest_revision: null,
      },
    });
    vi.mocked(createKubernetesActionRequest).mockResolvedValue({
      success: true,
      request: actionRequestFixture(),
    });
    vi.mocked(fetchKubernetesActionReport).mockResolvedValue({
      success: true,
      request_id: "request-1",
      status: "pending_approval",
      request: actionRequestFixture(),
      report: {},
      execution_policy: {
        approval_required: true,
        dry_run_required: true,
        native_execution_enabled: false,
        blocked_reason: "Direct cluster mutation stays disabled.",
      },
      timeline: [
        {
          action: "k8s.action_request.create",
          username: "admin",
          created_at: "2026-06-30T08:00:01Z",
          payload: { request_id: "request-1", status: "pending_approval" },
        },
      ],
    });
    vi.mocked(approveExternalKubernetesAction).mockResolvedValue({
      success: true,
      request: actionRequestFixture({
        status: "approved_external",
        approval_ref: "CHG-K8S-123",
        execution_policy: {
          approval_required: true,
          dry_run_required: true,
          native_execution_enabled: false,
          external_approval_recorded: true,
          blocked_reason: "Direct cluster mutation stays disabled.",
        },
        report: { status: "approved_external", approved: true, approval_ref: "CHG-K8S-123" },
        updated_at: "2026-06-30T08:01:00Z",
      }),
    });
    vi.mocked(verifyExternalKubernetesAction).mockResolvedValue({
      success: true,
      request: actionRequestFixture({
        status: "verified_external",
        approval_ref: "CHG-K8S-123",
        execution_policy: {
          approval_required: true,
          dry_run_required: true,
          native_execution_enabled: false,
          external_approval_recorded: true,
          external_verification_recorded: true,
          blocked_reason: "Direct cluster mutation stays disabled.",
        },
        report: { status: "verified_external", verified: true, summary: "Pods are ready." },
        updated_at: "2026-06-30T08:02:00Z",
      }),
    });
  });

  it("renders an operator overview without admin provider controls", async () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Обзор кластеров" })).toBeInTheDocument();
    expect(await screen.findByText("Требуется настройка")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Кластеры" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Требует внимания" })).toBeInTheDocument();
    expect(screen.queryByText("Админ-диагностика")).not.toBeInTheDocument();
    expect(screen.queryByText("Внутренний режим")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Настройка провайдеров" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Readiness gate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Sync worker" })).not.toBeInTheDocument();
    expect(screen.queryByText("Пустая страница")).not.toBeInTheDocument();
  });

  it("creates a read-only Studio diagnosis draft from an app row", async () => {
    const overview = overviewFixture();
    vi.mocked(fetchKubernetesOverview).mockResolvedValue({
      ...overview,
      summary: { ...overview.summary, apps: 1, warnings: 1 },
      apps: [appFixture()],
    });

    renderPage();

    expect((await screen.findAllByText("payments-api")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Создать диагностику payments-api" })[0]);

    await waitFor(() => {
      expect(createKubernetesDiagnosisDraft).toHaveBeenCalledWith({ app_id: "app_1" });
    });
  });

  it("does not treat unknown Devtron app health as an attention item", async () => {
    const overview = overviewFixture();
    vi.mocked(fetchKubernetesOverview).mockResolvedValue({
      ...overview,
      summary: { ...overview.summary, apps: 1 },
      apps: [{ ...appFixture(), id: "app_unknown", name: "unknown-api", health: "unknown" }],
    });

    renderPage();

    expect(await screen.findByText("unknown-api")).toBeInTheDocument();
    expect(await screen.findByText("Критичных приложений нет")).toBeInTheDocument();
  });

  it("shows degraded Rancher workloads in the attention section", async () => {
    const overview = overviewFixture();
    vi.mocked(fetchKubernetesOverview).mockResolvedValue({
      ...overview,
      summary: { ...overview.summary, incidents: 1, warnings: 1 },
      workloads: [workloadFixture()],
    });

    renderPage();

    expect(await screen.findByText("broken-worker")).toBeInTheDocument();
    expect(screen.queryByText("Критичных приложений нет")).not.toBeInTheDocument();
  });

  it("creates a policy-blocked restart approval request from an attention workload", async () => {
    const overview = overviewFixture();
    vi.mocked(fetchKubernetesOverview).mockResolvedValue({
      ...overview,
      summary: { ...overview.summary, incidents: 1, warnings: 1 },
      workloads: [workloadFixture()],
    });

    renderPage();

    expect(await screen.findByText("broken-worker")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Запросить перезапуск broken-worker" }));

    await waitFor(() => {
      expect(createKubernetesActionRequest).toHaveBeenCalledWith({
        action: "k8s.rollout.restart",
        reason: "Operator requested restart approval for webterm-prod/broken-worker",
        target: { workload_id: "workload_1" },
      });
    });
    expect(await screen.findByText("Заявка на действие")).toBeInTheDocument();
    expect(screen.getByText("выполнение выключено")).toBeInTheDocument();
    expect(await screen.findByText("Заявка создана")).toBeInTheDocument();
    expect(fetchKubernetesActionReport).toHaveBeenCalledWith("request-1");
    expect(screen.queryByRole("button", { name: /execute/i })).not.toBeInTheDocument();
  });

  it("lets staff record external approval and verification without native execution", async () => {
    const overview = overviewFixture();
    vi.mocked(fetchKubernetesOverview).mockResolvedValue({
      ...overview,
      summary: { ...overview.summary, incidents: 1, warnings: 1 },
      workloads: [workloadFixture()],
    });

    renderPage();

    expect(await screen.findByText("broken-worker")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Запросить перезапуск broken-worker" }));
    expect(await screen.findByText("Внешнее выполнение")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Ссылка на согласование"), { target: { value: "CHG-K8S-123" } });
    fireEvent.change(screen.getByLabelText("Сводка согласования"), { target: { value: "Approved after CAB review." } });
    fireEvent.click(screen.getByRole("button", { name: "Записать внешнее согласование" }));

    await waitFor(() => {
      expect(approveExternalKubernetesAction).toHaveBeenCalledWith("request-1", {
        approval_ref: "CHG-K8S-123",
        summary: "Approved after CAB review.",
      });
    });
    expect(await screen.findByText("согласовано вне WebTerm")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Ссылка на внешнее подтверждение"), {
      target: { value: "https://rancher.example.test/dashboard/c/local/apps/deployments/broken-worker" },
    });
    fireEvent.change(screen.getByLabelText("Сводка проверки"), { target: { value: "Pods are ready." } });
    fireEvent.click(screen.getByRole("button", { name: "Записать внешнюю проверку" }));

    await waitFor(() => {
      expect(verifyExternalKubernetesAction).toHaveBeenCalledWith("request-1", {
        outcome: "succeeded",
        summary: "Pods are ready.",
        external_ref: "https://rancher.example.test/dashboard/c/local/apps/deployments/broken-worker",
      });
    });
    expect(await screen.findByText("проверено вне WebTerm")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /execute/i })).not.toBeInTheDocument();
  });
});
