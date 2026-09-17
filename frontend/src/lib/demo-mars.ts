const MARS_SKILLS = ["frontend-design", "frontend-dev", "react-best-practices", "frontend-testing-debugging"];

const DEMO_MARS_ROLES = {
  orchestrator: "mars",
  architect: "gemini",
  executor: "codex",
  repair: "codex",
  reviewer: "gemini",
  verifier: "system",
};

const DEMO_MARS_ORCHESTRATION = {
  strategy: "gemini_architect_codex_executor_codex_repair_gemini_reviewer",
  roles: [
    {
      role: "architect",
      agent: "gemini",
      workspace_mode: "read_only",
      skills: ["frontend-design"],
      responsibility: "Turn the approved user request into an implementation contract for Codex.",
    },
    {
      role: "executor",
      agent: "codex",
      workspace_mode: "read_write",
      skills: ["frontend-dev", "react-best-practices"],
      responsibility: "Create or edit project files according to the contract.",
    },
    {
      role: "verifier",
      agent: "system",
      workspace_mode: "read_write",
      skills: ["frontend-testing-debugging"],
      responsibility: "Run the configured verification command.",
    },
    {
      role: "repair",
      agent: "codex",
      workspace_mode: "read_write",
      skills: MARS_SKILLS,
      responsibility: "Fix verification failures or explicit review blockers.",
    },
    {
      role: "reviewer",
      agent: "gemini",
      workspace_mode: "read_only",
      skills: ["frontend-design", "react-best-practices", "frontend-testing-debugging"],
      responsibility: "Review the final diff and verification output without changing files.",
    },
  ],
  skill_routing: {
    architect: ["frontend-design"],
    executor: ["frontend-dev", "react-best-practices"],
    verifier: ["frontend-testing-debugging"],
    repair: MARS_SKILLS,
    reviewer: ["frontend-design", "react-best-practices", "frontend-testing-debugging"],
  },
  max_repair_rounds: 1,
  review_repair_rounds: 1,
};

function demoMarsWorkspace(denyGlobs = [".git/**", ".venv/**", "node_modules/**", "dist/**", "build/**", ".env", ".env.*"]) {
  return {
    id: 1,
    name: "Personal workspace",
    root_path: "agent_projects\\mars_workspaces\\user_demo",
    read_allow_roots: ["agent_projects\\mars_workspaces\\user_demo"],
    write_allow_roots: ["agent_projects\\mars_workspaces\\user_demo"],
    deny_globs: denyGlobs,
    enabled: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function demoMarsRun(status: string, overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    session_id: 1,
    workspace_id: 1,
    workspace: demoMarsWorkspace(),
    cli_roles: DEMO_MARS_ROLES,
    status,
    runtime_control: { stop_requested: status === "stopped", orchestration: DEMO_MARS_ORCHESTRATION },
    allow_dirty: false,
    final_report: status === "queued" ? "" : "# MARS final report\n\nDemo run completed.",
    codex_summary: status === "queued" ? "" : "Demo Codex final answer.",
    gemini_review: status === "queued" ? "" : "Demo Gemini review.",
    test_output: status === "queued" ? "" : "No verification command configured.",
    git_before: "",
    git_after: status === "queued" ? "" : " M frontend/src/App.tsx",
    started_at: status === "queued" ? null : new Date().toISOString(),
    completed_at: status === "queued" ? null : new Date().toISOString(),
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function taskBriefFromOptions(options: RequestInit): string {
  try {
    const body = typeof options.body === "string" && options.body ? (JSON.parse(options.body) as { task_brief?: string }) : null;
    return String(body?.task_brief || "Demo MARS task").trim() || "Demo MARS task";
  } catch {
    return "Demo MARS task";
  }
}

function demoInterviewQuestions(taskBrief: string) {
  const taskLower = taskBrief.toLowerCase();
  const isGameTask = ["game", "игр", "змей", "snake", "3d", "three"].some((token) => taskLower.includes(token));
  const isBackendTask = ["api", "backend", "django", "endpoint", "бэк", "сервер"].some((token) => taskLower.includes(token));
  return [
    {
      id: "success_criteria",
      question: `Какой результат для «${taskBrief.slice(0, 80)}» считаем готовым?`,
      kind: "choice_text",
      options: isGameTask
        ? ["Играбельный прототип", "Полноценный MVP", "Красивый playable demo", "Только core gameplay"]
        : isBackendTask
          ? ["API работает", "Контракт покрыт тестами", "Безопасная интеграция", "Документированное поведение"]
          : ["Рабочий MVP", "Минимальный прототип", "Полированный UI", "Исправленная проблема"],
      placeholder: "Опишите конкретный видимый результат, если вариантов мало.",
      required: true,
    },
    {
      id: "first_scope",
      question: `Что точно входит в первую версию «${taskBrief.slice(0, 80)}»?`,
      kind: "multi_choice_text",
      options: isGameTask
        ? ["Игровой цикл", "Счет и рекорд", "Пауза/рестарт", "Звуки/эффекты", "Меню", "Адаптив"]
        : isBackendTask
          ? ["Endpoint", "Валидация", "Права доступа", "DB-модель", "Тесты", "Audit/logs"]
          : ["Основной flow", "UI states", "Тесты", "Документация", "Адаптив", "Интеграции"],
      required: true,
    },
    {
      id: "primary_surface",
      question: "Где это должно работать в первую очередь?",
      kind: "choice_text",
      options: isBackendTask ? ["Django API", "Frontend + API", "Локальный dev", "Production-like path"] : ["Web browser", "Mobile browser", "Responsive web", "Только локальный dev"],
      required: true,
    },
    ...(isGameTask
      ? [
          { id: "game_core_loop", question: "Какой core loop нужен для этой игры?", kind: "multi_choice_text", options: ["Движение и сбор предметов", "Рост сложности", "Проигрыш и рестарт", "Очки", "Уровни", "Бонусы"], required: true },
          { id: "game_controls", question: "Как игрок должен управлять игрой?", kind: "choice_text", options: ["Клавиатура", "Клавиатура + мышь", "Touch controls", "Автовыбор под устройство"], required: true },
          { id: "game_camera", question: "Какая камера лучше подходит этой игре?", kind: "choice_text", options: ["Вид сверху под углом", "Изометрия", "Следит за персонажем", "Свободная камера"], required: true },
          { id: "game_visual_style", question: "Какой визуальный стиль выбрать для первой сборки?", kind: "choice_text", options: ["3D low-poly", "Neon arcade", "Clean minimal", "Dark premium", "Pixel/retro"], required: true },
        ]
      : isBackendTask
        ? [
            { id: "api_contract", question: "Какой контракт нужен для этого endpoint?", kind: "multi_choice_text", options: ["GET endpoint", "POST/PATCH action", "Validation errors", "Permissions", "Audit event", "Pagination/filtering"], required: true },
            { id: "data_model", question: "Какие данные нужно хранить или читать?", kind: "multi_choice_text", options: ["Новая модель", "Существующая модель", "JSON config", "Файлы workspace", "Только read-only"], required: true },
            { id: "backend_safety", question: "Какие backend-ограничения важны?", kind: "multi_choice_text", options: ["Ownership check", "Feature gate", "No secrets in response", "Idempotent action", "Transaction safety"], required: true },
          ]
        : [
            { id: "main_flow", question: "Какой основной пользовательский flow нужен?", kind: "multi_choice_text", options: ["Создать", "Просмотреть", "Редактировать", "Запустить", "Проверить результат", "Экспортировать"], required: true },
            { id: "ui_states", question: "Какие состояния интерфейса нужно продумать?", kind: "multi_choice_text", options: ["Loading", "Empty", "Error", "Success", "Disabled", "Mobile"], required: true },
          ]),
    { id: "constraints", question: "Что MARS не должен менять?", kind: "multi_choice_text", options: ["Не трогать auth/settings", "Без новых зависимостей", "Без backend", "Не менять API", "Можно добавить библиотеки"], required: false },
    { id: "verification", question: "Как MARS должен проверить результат?", kind: "multi_choice_text", options: isBackendTask ? ["pytest", "API smoke", "Permission test", "Django check", "No migration drift"] : ["npm run build", "npm run test", "Playwright smoke", "Скриншот в браузере", "Ручная проверка"], required: true },
    { id: "priority", question: "Что важнее, если придется выбирать?", kind: "choice_text", options: ["Качество UI", "Скорость реализации", "Надежная архитектура", "Минимум изменений", "Максимум функционала"], required: true },
  ];
}

export function demoMarsFallback<T>(path: string, options: RequestInit = {}): T | undefined {
  if (path.includes("/api/mars/projects")) {
    const now = new Date();
    return {
      projects: [
        {
          session: { id: 8, workspace_id: 1, workspace: demoMarsWorkspace(), task_brief: "Собрать dashboard для генерации отчетов и автопроверкой npm run build", answers: { success_criteria: "Готовый dashboard с сохранением результата." }, interview_questions: [], selected_skill_slugs: MARS_SKILLS, generated_plan: "# MARS execution plan\n\nBuild dashboard, run tests, review.", status: "completed", created_at: new Date(now.getTime() - 86400000).toISOString(), updated_at: new Date(now.getTime() - 1800000).toISOString() },
          latest_run: demoMarsRun("completed", { id: 17, session_id: 8, final_report: "# MARS orchestration final report\n\nDemo completed.", codex_summary: "Dashboard generated.", gemini_review: "STATUS: pass\nLooks good.", test_output: "npm run build passed.", git_after: " M frontend/src/pages/DemoDashboard.tsx", started_at: new Date(now.getTime() - 2400000).toISOString(), completed_at: new Date(now.getTime() - 1800000).toISOString(), created_at: new Date(now.getTime() - 2400000).toISOString() }),
          run_count: 2,
          recommended_skills: MARS_SKILLS,
        },
        {
          session: { id: 7, workspace_id: 1, workspace: demoMarsWorkspace(), task_brief: "Python script for CSV cleanup and daily report export", answers: { success_criteria: "One command creates a clean report." }, interview_questions: [], selected_skill_slugs: ["frontend-dev", "frontend-testing-debugging"], generated_plan: "# MARS execution plan\n\nCreate script and verify.", status: "running", created_at: new Date(now.getTime() - 172800000).toISOString(), updated_at: new Date(now.getTime() - 5400000).toISOString() },
          latest_run: demoMarsRun("running", { id: 16, session_id: 7, codex_summary: "Writing parser and report export.", gemini_review: "", test_output: "", git_after: "", started_at: new Date(now.getTime() - 5400000).toISOString(), completed_at: null, created_at: new Date(now.getTime() - 5400000).toISOString() }),
          run_count: 1,
          recommended_skills: ["frontend-dev", "frontend-testing-debugging"],
        },
      ],
    } as T;
  }
  if (path.includes("/api/mars/workspaces")) {
    return (path.match(/\/api\/mars\/workspaces\/\d+\//) ? { workspace: demoMarsWorkspace() } : { workspaces: [demoMarsWorkspace()] }) as T;
  }
  if (path.includes("/api/mars/sessions")) {
    const taskBrief = taskBriefFromOptions(options);
    const session = { id: 1, workspace_id: 1, workspace: demoMarsWorkspace(), task_brief: taskBrief, answers: {}, interview_questions: demoInterviewQuestions(taskBrief), selected_skill_slugs: MARS_SKILLS, generated_plan: path.includes("/answer/") || path.includes("/approve-plan/") || path.includes("/run/") ? "# MARS execution plan\n\n## Goal\nРабочий результат в личном workspace.\n\n## Execution checklist\n1. Inspect workspace.\n2. Implement approved change.\n3. Run verification.\n4. Request Gemini review." : "", status: path.includes("/approve-plan/") || path.includes("/run/") ? "approved" : path.includes("/answer/") ? "plan_ready" : "interview", created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    return (path.includes("/run/") ? { run: demoMarsRun("queued", { workspace: session.workspace }) } : { session, recommended_skills: session.selected_skill_slugs }) as T;
  }
  if (path.includes("/api/mars/runs") && path.includes("/events")) {
    return {
      events: [
        { id: 1, run_id: 1, event_type: "mars_run_queued", message: "MARS run queued", payload: {}, created_at: new Date().toISOString() },
        { id: 2, run_id: 1, event_type: "codex_stdout", message: "Demo Codex stream", payload: { stream: "stdout", text: "Demo Codex stream" }, created_at: new Date().toISOString() },
      ],
    } as T;
  }
  if (path.includes("/api/mars/runs")) {
    return { run: demoMarsRun(path.includes("/stop/") ? "stopped" : "completed", { workspace: demoMarsWorkspace([]) }) } as T;
  }
  return undefined;
}
