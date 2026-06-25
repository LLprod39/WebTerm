import { expect, test } from "@playwright/test";
import { installApiHarness, json } from "./support/apiHarness";

const fullFeatures = {
  servers: true,
  dashboard: true,
  agents: true,
  studio: true,
  settings: true,
  orchestrator: true,
};

const FIXED_DATE = "2026-03-01T08:00:00.000Z";

type AgentMode = "mini" | "full" | "multi";

type AgentItem = {
  id: number;
  name: string;
  mode: AgentMode;
  agent_type: string;
  agent_type_display: string;
  server_count: number;
  last_run_at: string | null;
  schedule_minutes: number;
  schedule_config?: Record<string, unknown>;
  max_iterations: number;
  goal: string;
  is_enabled?: boolean;
  sudo_policy?: "disabled" | "ask" | "approved";
  active_run_id: number | null;
  last_run_id: number | null;
  execution_readiness?: {
    required: boolean;
    ready: boolean;
    status: string;
    severity: "success" | "info" | "warning" | "high" | "critical" | "fatal";
    title: string;
    description: string;
    next_action: string;
    worker: Record<string, unknown> | null;
  };
};

function workerState(overrides: Record<string, unknown> = {}) {
  return {
    worker_kind: "scheduled_agents",
    worker_key: "default",
    status: "missing",
    is_stale: true,
    hostname: "",
    pid: null,
    command: "",
    heartbeat_at: null,
    lease_expires_at: null,
    last_started_at: null,
    last_stopped_at: null,
    last_cycle_started_at: null,
    last_cycle_finished_at: null,
    last_summary: {},
    last_error: "",
    ...overrides,
  };
}

function runtimeOverview(overrides: Record<string, unknown> = {}) {
  return {
    status: "idle",
    severity: "info",
    summary: {
      configured_agents: 0,
      active_runs: 0,
      pending_runs: 0,
      running_runs: 0,
      waiting_runs: 0,
      queued_dispatches: 0,
      claimed_dispatches: 0,
      scheduled_agents: 0,
      scheduled_due_now: 0,
      issues: 0,
    },
    queue: {
      runs: {},
      dispatches: {},
    },
    schedule: {
      total_scheduled: 0,
      enabled: 0,
      paused: 0,
      due_now: 0,
      worker_ready: false,
    },
    workers: {},
    execution_readiness: {
      required: true,
      ready: false,
      status: "missing",
      severity: "warning",
      title: "Execution worker не запущен",
      description: "Full/multi-агенты будут поставлены в очередь, но не начнут выполняться до запуска worker.",
      next_action: "python manage.py run_agent_execution_plane --worker-key default",
      worker: null,
    },
    issues: [],
    commands: {
      execution_worker: "python manage.py run_agent_execution_plane --worker-key default",
      scheduled_agents_worker: "python manage.py run_scheduled_agents --daemon --worker-key default",
      ops_supervisor: "python manage.py run_ops_supervisor --with-scheduled-agents --with-watchers",
    },
    items: {
      active_runs: [],
      queued_dispatches: [],
      scheduled_due: [],
      stale_candidates: [],
    },
    generated_at: FIXED_DATE,
    ...overrides,
  };
}

function normalizeAgent(agent: AgentItem): AgentItem {
  return {
    schedule_config: { mode: "manual" },
    is_enabled: true,
    sudo_policy: "ask",
    ...agent,
  };
}

function buildRunDetail(runId: number, agentId: number, agentName: string) {
  return {
    success: true,
    run: {
      id: runId,
      agent_id: agentId,
      agent_name: agentName,
      agent_type: "custom",
      agent_mode: "full",
      server_name: "Web-01",
      status: "running",
      ai_analysis: "",
      commands_output: [],
      duration_ms: 5_000,
      started_at: FIXED_DATE,
      completed_at: null,
      iterations_log: [],
      tool_calls: [],
      total_iterations: 3,
      connected_servers: [{ server_id: 1, server_name: "Web-01" }],
      final_report: "",
      pending_question: "",
      plan_tasks: [],
      orchestrator_log: [],
    },
  };
}

function buildRunLog(status = "running") {
  return {
    success: true,
    iterations_log: [],
    tool_calls: [],
    total_iterations: 3,
    status,
    pending_question: "",
    plan_tasks: [],
  };
}

function buildRunReport(detail: ReturnType<typeof buildRunDetail>) {
  const run = detail.run as ReturnType<typeof buildRunDetail>["run"] & { user_reply?: string };
  const isStopped = run.status === "stopped";
  const isFailed = run.status === "failed";
  const isCompleted = run.status === "completed";
  const isWaiting = run.status === "waiting";
  const isTerminal = isStopped || isFailed || isCompleted;
  const isStale = run.agent_name.toLowerCase().includes("stale") && !isTerminal;
  const artifactBundleUrl = `/servers/api/agents/runs/${run.id}/artifacts/download-all/`;
  const reportDescription = "Агент выполняет проверки и собирает доказательства для финального отчёта.";
  const dispatch = {
    id: 801,
    run_id: run.id,
    dispatch_kind: "launch",
    status: isStopped ? "canceled" : isFailed ? "canceled" : "queued",
    server_ids: [1],
    plan_only: false,
    queued_at: run.started_at,
    claimed_at: null,
    heartbeat_at: null,
    lease_expires_at: null,
    completed_at: run.completed_at,
    claimed_by: "",
    attempt_count: 0,
    error: isStopped ? "operator_stop_requested" : isFailed ? "operator_stale_cleanup" : "",
    metadata: {},
  };

  return {
    success: true,
    schema_version: 1,
    run: {
      id: run.id,
      agent_id: run.agent_id,
      agent_name: run.agent_name,
      agent_type: run.agent_type,
      agent_mode: run.agent_mode,
      server_name: run.server_name,
      server_id: 1,
      status: run.status,
      duration_ms: run.duration_ms,
      started_at: run.started_at,
      completed_at: run.completed_at,
      total_iterations: run.total_iterations,
      connected_servers: run.connected_servers,
      pending_question: run.pending_question,
      dispatch,
    },
    report_state: {
      phase: isCompleted ? "ready" : isStopped ? "stopped" : isFailed ? "failed" : isWaiting ? "waiting" : "executing",
      report_ready: isCompleted,
      artifacts_ready: isCompleted,
      is_terminal: isTerminal,
      headline: isCompleted ? "Финальный отчёт готов" : isStopped ? "Запуск остановлен" : isFailed ? "Запуск завершился ошибкой" : isWaiting ? "Агент ждёт ответа" : "Агент выполняет проверки",
      description:
        isCompleted
          ? "Структурированный отчёт сохранён. Артефакты готовы к скачиванию."
          : isStopped
          ? "Оператор остановил выполнение до формирования финального отчёта."
          : isFailed
            ? "Stale-запуск очищен оператором до формирования финального отчёта."
          : isWaiting
            ? run.pending_question || "Агент поставил выполнение на паузу до ответа оператора."
          : `${reportDescription} Dispatch ждёт в очереди 5s. Статус worker: missing.`,
      current_step: isCompleted ? "Финальный отчёт готов" : isStopped ? "Запуск остановлен" : isFailed ? "Запуск очищен" : isWaiting ? "Ожидает ответа оператора" : isStale ? "Запуск завис в очереди" : "Execution worker не принимает запуск",
      next_expected:
        isCompleted
          ? "Дополнительных действий не требуется."
          : isStopped
          ? "При необходимости запустите агент повторно."
          : isFailed
            ? "При необходимости запустите агент повторно."
          : isWaiting
            ? "Ответьте на вопрос агента, чтобы продолжить выполнение."
          : "Запустите worker: python manage.py run_agent_execution_plane --worker-key default",
      progress: isTerminal ? 100 : isWaiting ? 68 : 62,
      execution_state: {
        status: isStopped || isFailed ? "dispatch_canceled" : isWaiting ? "waiting_for_operator" : "worker_missing",
        severity: "warning",
        title: isStopped ? "Dispatch отменён" : isFailed ? "Запуск failed" : isWaiting ? "Агент ждёт ответа" : isStale ? "Запуск завис в очереди" : "Execution worker не принимает запуск",
        description: isStopped
          ? "Очередь запуска была отменена."
          : isFailed
            ? "Stale-запуск очищен оператором."
            : isWaiting
              ? run.pending_question || "Выполнение ожидает ответа оператора."
            : isStale
              ? "Dispatch ждёт в очереди 5m. Runtime превысил stale threshold."
              : "Dispatch ждёт в очереди 5s. Статус worker: missing.",
        next_action:
          isStopped || isFailed
            ? "При необходимости запустите агент заново."
            : isWaiting
              ? "Ответьте на вопрос агента на странице отчёта."
            : isStale
              ? "Очистите stale run или запустите execution worker, если запуск ещё должен выполняться."
            : "Запустите worker: python manage.py run_agent_execution_plane --worker-key default",
        dispatch,
        worker: {
          worker_kind: "agent_execution",
          worker_key: "",
          status: "missing",
          is_stale: true,
          hostname: "",
          pid: null,
          command: "",
          heartbeat_at: null,
          heartbeat_age_ms: null,
          lease_expires_at: null,
          last_started_at: null,
          last_stopped_at: null,
          last_cycle_started_at: null,
          last_cycle_finished_at: null,
          last_summary: {},
          last_error: "",
        },
        queued_age_ms: isStale ? 300000 : 5000,
        queued_for: isStale ? "5m" : "5s",
        heartbeat_age_ms: null,
        heartbeat_age: "—",
        runtime_age_ms: isStale ? 300000 : 5000,
        runtime_age: isStale ? "5m" : "5s",
        stale_after_ms: 60000,
        stale_after: "1m",
        is_stale_candidate: isStale,
        can_cleanup: isStale,
        lease_expired: false,
        worker_ready: false,
      },
    },
    artifact_state: {
      ready: isCompleted,
      title: isCompleted ? "Артефакты отчёта готовы" : "Артефакты ещё не готовы",
      description: isCompleted ? "Файлы собраны из финального отчёта и сохранённых данных запуска." : "Артефакты появятся только после того, как агент сохранит финальный markdown-отчёт.",
      empty_title: isCompleted ? "" : "Артефакты появятся после финального отчёта",
      empty_description: isCompleted ? "" : "После выполнения агент соберёт итоговый markdown-отчёт.",
      bundle_ready: isCompleted,
      bundle_download_url: isCompleted ? artifactBundleUrl : "",
      artifact_count: isCompleted ? 3 : 0,
      total_size_bytes: isCompleted ? 3072 : 0,
      total_size_label: isCompleted ? "3.0 KB" : "0 B",
      manifest_ready: isCompleted,
      manifest_name: isCompleted ? "artifact-manifest.json" : "",
    },
    delivery_state: {
      enabled: true,
      channels: ["telegram"],
      channel: "telegram",
      target: "***6789",
      status: isCompleted ? "sent" : "waiting_report",
      severity: isCompleted ? "success" : "info",
      label: isCompleted ? "Доставлено" : "Ждёт отчёт",
      title: isCompleted ? "Отчёт доставлен" : "Доставка ждёт финальный отчёт",
      description: isCompleted
        ? "Отчёт отправлен в Telegram."
        : "Внешняя доставка включена, но финальный отчёт ещё не сформирован.",
      next_action: isCompleted ? "" : "Дождитесь завершения агента.",
      updated_at: isCompleted ? run.completed_at : null,
      event: null,
    },
    report: {
      schema_version: 1,
      title: run.agent_name,
      subtitle: isCompleted
        ? "Структурированный отчёт сохранён. Артефакты готовы к скачиванию."
        : isStopped
        ? "Оператор остановил выполнение до формирования финального отчёта."
        : isFailed
          ? "Stale-запуск очищен оператором до формирования финального отчёта."
        : isWaiting
          ? "Агент ожидает ответа оператора."
          : `${reportDescription} Dispatch ждёт в очереди 5s. Статус worker: missing.`,
      status: run.status,
      status_label: isCompleted ? "Завершен" : isStopped ? "Остановлен" : isFailed ? "Ошибка" : isWaiting ? "Ожидание" : "Выполняется",
      severity: isCompleted ? "success" : isStopped || isFailed || isWaiting ? "warning" : "info",
      summary: isCompleted
        ? "Структурированный отчёт сохранён. Артефакты готовы к скачиванию."
        : isStopped
        ? "Оператор остановил выполнение до формирования финального отчёта."
        : isFailed
          ? "Stale-запуск очищен оператором до формирования финального отчёта."
        : isWaiting
          ? "Агент поставил запуск на паузу и ждёт ответа оператора."
          : reportDescription,
      root_cause: null,
      markdown: isCompleted ? "# Final\n\n## Что произошло\n- Агент завершил проверку.\n" : "",
      meta: {
        server: run.server_name,
        window: run.started_at,
        analysis_duration: "5s",
        finished_at: run.completed_at,
        started_at: run.started_at,
      },
      kpis: [
        {
          id: "status",
          label: "Статус",
          value: isCompleted ? "Завершен" : isStopped ? "Остановлен" : isFailed ? "Ошибка" : isWaiting ? "Ожидание" : "Выполняется",
          hint: run.status,
          severity: isCompleted ? "success" : isStopped || isFailed || isWaiting ? "warning" : "info",
        },
        { id: "duration", label: "Длительность", value: "5s", hint: "runtime", severity: "info" },
      ],
      findings: Array.from({ length: 8 }, (_, index) => ({
        id: `finding-${index + 1}`,
        title: `Collected execution signal ${index + 1}`,
        description: "The run page keeps enough report content to exercise scrolling.",
        severity: index === 2 ? "high" : "info",
        source: "report",
      })),
      risks: Array.from({ length: 4 }, (_, index) => ({
        id: `risk-${index + 1}`,
        title: `Review rollout blocker ${index + 1}`,
        description: "Operator review is required before the run can be considered complete.",
        severity: index === 0 ? "high" : "warning",
        source: "report",
      })),
      recommendations: [
        {
          id: "review",
          priority: "P2",
          title: "Review the final report after completion.",
          description: "",
          owner: "Operator",
          done: false,
        },
      ],
    },
    events: [
      {
        id: 1,
        run_id: run.id,
        event_type: "agent_started",
        task_id: null,
        message: "Agent run started.",
        payload: {},
        created_at: run.started_at,
        severity: "info",
        source: "agent",
        title: "Запуск создан",
        summary: "Agent run started.",
        phase: "starting",
        category: "system",
        important: true,
      },
      {
        id: 2,
        run_id: run.id,
        event_type: "agent_task_start",
        task_id: 2,
        message: "Running package readiness checks.",
        payload: { command: "apt list --upgradable" },
        created_at: run.started_at,
        severity: "info",
        source: "task",
        title: "Apply patch window checks",
        summary: "Running package readiness checks.",
        phase: "executing",
        category: "task",
        important: true,
      },
      {
        id: 3,
        run_id: run.id,
        event_type: "agent_task_failed",
        task_id: 2,
        message: "Package lock check returned a warning exit code.",
        payload: { command: "apt-get check", exit_code: 100 },
        created_at: run.started_at,
        severity: "critical",
        source: "command",
        title: "Package lock check failed",
        summary: "apt-get check вернул код 100, rollout требует ручной проверки.",
        phase: "executing",
        category: "task",
        important: true,
      },
      ...(isWaiting
        ? [
            {
              id: 4,
              run_id: run.id,
              event_type: "agent_question",
              task_id: null,
              message: run.pending_question,
              payload: { question: run.pending_question },
              created_at: run.started_at,
              severity: "warning",
              source: "agent",
              title: "Агент ждёт ответа",
              summary: run.pending_question,
              phase: "waiting",
              category: "agent",
              important: true,
            },
          ]
        : []),
      ...(run.user_reply
        ? [
            {
              id: 5,
              run_id: run.id,
              event_type: "agent_user_reply",
              task_id: null,
              message: "Operator replied to pending agent question",
              payload: { answer: run.user_reply },
              created_at: FIXED_DATE,
              severity: "success",
              source: "operator",
              title: "Ответ отправлен агенту",
              summary: run.user_reply,
              phase: "waiting",
              category: "agent",
              important: true,
            },
          ]
        : []),
    ],
    logs: [],
    agent_steps: [
      {
        id: "1",
        index: 1,
        title: "Inspect service health",
        description: "Collect systemd and disk status before applying changes.",
        command: "systemctl is-active nginx",
        status: "done",
        severity: "success",
        status_label: "Завершено",
        duration_ms: 1250,
        details: "nginx is active, disk usage is below threshold.",
        error: "",
        started_at: run.started_at,
        completed_at: run.started_at,
      },
      {
        id: "2",
        index: 2,
        title: "Apply patch window checks",
        description: "Verify the maintenance window and prepare the package update.",
        command: "run_command",
        status: isWaiting ? "waiting" : "running",
        severity: isWaiting ? "warning" : "info",
        status_label: isWaiting ? "Ожидает ответа" : "Выполняется",
        duration_ms: 0,
        details: isWaiting ? run.pending_question : "Checking package locks and pending services.",
        error: "",
        started_at: run.started_at,
        completed_at: null,
      },
      {
        id: "3",
        index: 3,
        title: "Write completion report",
        description: "Summarize commands, risks, and next verification steps.",
        command: "",
        status: "pending",
        severity: "info",
        status_label: "Ожидает",
        duration_ms: 0,
        details: "",
        error: "",
        started_at: null,
        completed_at: null,
      },
    ],
    artifacts: isCompleted
      ? [
          {
            id: "final-report",
            name: "final-report.md",
            type: "Markdown",
            description: "Readable final report.",
            size_bytes: 256,
            size_label: "256 B",
            created_at: run.completed_at,
            artifact_id: 51,
            download_kind: "server",
            download_url: `/servers/api/agents/runs/${run.id}/artifacts/51/download/`,
            content_type: "text/markdown",
            content: "",
            truncated: false,
            checksum_sha256: "a".repeat(64),
          },
          {
            id: "run-context",
            name: "run-context.json",
            type: "JSON",
            description: "Normalized run metadata and structured report context.",
            size_bytes: 1792,
            size_label: "1.8 KB",
            created_at: run.completed_at,
            artifact_id: 52,
            download_kind: "server",
            download_url: `/servers/api/agents/runs/${run.id}/artifacts/52/download/`,
            content_type: "application/json",
            content: "",
            truncated: false,
            checksum_sha256: "b".repeat(64),
          },
          {
            id: "artifact-manifest",
            name: "artifact-manifest.json",
            type: "JSON",
            description: "Integrity manifest with artifact sizes and SHA-256 checksums.",
            size_bytes: 1024,
            size_label: "1.0 KB",
            created_at: run.completed_at,
            artifact_id: 53,
            download_kind: "server",
            download_url: `/servers/api/agents/runs/${run.id}/artifacts/53/download/`,
            content_type: "application/json",
            content: "",
            truncated: false,
            checksum_sha256: "c".repeat(64),
          },
        ]
      : [],
    generated_at: FIXED_DATE,
  };
}

function applyDeliveryStatus(report: ReturnType<typeof buildRunReport>, status?: "sent" | "failed" | "skipped" | "pending") {
  if (!status || !report.delivery_state) return report;
  const variants = {
    sent: {
      status: "sent",
      severity: "success",
      label: "Доставлено",
      title: "Отчёт доставлен",
      description: "Отчёт отправлен в Telegram.",
      next_action: "",
      updated_at: FIXED_DATE,
    },
    failed: {
      status: "failed",
      severity: "critical",
      label: "Ошибка",
      title: "Доставка отчёта не удалась",
      description: "Доставка в Telegram завершилась ошибкой HTTP 503.",
      next_action: "Проверьте настройки канала и повторите отправку отчёта после исправления причины.",
      updated_at: FIXED_DATE,
    },
    skipped: {
      status: "skipped",
      severity: "warning",
      label: "Пропущено",
      title: "Доставка отчёта пропущена",
      description: "Доставка в Telegram пропущена: не настроены bot token или chat id.",
      next_action: "Настройте Telegram bot token и chat id или выключите доставку для агента.",
      updated_at: FIXED_DATE,
    },
    pending: {
      status: "pending",
      severity: "warning",
      label: "Ожидает",
      title: "Доставка ещё не подтверждена",
      description: "Финальный отчёт готов, но событие успешной доставки ещё не записано.",
      next_action: "Проверьте worker и настройки доставки отчёта.",
      updated_at: null,
    },
  } as const;
  report.delivery_state = {
    ...report.delivery_state,
    ...variants[status],
    event: status === "sent"
      ? {
          id: 9,
          run_id: report.run.id,
          event_type: "agent_report_delivery_sent",
          task_id: null,
          message: "Report delivered",
          payload: { channel: "telegram", chat_id: "***6789" },
          created_at: FIXED_DATE,
          severity: "success",
          source: "report",
          title: "Отчёт доставлен",
          summary: "Отчёт отправлен в Telegram.",
          phase: "delivery",
          category: "report",
          important: true,
        }
      : null,
  } as typeof report.delivery_state;
  return report;
}

function makeAgentsHandler(
  initialAgents: AgentItem[] = [],
  options: {
    workerStates?: Record<string, unknown>;
    runtimeOverview?: Record<string, unknown>;
    completedRunIds?: number[];
    deliveryStatusByRunId?: Record<number, "sent" | "failed" | "skipped" | "pending">;
    waitingRunQuestions?: Record<number, string>;
    reportMutators?: Record<number, (report: ReturnType<typeof buildRunReport>) => void>;
  } = {},
) {
  const agents = initialAgents.map(normalizeAgent);
  const completedRunIds = new Set(options.completedRunIds || []);
  const deliveryStatusByRunId: Record<number, "sent" | "failed" | "skipped" | "pending"> = { ...(options.deliveryStatusByRunId || {}) };
  const workerStates = options.workerStates || {
    scheduled_agents: workerState(),
  };
  const runtime = options.runtimeOverview || runtimeOverview({
    summary: {
      configured_agents: agents.length,
      active_runs: agents.filter((agent) => agent.active_run_id).length,
      pending_runs: 0,
      running_runs: agents.filter((agent) => agent.active_run_id).length,
      waiting_runs: 0,
      queued_dispatches: 0,
      claimed_dispatches: 0,
      scheduled_agents: agents.filter((agent) => agent.schedule_minutes > 0).length,
      scheduled_due_now: agents.filter((agent) => agent.schedule_minutes > 0).length,
      issues: 0,
    },
    workers: workerStates,
  });
  let nextAgentId = 300;
  let nextRunId = 700;
  const runDetails = new Map<number, ReturnType<typeof buildRunDetail>>();
  const runLogs = new Map<number, ReturnType<typeof buildRunLog>>();

  for (const agent of agents) {
    if (agent.active_run_id) {
      const detail = buildRunDetail(agent.active_run_id, agent.id, agent.name);
      const pendingQuestion = options.waitingRunQuestions?.[agent.active_run_id];
      if (pendingQuestion) {
        detail.run.status = "waiting";
        detail.run.pending_question = pendingQuestion;
      }
      runDetails.set(agent.active_run_id, detail);
      runLogs.set(agent.active_run_id, buildRunLog(detail.run.status));
    }
    if (agent.last_run_id && completedRunIds.has(agent.last_run_id)) {
      const detail = buildRunDetail(agent.last_run_id, agent.id, agent.name);
      detail.run.status = "completed";
      detail.run.completed_at = FIXED_DATE;
      detail.run.final_report = "# Final\n\n## Что произошло\n- Агент завершил проверку.\n";
      runDetails.set(agent.last_run_id, detail);
      runLogs.set(agent.last_run_id, buildRunLog("completed"));
    }
  }

  return async (req: any) => {
    if (req.path === "/api/auth/session/" && req.method === "GET") {
      return json({
        authenticated: true,
        user: {
          id: 1,
          username: "admin",
          email: "admin@example.com",
          is_staff: true,
          features: fullFeatures,
        },
      });
    }

    if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") {
      return json({
        success: true,
        servers: [
          {
            id: 1,
            name: "Web-01",
            host: "10.0.0.11",
            port: 22,
            username: "root",
            server_type: "ssh",
            status: "online",
            group_id: 11,
            group_name: "Core",
            is_shared: false,
            can_edit: true,
            share_context_enabled: true,
            shared_by_username: "",
            terminal_path: "/servers/1/terminal",
            minimal_terminal_path: "/servers/1/terminal/minimal",
            last_connected: null,
          },
        ],
        groups: [{ id: 11, name: "Core", server_count: 1 }],
        stats: { owned: 1, shared: 0, total: 1 },
        recent_activity: [],
      });
    }

    if (req.path === "/servers/api/agents/templates/" && req.method === "GET") {
      return json({ success: true, templates: [] });
    }

    if (req.path === "/servers/api/agents/dashboard/" && req.method === "GET") {
      return json({ success: true, active: [], recent: [] });
    }

    if (req.path === "/api/studio/skills/" && req.method === "GET") {
      return json([]);
    }

    if (req.path === "/servers/api/agents/" && req.method === "GET") {
      return json({ success: true, agents, worker_states: workerStates, runtime_overview: runtime });
    }

    if (req.path === "/servers/api/agents/runtime/cleanup-stale/" && req.method === "POST") {
      const runtimeRecord = runtime as Record<string, any>;
      const items = runtimeRecord.items || {};
      const staleRuns = Array.isArray(items.stale_candidates) ? items.stale_candidates : [];
      const staleRunIds = new Set(staleRuns.map((item: any) => Number(item.run_id)));
      const cleaned = staleRunIds.size;
      for (const agent of agents) {
        if (agent.active_run_id && staleRunIds.has(agent.active_run_id)) {
          agent.active_run_id = null;
          agent.last_run_id = agent.last_run_id || Array.from(staleRunIds)[0] || null;
        }
      }
      for (const runId of staleRunIds) {
        const runDetail = runDetails.get(runId);
        if (runDetail) {
          runDetail.run.status = "failed";
          runDetail.run.completed_at = FIXED_DATE;
        }
        const runLog = runLogs.get(runId);
        if (runLog) {
          runLog.status = "failed";
        }
      }
      runtimeRecord.summary = {
        ...(runtimeRecord.summary || {}),
        active_runs: Math.max(0, Number(runtimeRecord.summary?.active_runs || 0) - cleaned),
        pending_runs: 0,
        queued_dispatches: 0,
      };
      runtimeRecord.items = {
        ...items,
        active_runs: (items.active_runs || []).filter((item: any) => !staleRunIds.has(Number(item.run_id))),
        queued_dispatches: (items.queued_dispatches || []).filter((item: any) => !staleRunIds.has(Number(item.run_id))),
        scheduled_due: (items.scheduled_due || []).map((item: any) =>
          staleRunIds.has(Number(item.active_run_id))
            ? { ...item, active_run_id: null, active_run_status: "" }
            : item,
        ),
        stale_candidates: [],
      };
      return json({
        success: true,
        cleanup: {
          stale_seconds: 60,
          scanned: cleaned,
          cleaned,
          canceled_dispatches: cleaned,
          runs: staleRuns.map((item: any) => ({
            run_id: item.run_id,
            agent_id: item.agent_id,
            agent_name: item.agent_name,
            status: "failed",
            age_seconds: item.age_seconds,
            canceled_dispatches: 1,
          })),
          generated_at: FIXED_DATE,
        },
        runtime_overview: runtime,
      });
    }

    if (req.path === "/servers/api/agents/create/" && req.method === "POST") {
      const created: AgentItem = {
        id: nextAgentId++,
        name: String(req.body?.name || "Custom Agent"),
        mode: (req.body?.mode || "mini") as AgentMode,
        agent_type: String(req.body?.agent_type || "custom"),
        agent_type_display: "Custom",
        server_count: Array.isArray(req.body?.server_ids) ? req.body.server_ids.length : 0,
        last_run_at: null,
        schedule_minutes: Number(req.body?.schedule_minutes || 0),
        schedule_config: { mode: "manual" },
        max_iterations: Number(req.body?.max_iterations || 20),
        goal: String(req.body?.goal || ""),
        is_enabled: true,
        sudo_policy: "ask",
        active_run_id: null,
        last_run_id: null,
      };
      agents.push(created);
      return json({ success: true, id: created.id });
    }

    if (req.path.match(/^\/servers\/api\/agents\/\d+\/run\/$/) && req.method === "POST") {
      const agentId = Number(req.path.split("/")[4]);
      const target = agents.find((agent) => agent.id === agentId);
      if (!target) {
        return json({ success: false, runs: [] }, 404);
      }

      const runId = nextRunId++;
      target.last_run_id = runId;
      target.last_run_at = FIXED_DATE;

      if (target.mode === "full" || target.mode === "multi") {
        target.active_run_id = runId;
        runDetails.set(runId, buildRunDetail(runId, target.id, target.name));
        runLogs.set(runId, buildRunLog());
        return json({ success: true, runs: [], run_id: runId });
      }

      const miniDetail = buildRunDetail(runId, target.id, target.name);
      miniDetail.run.status = "completed";
      miniDetail.run.completed_at = FIXED_DATE;
      miniDetail.run.duration_ms = 1_250;
      miniDetail.run.ai_analysis = "# Summary\nMini audit succeeded";
      miniDetail.run.final_report = "# Summary\nMini audit succeeded\n\n## Full evidence\n- Full-only evidence line";
      miniDetail.run.commands_output = [
        {
          cmd: "hostname",
          stdout: "web-01",
          stderr: "",
          exit_code: 0,
          duration_ms: 40,
        },
      ];
      runDetails.set(runId, miniDetail);
      runLogs.set(runId, buildRunLog("completed"));

      return json({
        success: true,
        run_id: runId,
        runs: [
          {
            run_id: runId,
            server_name: "Web-01",
            status: "completed",
            ai_analysis: miniDetail.run.ai_analysis,
            duration_ms: miniDetail.run.duration_ms,
            commands_output: miniDetail.run.commands_output,
            total_iterations: 1,
            final_report: miniDetail.run.final_report,
          },
        ],
      });
    }

    if (req.path.match(/^\/servers\/api\/agents\/\d+\/stop\/$/) && req.method === "POST") {
      const agentId = Number(req.path.split("/")[4]);
      const target = agents.find((agent) => agent.id === agentId);
      if (target?.active_run_id) {
        const runId = target.active_run_id;
        target.active_run_id = null;
        const runDetail = runDetails.get(runId);
        if (runDetail) {
          runDetail.run.status = "stopped";
          runDetail.run.completed_at = FIXED_DATE;
        }
        const runLog = runLogs.get(runId);
        if (runLog) {
          runLog.status = "stopped";
        }
      }
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/agents\/\d+\/delete\/$/) && req.method === "POST") {
      const agentId = Number(req.path.split("/")[4]);
      const index = agents.findIndex((agent) => agent.id === agentId);
      if (index >= 0) {
        agents.splice(index, 1);
      }
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      const detail = runDetails.get(runId);
      return detail ? json(detail) : json({ success: false }, 404);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/report\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      const detail = runDetails.get(runId);
      if (!detail) return json({ success: false }, 404);
      const report = buildRunReport(detail);
      applyDeliveryStatus(report, deliveryStatusByRunId[runId]);
      options.reportMutators?.[runId]?.(report);
      return json(report);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/report\/deliver\/$/) && req.method === "POST") {
      const runId = Number(req.path.split("/")[5]);
      const detail = runDetails.get(runId);
      if (!detail) return json({ success: false }, 404);
      if (detail.run.status !== "completed") return json({ success: false, error: "Report is not ready" }, 409);
      deliveryStatusByRunId[runId] = "sent";
      const report = buildRunReport(detail);
      applyDeliveryStatus(report, "sent");
      return json(report);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/reply\/$/) && req.method === "POST") {
      const runId = Number(req.path.split("/")[5]);
      const detail = runDetails.get(runId);
      if (!detail || detail.run.status !== "waiting") return json({ success: false, error: "Run not found or not waiting" }, 404);
      const answer = String((req.body as { answer?: unknown } | null)?.answer || "").trim();
      if (!answer) return json({ success: false, error: "Answer required" }, 400);
      detail.run.status = "running";
      detail.run.pending_question = "";
      (detail.run as typeof detail.run & { user_reply?: string }).user_reply = answer;
      const runLog = runLogs.get(runId);
      if (runLog) {
        runLog.status = "running";
        runLog.pending_question = "";
      }
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/artifacts\/download-all\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      return json("fake zip bundle", runDetails.has(runId) ? 200 : 404);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/artifacts\/\d+\/download\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      return json("# Final\n", runDetails.has(runId) ? 200 : 404);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/log\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      const log = runLogs.get(runId);
      return log ? json(log) : json({ success: false }, 404);
    }
  };
}

test("creates and runs a mini agent from the agents page", async ({ page }) => {
  const harness = await installApiHarness(page, makeAgentsHandler());

  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();
  await page.getByRole("button", { name: "Create your first agent" }).click();

  const createDialog = page.getByRole("dialog");
  await expect(createDialog.getByText("Agent type")).toBeVisible();
  await createDialog.getByRole("button", { name: /Custom/i }).click();

  await expect(createDialog.getByRole("heading", { name: "Basics" })).toBeVisible();
  await createDialog.getByPlaceholder("Log analysis").fill("Disk Audit");
  await createDialog.locator("textarea").nth(0).fill("hostname\nuptime");
  await createDialog.locator("textarea").nth(1).fill("Summarize the result");
  await createDialog.getByRole("button", { name: "Next" }).click();

  await expect(createDialog.getByRole("heading", { name: "Server selection" })).toBeVisible();
  await createDialog.getByRole("button", { name: /Web-01/i }).click();
  await createDialog.getByRole("button", { name: "Next" }).click();

  await expect(createDialog.getByRole("heading", { name: "Capabilities" })).toBeVisible();
  await createDialog.getByRole("button", { name: "Next" }).click();

  await expect(createDialog.getByText("Preflight passed")).toBeVisible();
  await createDialog.getByRole("button", { name: "Create Agent" }).click();

  await expect.poll(() => harness.getCalls("/servers/api/agents/create/", "POST").length).toBe(1);
  await expect(createDialog).toBeHidden();
  await expect(page.getByRole("main").getByText("Disk Audit")).toBeVisible();

  await page.getByRole("button", { name: /^Run$/ }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/300/run/", "POST").length).toBe(1);
  await expect(page.getByText("Mini audit succeeded")).toBeVisible();
});

test("shows mini run report as a quick preview with full report CTA", async ({ page }) => {
  await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 221,
        name: "Mini Preview",
        mode: "mini",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: null,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Render quick report preview",
        active_run_id: null,
        last_run_id: null,
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Mini Preview")).toBeVisible();
  await page.getByRole("button", { name: /^Run$/ }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Agent report for Web-01" })).toBeVisible();
  await expect(dialog.getByText("Completed")).toBeVisible();
  await expect(dialog.getByText("1s")).toBeVisible();
  await expect(dialog.getByText("1 commands")).toBeVisible();
  await expect(dialog.getByText("Mini audit succeeded")).toBeVisible();
  await expect(dialog.getByText("Full-only evidence line")).toHaveCount(0);

  await dialog.getByRole("link", { name: "Open full report" }).click();
  await expect(page).toHaveURL(/\/agents\/run\/700$/);
  await expect(page.locator("h1", { hasText: "Mini Preview" })).toBeVisible();
});

test("blocks full agent launch when execution worker is not ready", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 211,
        name: "Worker Blocked",
        mode: "full",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: null,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Run only when the execution worker is available",
        active_run_id: null,
        last_run_id: null,
        execution_readiness: {
          required: true,
          ready: false,
          status: "idle",
          severity: "warning",
          title: "Execution worker не активен",
          description: "Full/multi-агенты могут остаться в очереди.",
          next_action: "Запустите worker: python manage.py run_agent_execution_plane --worker-key default",
          worker: null,
        },
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Worker Blocked")).toBeVisible();
  await expect(page.getByText("Execution worker").first()).toBeVisible();
  await expect(page.getByText("Full/multi agent queue runtime")).toBeVisible();
  await expect(page.getByText("worker wait")).toBeVisible();
  await expect(page.getByText("python manage.py run_agent_execution_plane").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^Copy$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Run$/ })).toBeDisabled();
  expect(harness.getCalls("/servers/api/agents/211/run/", "POST")).toHaveLength(0);
});

test("shows agent runtime queue blockers", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 214,
          name: "Queued Pipeline",
          mode: "multi",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 10,
          schedule_config: { mode: "interval", interval_minutes: 10 },
          max_iterations: 20,
          goal: "Waits for worker diagnostics",
          active_run_id: 904,
          last_run_id: 904,
        },
      ],
      {
        runtimeOverview: runtimeOverview({
          status: "needs_attention",
          severity: "warning",
          summary: {
            configured_agents: 1,
            active_runs: 1,
            pending_runs: 1,
            running_runs: 0,
            waiting_runs: 0,
            queued_dispatches: 1,
            claimed_dispatches: 0,
            scheduled_agents: 1,
            scheduled_due_now: 1,
            issues: 2,
          },
          issues: [
            {
              id: "execution_worker_not_ready",
              severity: "warning",
              title: "Execution worker не активен",
              description: "Full/multi-запуски есть в очереди, но worker не подтверждён.",
              next_action: "python manage.py run_agent_execution_plane --worker-key default",
            },
            {
              id: "scheduled_agents_worker_not_ready",
              severity: "warning",
              title: "Schedule worker не активен",
              description: "Есть due-агенты, но автозапуск по расписанию не подтверждён.",
              next_action: "python manage.py run_scheduled_agents --daemon --worker-key default",
            },
          ],
          items: {
            active_runs: [
              {
                run_id: 904,
                agent_id: 214,
                agent_name: "Queued Pipeline",
                agent_mode: "multi",
                server_id: 1,
                server_name: "Web-01",
                status: "pending",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 420,
                duration_ms: 0,
                pending_question: "",
                is_stale_candidate: true,
                dispatch: null,
              },
            ],
            queued_dispatches: [
              {
                dispatch_id: 19,
                run_id: 904,
                agent_id: 214,
                agent_name: "Queued Pipeline",
                agent_mode: "multi",
                server_id: 1,
                server_name: "Web-01",
                dispatch_kind: "launch",
                status: "queued",
                server_ids: [1],
                queued_at: FIXED_DATE,
                claimed_at: null,
                heartbeat_at: null,
                lease_expires_at: null,
                queued_age_seconds: 420,
                lease_seconds_left: null,
                claimed_by: "",
                attempt_count: 0,
                error: "",
              },
            ],
            scheduled_due: [
              {
                agent_id: 214,
                agent_name: "Queued Pipeline",
                agent_mode: "multi",
                server_count: 1,
                server_names: ["Web-01"],
                schedule_minutes: 10,
                schedule_config: { mode: "interval", interval_minutes: 10 },
                last_run_at: FIXED_DATE,
                next_due_at: FIXED_DATE,
                due_age_seconds: 60,
                active_run_id: 904,
                active_run_status: "pending",
              },
            ],
            stale_candidates: [
              {
                run_id: 904,
                agent_id: 214,
                agent_name: "Queued Pipeline",
                agent_mode: "multi",
                server_id: 1,
                server_name: "Web-01",
                status: "pending",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 420,
                duration_ms: 0,
                pending_question: "",
                is_stale_candidate: true,
                dispatch: null,
              },
            ],
          },
        }),
      },
    ),
  );

  await page.goto("/agents");
  const runtimeSection = page.locator("section").filter({ hasText: "Agent runtime" }).first();
  await expect(runtimeSection).toBeVisible();
  await expect(runtimeSection.getByText("Runtime blockers detected")).toBeVisible();
  await expect(runtimeSection.getByText("Full/multi-запуски есть в очереди")).toBeVisible();
  await expect(runtimeSection.getByText("queued", { exact: true }).first()).toBeVisible();
  await expect(runtimeSection.getByText("due", { exact: true }).first()).toBeVisible();
  await expect(runtimeSection.getByText("Active runs", { exact: true })).toBeVisible();
  await expect(runtimeSection.getByText("Dispatch queue", { exact: true })).toBeVisible();
  await expect(runtimeSection.getByText("Due schedule", { exact: true })).toBeVisible();
  await expect(runtimeSection.getByText("Stale candidates", { exact: true })).toBeVisible();
  await expect(runtimeSection.getByText("Queued Pipeline").first()).toBeVisible();
  await expect(runtimeSection.getByText("run #904")).toBeVisible();
  await expect(runtimeSection.getByRole("button", { name: /Clean stale/i })).toBeVisible();
  await expect(runtimeSection.getByText("Recommended production worker")).toBeVisible();
  await expect(runtimeSection.getByText("python manage.py run_ops_supervisor")).toBeVisible();
  await expect(runtimeSection.getByText("python manage.py run_scheduled_agents")).toBeVisible();

  await runtimeSection.getByRole("button", { name: /Clean stale/i }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/runtime/cleanup-stale/", "POST").length).toBe(1);
  await expect(page.getByText("Cleaned stale runs: 1; canceled dispatches: 1.")).toBeVisible();
  await expect(runtimeSection.getByRole("button", { name: /Clean stale/i })).toBeHidden();
});

test("shows scheduled agents worker runtime state", async ({ page }) => {
  await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 213,
          name: "Nightly Health",
          mode: "mini",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 15,
          schedule_config: { mode: "interval", interval_minutes: 15 },
          max_iterations: 20,
          goal: "Run health checks on a schedule",
          active_run_id: null,
          last_run_id: 900,
        },
      ],
      {
        workerStates: {
          scheduled_agents: workerState({
            status: "running",
            is_stale: false,
            hostname: "sched-worker-01",
            pid: 7331,
            heartbeat_at: FIXED_DATE,
            lease_expires_at: "2026-03-01T08:03:00.000Z",
            last_cycle_finished_at: FIXED_DATE,
            last_summary: { scanned: 4, due: 1, launched_agents: 1, skipped: 3 },
          }),
        },
      },
    ),
  );

  await page.goto("/agents");
  await expect(page.getByText("Nightly Health")).toBeVisible();
  await expect(page.getByText("Schedule worker").first()).toBeVisible();
  await expect(page.getByText("Scheduled agent dispatcher runtime")).toBeVisible();
  await expect(page.getByText("sched-worker-01")).toBeVisible();
  await expect(page.getByText("launched_agents: 1")).toBeVisible();
});

test("stops active agent run from list with explicit run id", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 212,
        name: "Active Rollout",
        mode: "full",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: FIXED_DATE,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Stop the active run from the list",
        active_run_id: 902,
        last_run_id: 902,
        execution_readiness: {
          required: true,
          ready: true,
          status: "running",
          severity: "success",
          title: "Execution worker готов",
          description: "Worker accepts full/multi runs.",
          next_action: "",
          worker: {
            worker_kind: "agent_execution",
            worker_key: "default",
            status: "running",
            is_stale: false,
            hostname: "worker-01",
            pid: 4242,
            command: "python manage.py run_agent_execution_plane",
            heartbeat_at: FIXED_DATE,
            lease_expires_at: "2026-03-01T08:03:00.000Z",
            last_started_at: FIXED_DATE,
            last_stopped_at: null,
            last_cycle_started_at: FIXED_DATE,
            last_cycle_finished_at: FIXED_DATE,
            last_summary: { processed: 3, completed: 3, failed: 0 },
            last_error: "",
          },
        },
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Active Rollout")).toBeVisible();
  await expect(page.getByText("worker-01")).toBeVisible();
  await expect(page.getByText("processed: 3")).toBeVisible();
  await page.getByRole("button", { name: /^Stop$/ }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/212/stop/", "POST").length).toBe(1);
  expect(harness.getCalls("/servers/api/agents/212/stop/", "POST")[0].body).toEqual({ run_id: 902 });
});

test("opens a live agent run and sends stop from the run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 202,
        name: "Patch Rollout",
        mode: "full",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: FIXED_DATE,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Roll out production patch safely",
        active_run_id: 901,
        last_run_id: 901,
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Patch Rollout")).toBeVisible();
  await page.getByRole("link", { name: "Watch" }).click();

  await expect(page).toHaveURL(/\/agents\/run\/901$/);
  await expect(page.locator("h1", { hasText: "Patch Rollout" })).toBeVisible();
  await expect(page.getByText("Отчёт формируется")).toBeVisible();
  await expect(page.getByText("Execution worker не принимает запуск").first()).toBeVisible();
  await expect(page.getByText("Доставка отчёта")).toBeVisible();
  await expect(page.getByText("Ждёт отчёт").first()).toBeVisible();

  const scrollRoot = page.locator("[data-agent-run-scroll]");
  await expect.poll(() => scrollRoot.evaluate((node) => node.scrollHeight > node.clientHeight)).toBe(true);
  await scrollRoot.evaluate((node) => {
    node.scrollTop = 0;
  });
  await scrollRoot.hover();
  await page.mouse.wheel(0, 700);
  await expect.poll(() => scrollRoot.evaluate((node) => node.scrollTop)).toBeGreaterThan(0);

  await page.getByRole("button", { name: "События" }).first().click();
  await expect(page.getByText("Хронология событий")).toBeVisible();
  await expect(page.getByText("Последний важный сигнал")).toBeVisible();
  await expect(page.getByText("Package lock check failed").first()).toBeVisible();
  await expect(page.getByText("Старт", { exact: true })).toBeVisible();
  await expect(page.getByText("Выполнение", { exact: true })).toBeVisible();
  await expect(page.getByText("Выполнение: 2 · 1 проблем")).toBeVisible();
  await expect(page.getByText("Запуск создан")).toBeVisible();
  await page.getByPlaceholder("Поиск по событиям, задачам, фазам и payload").fill("apt-get");
  await expect(page.getByText("Package lock check failed").first()).toBeVisible();
  await expect(page.getByText("Запуск создан")).toBeHidden();
  await page.getByRole("button", { name: "Debug" }).click();
  await expect(page.getByText("\"exit_code\": 100")).toBeVisible();

  await page.getByRole("tab", { name: "Ход агента" }).click();
  const agentTab = page.getByRole("tabpanel", { name: "Ход агента" });
  await expect(page.getByText("1 из 3 шагов завершено")).toBeVisible();
  await expect(page.getByText("Inspect service health").first()).toBeVisible();
  await expect(page.getByText("Apply patch window checks").first()).toBeVisible();
  await page.getByPlaceholder("Поиск по шагам, командам и результатам").fill("package locks");
  await expect(agentTab.locator("article").filter({ hasText: "Apply patch window checks" })).toBeVisible();
  await expect(agentTab.locator("article").filter({ hasText: "Inspect service health" })).toHaveCount(0);
  await page.getByPlaceholder("Поиск по шагам, командам и результатам").fill("");
  await page.getByRole("button", { name: "Активные" }).click();
  await expect(agentTab.locator("article").filter({ hasText: "Write completion report" })).toBeVisible();
  await expect(agentTab.locator("article").filter({ hasText: "Inspect service health" })).toHaveCount(0);

  await page.getByRole("button", { name: "Артефакты" }).first().click();
  await expect(page.getByText("Артефакты появятся после финального отчёта").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Скачать/ })).toHaveCount(0);

  await page.getByRole("button", { name: /Stop/i }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/202/stop/", "POST").length).toBe(1);
});

test("keeps artifacts hidden while live report is not ready", async ({ page }) => {
  await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 219,
          name: "Premature Artifact Run",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Do not expose artifacts until report finalization",
          active_run_id: 909,
          last_run_id: 909,
        },
      ],
      {
        reportMutators: {
          909: (report) => {
            report.report_state.report_ready = false;
            report.report_state.artifacts_ready = false;
            report.artifact_state.ready = false;
            report.artifact_state.artifact_count = 1;
            report.artifacts = [
              {
                id: "premature-final-report",
                name: "final-report.md",
                type: "Markdown",
                description: "Should stay hidden before final report readiness.",
                size_bytes: 42,
                size_label: "42 B",
                created_at: FIXED_DATE,
                artifact_id: 91,
                download_kind: "server",
                download_url: "/servers/api/agents/runs/909/artifacts/91/download/",
                content_type: "text/markdown",
                content: "# Draft",
                truncated: false,
                checksum_sha256: "d".repeat(64),
              },
            ];
          },
        },
      },
    ),
  );

  await page.goto("/agents/run/909");
  await expect(page.getByRole("heading", { name: "Premature Artifact Run" })).toBeVisible();
  await page.getByRole("button", { name: "Артефакты" }).first().click();
  await expect(page.getByText("Артефакты появятся после финального отчёта").first()).toBeVisible();
  await expect(page.getByText("final-report.md")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Скачать/ })).toHaveCount(0);
});

test("answers a pending agent question from the run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 218,
          name: "Interactive Rollout",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Ask before restarting nginx",
          active_run_id: 907,
          last_run_id: 907,
        },
      ],
      {
        waitingRunQuestions: {
          907: "Можно перезапустить nginx сейчас?",
        },
        runtimeOverview: runtimeOverview({
          summary: {
            configured_agents: 1,
            active_runs: 1,
            pending_runs: 0,
            running_runs: 0,
            waiting_runs: 1,
            queued_dispatches: 0,
            claimed_dispatches: 0,
            scheduled_agents: 0,
            scheduled_due_now: 0,
            issues: 0,
          },
          items: {
            active_runs: [
              {
                run_id: 907,
                agent_id: 218,
                agent_name: "Interactive Rollout",
                agent_mode: "full",
                server_id: 1,
                server_name: "Web-01",
                status: "waiting",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 45,
                duration_ms: 45_000,
                pending_question: "Можно перезапустить nginx сейчас?",
                is_stale_candidate: false,
                dispatch: null,
              },
            ],
            queued_dispatches: [],
            scheduled_due: [],
            stale_candidates: [],
          },
        }),
      },
    ),
  );

  await page.goto("/agents");
  await expect(page.getByText("Interactive Rollout").first()).toBeVisible();
  await expect(page.getByText("Needs answer").first()).toBeVisible();
  await expect(page.getByText("Agent question: Можно перезапустить nginx сейчас?")).toBeVisible();
  await page.getByRole("link", { name: /Answer/i }).click();
  await expect(page).toHaveURL(/\/agents\/run\/907$/);

  await expect(page.locator("h1", { hasText: "Interactive Rollout" })).toBeVisible();
  await expect(page.getByText("Агент ждёт ответа").first()).toBeVisible();
  await expect(page.getByText("Можно перезапустить nginx сейчас?").first()).toBeVisible();

  await page.getByLabel("Ответ агенту").fill("Да, перезапускай nginx в текущем окне.");
  await page.getByRole("button", { name: "Отправить ответ" }).click();

  const replyPath = "/servers/api/agents/runs/907/reply/";
  await expect.poll(() => harness.getCalls(replyPath, "POST").length).toBe(1);
  expect(harness.getCalls(replyPath, "POST")[0].body).toEqual({
    answer: "Да, перезапускай nginx в текущем окне.",
  });
  await expect(page.getByText("Ответ отправлен агенту.")).toBeVisible();
  await expect(page.getByText("Вопрос агента")).toHaveCount(0);

  await page.getByRole("button", { name: "События" }).first().click();
  await expect(page.getByText("Ответ отправлен агенту").first()).toBeVisible();
});

test("cleans stale run from the live run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 216,
          name: "Stale Rollout",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Recover stale worker queue",
          active_run_id: 906,
          last_run_id: 906,
        },
      ],
      {
        runtimeOverview: runtimeOverview({
          status: "needs_attention",
          severity: "warning",
          summary: {
            configured_agents: 1,
            active_runs: 1,
            pending_runs: 1,
            running_runs: 0,
            waiting_runs: 0,
            queued_dispatches: 1,
            claimed_dispatches: 0,
            scheduled_agents: 0,
            scheduled_due_now: 0,
            issues: 1,
          },
          items: {
            active_runs: [
              {
                run_id: 906,
                agent_id: 216,
                agent_name: "Stale Rollout",
                agent_mode: "full",
                server_id: 1,
                server_name: "Web-01",
                status: "pending",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 300,
                duration_ms: 0,
                pending_question: "",
                is_stale_candidate: true,
                dispatch: null,
              },
            ],
            queued_dispatches: [
              {
                dispatch_id: 32,
                run_id: 906,
                agent_id: 216,
                agent_name: "Stale Rollout",
                agent_mode: "full",
                server_id: 1,
                server_name: "Web-01",
                dispatch_kind: "launch",
                status: "queued",
                server_ids: [1],
                queued_at: FIXED_DATE,
                claimed_at: null,
                heartbeat_at: null,
                lease_expires_at: null,
                queued_age_seconds: 300,
                lease_seconds_left: null,
                claimed_by: "",
                attempt_count: 0,
                error: "",
              },
            ],
            scheduled_due: [],
            stale_candidates: [
              {
                run_id: 906,
                agent_id: 216,
                agent_name: "Stale Rollout",
                agent_mode: "full",
                server_id: 1,
                server_name: "Web-01",
                status: "pending",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 300,
                duration_ms: 0,
                pending_question: "",
                is_stale_candidate: true,
                dispatch: null,
              },
            ],
          },
        }),
      },
    ),
  );

  await page.goto("/agents/run/906");
  await expect(page.locator("h1", { hasText: "Stale Rollout" })).toBeVisible();
  await expect(page.getByText("Запуск завис в очереди").first()).toBeVisible();
  await expect(page.getByText("Runtime").first()).toBeVisible();
  await expect(page.getByText("Stale after").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Скопировать действие/ })).toBeVisible();

  await page.getByRole("button", { name: /Очистить stale/ }).first().click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/runtime/cleanup-stale/", "POST").length).toBe(1);
  await expect(page.getByText("Очищено stale-запусков: 1; отменено dispatch: 1.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Очистить stale/ })).toHaveCount(0);
});

test("downloads completed run artifacts as a server bundle", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 217,
          name: "Completed Report",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Inspect artifact bundle",
          active_run_id: null,
          last_run_id: 908,
        },
      ],
      { completedRunIds: [908] },
    ),
  );

  await page.goto("/agents/run/908");
  await expect(page.locator("h1", { hasText: "Completed Report" })).toBeVisible();
  await expect(page.getByText("Доставка отчёта")).toBeVisible();
  await expect(page.getByText("Доставлено").first()).toBeVisible();
  await page.getByRole("tab", { name: "Артефакты" }).click();
  await expect(page.getByText("Артефакты отчёта готовы")).toBeVisible();
  await expect(page.getByText("3 файлов · 3.0 KB")).toBeVisible();
  await expect(page.getByText("manifest проверен")).toBeVisible();
  await expect(page.getByText("artifact-manifest.json")).toBeVisible();
  await expect(page.getByText("sha256:aaaaaaaaaaaa")).toBeVisible();
  await page.getByRole("button", { name: "Скачать всё" }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/runs/908/artifacts/download-all/", "GET").length).toBe(1);
  expect(harness.getCalls("/servers/api/agents/runs/908/artifacts/51/download/", "GET")).toHaveLength(0);
});

test("retries failed report delivery from the run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 218,
          name: "Failed Delivery Report",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Retry report delivery",
          active_run_id: null,
          last_run_id: 910,
        },
      ],
      { completedRunIds: [910], deliveryStatusByRunId: { 910: "failed" } },
    ),
  );

  await page.goto("/agents/run/910");
  await expect(page.locator("h1", { hasText: "Failed Delivery Report" })).toBeVisible();
  await expect(page.getByText("Доставка в Telegram завершилась ошибкой HTTP 503.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Повторить" })).toBeVisible();
  await page.getByRole("button", { name: "Повторить" }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/runs/910/report/deliver/", "POST").length).toBe(1);
  await expect(page.getByText("Доставка отчёта запущена повторно.")).toBeVisible();
  await expect(page.getByText("Доставлено").first()).toBeVisible();
});
