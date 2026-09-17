export function makeSettingsFixtureData() {
  const notifications = {
    telegram_bot_token: "",
    telegram_chat_id: "",
    notify_email: "ops@example.com",
    smtp_host: "",
    smtp_port: "587",
    smtp_user: "",
    smtp_password: "",
    from_email: "",
    site_url: "http://127.0.0.1:9000",
  };

  const settingsConfig = {
    default_provider: "grok",
    internal_llm_provider: "grok",
    gemini_enabled: true,
    grok_enabled: true,
    openai_enabled: true,
    claude_enabled: true,
    gemini_set: true,
    grok_set: true,
    openai_set: true,
    claude_set: true,
    chat_llm_provider: "grok",
    chat_llm_model: "grok-3-mini",
    agent_llm_provider: "grok",
    agent_llm_model: "grok-3",
    orchestrator_llm_provider: "openai",
    orchestrator_llm_model: "gpt-5.2",
    chat_model_gemini: "gemini-2.5-pro",
    chat_model_grok: "grok-3-mini",
    chat_model_openai: "gpt-5.2",
    chat_model_claude: "claude-4.5-sonnet",
    openai_reasoning_effort: "medium",
    domain_auth_enabled: true,
    domain_auth_header: "REMOTE_USER",
    domain_auth_auto_create: true,
  };

  const accessUsers = [
    {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      is_staff: true,
      is_active: true,
      is_superuser: true,
      access_profile: "admin_full",
      groups: [{ id: 11, name: "Core" }],
      effective_permissions: { servers: true, settings: true, orchestrator: true },
      permission_sources: { servers: "profile", settings: "profile", orchestrator: "profile" },
      group_permission_sources: { servers: [{ group_id: 11, group_name: "Core", allowed: true }] },
    },
    {
      id: 2,
      username: "operator",
      email: "operator@example.com",
      is_staff: false,
      is_active: true,
      is_superuser: false,
      access_profile: "server_only",
      groups: [{ id: 11, name: "Core" }],
      effective_permissions: { servers: true, settings: false, orchestrator: false },
      permission_sources: { servers: "group", settings: "direct", orchestrator: "profile" },
      group_permission_sources: { servers: [{ group_id: 11, group_name: "Core", allowed: true }] },
    },
  ];

  const accessGroups = [
    {
      id: 11,
      name: "Core",
      members: [
        { id: 1, username: "admin" },
        { id: 2, username: "operator" },
      ],
      member_count: 2,
      explicit_permissions: { servers: true },
    },
  ];

  const accessPermissions = [
    {
      id: 1,
      user_id: 2,
      username: "operator",
      feature: "settings",
      feature_display: "Settings",
      allowed: false,
    },
  ];

  const accessGroupPermissions = [
    {
      id: 21,
      group_id: 11,
      group_name: "Core",
      feature: "servers",
      feature_display: "Servers",
      allowed: true,
    },
  ];
  return { notifications, settingsConfig, accessUsers, accessGroups, accessPermissions, accessGroupPermissions };
}
