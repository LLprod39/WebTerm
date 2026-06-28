import { FIXED_DATE } from "./platformFixtureTypes";

export function makeStudioMarsFixtureData() {
  const pipelines = [
    {
      id: 101,
      name: "Nightly Patch",
      description: "Patch workflow",
      icon: "⚡",
      tags: ["ops"],
      is_shared: false,
      is_template: false,
      node_count: 3,
      created_at: FIXED_DATE,
      updated_at: FIXED_DATE,
      last_run: null,
      graph_version: 2,
      trigger_summary: { active_total: 1, active_manual: 1, active_webhook: 0, active_schedule: 0, active_monitoring: 0, last_triggered_at: null },
      nodes: [
        { id: "manual_start", type: "trigger/manual", position: { x: 0, y: 0 }, data: { label: "Manual start", is_active: true } },
      ],
      edges: [],
      triggers: [],
    },
  ];

  const draftSessions = [
    {
      id: 501,
      status: "ready",
      intent: "create",
      title: "Daily health report",
      user_goal: "Create a daily health check with Telegram delivery.",
      source_pipeline_id: null,
      applied_pipeline_id: null,
      selected_node_id: "",
      created_at: FIXED_DATE,
      updated_at: FIXED_DATE,
      applied_at: null,
      latest_revision: {
        id: 9001,
        session_id: 501,
        user_message: "Create a daily health check with Telegram delivery.",
        created_at: FIXED_DATE,
        preview_nodes: [
          { id: "manual_start", type: "trigger/manual", position: { x: 0, y: 0 }, data: { label: "Manual start" } },
          { id: "server_check", type: "ops/server_snapshot", position: { x: 260, y: 0 }, data: { label: "Server check" } },
          { id: "report", type: "output/report", position: { x: 520, y: 0 }, data: { label: "Telegram report" } },
        ],
        preview_edges: [
          { id: "e1", source: "manual_start", target: "server_check", sourceHandle: "out" },
          { id: "e2", source: "server_check", target: "report", sourceHandle: "out" },
        ],
        response: {
          reply: "Draft ready.",
          target_node_id: null,
          node_patch: {},
          graph_patch: {
            anchor_node_id: null,
            nodes: [
              { ref: "manual_start", type: "trigger/manual", label: "Manual start", data: {} },
              { ref: "server_check", type: "ops/server_snapshot", label: "Server check", data: {} },
              { ref: "report", type: "output/report", label: "Telegram report", data: {} },
            ],
            edges: [
              { source: "manual_start", target: "server_check" },
              { source: "server_check", target: "report" },
            ],
          },
          warnings: [],
          validation: { ok: true, errors: [], warnings: [] },
          risk: { level: "safe", items: [] },
          requirements: ["Run on demand", "Collect health metrics", "Send Telegram summary"],
          assumptions: ["Web-01 is the first pilot server"],
          questions: [],
          patch_summary: "Creates a manual health report pipeline.",
          resource_plan: {
            servers: [{ id: "1", name: "Web-01", reason: "Pilot server" }],
            mcp_servers: [],
            skills: [],
            missing: [],
            notes: [],
          },
          suggested_next_actions: ["Validate dry-run", "Create pipeline"],
          confidence: 0.84,
          selected_template: {
            slug: "pilot-health-report",
            name: "Pilot: Health Report",
            source: "visual_fixture",
          },
          template_recommendations: [
            {
              slug: "pilot-health-report",
              name: "Pilot: Health Report",
              description: "Health check and report",
              node_types: ["trigger/manual", "ops/server_snapshot", "output/report"],
            },
          ],
        },
      },
    },
  ];

  const marsWorkspace = {
    id: 31,
    name: "WebTerm workspace",
    root_path: "C:/WebTrerm",
    read_allow_roots: ["C:/WebTrerm"],
    write_allow_roots: ["C:/WebTrerm"],
    deny_globs: ["**/.env", "**/node_modules/**"],
    enabled: true,
    created_at: FIXED_DATE,
    updated_at: FIXED_DATE,
  };
  const marsSession = {
    id: 41,
    workspace_id: marsWorkspace.id,
    workspace: marsWorkspace,
    task_brief: "Create a compact deployment checklist",
    answers: {},
    interview_questions: [
      {
        id: "verification",
        question: "How should MARS verify the result?",
        kind: "multi_choice_text",
        options: ["npm run build", "Playwright smoke"],
        required: true,
      },
    ],
    selected_skill_slugs: [],
    generated_plan: "# Execution plan\n\n1. Build the checklist.\n2. Run verification.",
    status: "interview",
    created_at: FIXED_DATE,
    updated_at: FIXED_DATE,
  };
  const marsRun = {
    id: 51,
    session_id: marsSession.id,
    workspace_id: marsWorkspace.id,
    workspace: marsWorkspace,
    cli_roles: {},
    status: "completed",
    runtime_control: {},
    allow_dirty: false,
    final_report: "Checklist generated and verified.",
    codex_summary: "Updated project checklist.",
    gemini_review: "No blocking issues.",
    test_output: "npm run build passed",
    git_before: "abc123",
    git_after: "def456",
    started_at: FIXED_DATE,
    completed_at: FIXED_DATE,
    created_at: FIXED_DATE,
  };
  const marsProjects = [
    {
      session: marsSession,
      latest_run: marsRun,
      run_count: 1,
      recommended_skills: [],
    },
  ];

  return { pipelines, draftSessions, marsWorkspace, marsSession, marsRun, marsProjects };
}
