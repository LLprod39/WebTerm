import { FIXED_DATE } from "./agentsMockShared";

export function buildRunDetail(runId: number, agentId: number, agentName: string) {
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

export function buildRunLog(status = "running") {
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

export function buildRunReport(detail: ReturnType<typeof buildRunDetail>) {
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
          : "Запустите worker: python manage.py run_agent_execution_plane --worker-key <unique-worker-key>",
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
            : "Запустите worker: python manage.py run_agent_execution_plane --worker-key <unique-worker-key>",
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
