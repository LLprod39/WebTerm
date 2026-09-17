export type AccessUiLang = "en" | "ru";

export type AccessFeatureGroup =
  | "workspace"
  | "automation"
  | "studio"
  | "ai"
  | "kubernetes"
  | "knowledge";

export type AccessFeatureMeta = {
  labelEn: string;
  labelRu: string;
  descriptionEn: string;
  descriptionRu: string;
  group: AccessFeatureGroup;
  /** Short chip label when collapsing related features */
  chipEn?: string;
  chipRu?: string;
};

/** Canonical UI catalog — keys match backend FEATURE_CHOICES (do not rename codes). */
export const ACCESS_FEATURE_META: Record<string, AccessFeatureMeta> = {
  servers: {
    labelEn: "Servers",
    labelRu: "Серверы",
    descriptionEn: "Inventory, terminal, shares, and server settings.",
    descriptionRu: "Инвентарь, терминал, доступы и настройки серверов.",
    group: "workspace",
  },
  dashboard: {
    labelEn: "Dashboard",
    labelRu: "Панель",
    descriptionEn: "Home panel and high-level fleet overview.",
    descriptionRu: "Главная панель и обзор флота.",
    group: "workspace",
  },
  agents: {
    labelEn: "Agents",
    labelRu: "Агенты",
    descriptionEn: "Agent catalog, runs, and run reports.",
    descriptionRu: "Каталог агентов, запуски и отчёты.",
    group: "automation",
  },
  chat: {
    labelEn: "Chat (assistant)",
    labelRu: "Чат (ассистент)",
    descriptionEn: "Operator chat assistant in the main Chat section.",
    descriptionRu: "Ассистент в разделе «Чат».",
    group: "workspace",
  },
  automation: {
    labelEn: "Automation (playbooks)",
    labelRu: "Автоматизация (плейбуки)",
    descriptionEn: "Ansible playbooks, bindings, and run wizard.",
    descriptionRu: "Ansible-плейбуки, привязки и мастер запуска.",
    group: "automation",
  },
  ai_connections_personal: {
    labelEn: "AI connections (personal)",
    labelRu: "AI-подключения (личные)",
    descriptionEn: "Personal provider keys and models in Settings → AI.",
    descriptionRu: "Личные ключи и модели в Настройки → AI.",
    group: "ai",
  },
  ai_connections_admin: {
    labelEn: "AI connections (workspace admin)",
    labelRu: "AI-подключения (админ workspace)",
    descriptionEn: "Manage workspace-wide AI providers and routing (opt-in).",
    descriptionRu: "Управление AI-провайдерами workspace и маршрутизацией (выдаётся отдельно).",
    group: "ai",
  },
  studio: {
    labelEn: "Studio",
    labelRu: "Студия",
    descriptionEn: "Studio hub. Section APIs may still need Studio section grants.",
    descriptionRu: "Хаб Студии. Для секций API могут требоваться отдельные права.",
    group: "studio",
  },
  studio_pipelines: {
    labelEn: "Studio: Pipelines",
    labelRu: "Студия: Пайплайны",
    descriptionEn: "Create and edit Studio pipelines.",
    descriptionRu: "Создание и редактирование пайплайнов Студии.",
    group: "studio",
  },
  studio_runs: {
    labelEn: "Studio: Runs",
    labelRu: "Студия: Запуски",
    descriptionEn: "View and manage Studio pipeline runs.",
    descriptionRu: "Просмотр и управление запусками пайплайнов.",
    group: "studio",
  },
  studio_agents: {
    labelEn: "Studio: Agent configs",
    labelRu: "Студия: Агент-конфиги",
    descriptionEn: "Studio agent configuration API (separate from main Agents).",
    descriptionRu: "Конфиги агентов Студии (отдельно от раздела «Агенты»).",
    group: "studio",
  },
  studio_skills: {
    labelEn: "Studio: Skills",
    labelRu: "Студия: Скиллы",
    descriptionEn: "Studio skills catalog.",
    descriptionRu: "Каталог скиллов Студии.",
    group: "studio",
  },
  studio_mcp: {
    labelEn: "Studio: MCP",
    labelRu: "Студия: MCP",
    descriptionEn: "Model Context Protocol registry in Studio.",
    descriptionRu: "Реестр MCP (Model Context Protocol) в Студии.",
    group: "studio",
  },
  studio_notifications: {
    labelEn: "Studio: Notifications",
    labelRu: "Студия: Уведомления",
    descriptionEn: "Studio alerts and notification settings.",
    descriptionRu: "Алерты и уведомления Студии.",
    group: "studio",
  },
  telegram_notifications: {
    labelEn: "Telegram: Notifications",
    labelRu: "Telegram: Уведомления",
    descriptionEn: "Personal Telegram chat ID for agent reports and alerts.",
    descriptionRu: "Личный Telegram chat ID для отчётов агентов и алертов.",
    group: "automation",
  },
  telegram_assistant: {
    labelEn: "Telegram: AI Assistant",
    labelRu: "Telegram: ИИ-ассистент",
    descriptionEn: "Link Telegram and chat with the platform assistant; create personal bots.",
    descriptionRu: "Привязка Telegram и чат с ассистентом платформы; создание личных ботов.",
    group: "automation",
  },
  kubernetes: {
    labelEn: "Kubernetes",
    labelRu: "Кубернетес",
    descriptionEn: "Cluster inventory and request/approval flows.",
    descriptionRu: "Инвентарь кластеров и заявки на изменения.",
    group: "kubernetes",
  },
  kubernetes_admin_read: {
    labelEn: "Kubernetes: deep inspect",
    labelRu: "Kubernetes: углублённый просмотр",
    descriptionEn: "Live YAML, logs, and watch (needs admin mode; opt-in).",
    descriptionRu: "Живой YAML, логи и watch (нужен admin mode; выдаётся отдельно).",
    group: "kubernetes",
    chipEn: "K8s: inspect",
    chipRu: "K8s: просмотр",
  },
  kubernetes_admin_write: {
    labelEn: "Kubernetes: mutate cluster",
    labelRu: "Kubernetes: изменение кластера",
    descriptionEn: "Apply, patch, scale, delete (native admin flags; opt-in).",
    descriptionRu: "Apply, patch, scale, delete (флаги admin; выдаётся отдельно).",
    group: "kubernetes",
    chipEn: "K8s: write",
    chipRu: "K8s: запись",
  },
  kubernetes_break_glass: {
    labelEn: "Kubernetes: emergency access (exec)",
    labelRu: "Kubernetes: аварийный доступ (exec)",
    descriptionEn: "Pod exec, port-forward, node debug — high risk (opt-in).",
    descriptionRu: "Exec в под, port-forward, отладка нод — высокий риск (выдаётся отдельно).",
    group: "kubernetes",
    chipEn: "K8s: break-glass",
    chipRu: "K8s: аварийный",
  },
  kubernetes_secret_read: {
    labelEn: "Kubernetes: read secrets",
    labelRu: "Kubernetes: чтение секретов",
    descriptionEn: "View secret values (env-gated; opt-in).",
    descriptionRu: "Просмотр значений секретов (ещё и env-флаг; выдаётся отдельно).",
    group: "kubernetes",
    chipEn: "K8s: secrets",
    chipRu: "K8s: секреты",
  },
  mars: {
    labelEn: "MARS (diagnostics)",
    labelRu: "MARS (диагностика)",
    descriptionEn: "MARS diagnostic workflows (opt-in).",
    descriptionRu: "Диагностические сценарии MARS (выдаётся отдельно).",
    group: "knowledge",
  },
  settings: {
    labelEn: "Settings",
    labelRu: "Настройки",
    descriptionEn: "Platform settings, users, groups, audit (except AI connections).",
    descriptionRu: "Настройки платформы, пользователи, группы, аудит (кроме AI-подключений).",
    group: "workspace",
  },
  orchestrator: {
    labelEn: "Orchestrator (legacy)",
    labelRu: "Оркестратор (legacy)",
    descriptionEn: "Legacy orchestrator / tools API — not the main Chat UI.",
    descriptionRu: "Legacy API оркестратора — это не основной раздел «Чат».",
    group: "automation",
  },
  knowledge_base: {
    labelEn: "Knowledge Base",
    labelRu: "База знаний",
    descriptionEn: "RAG / knowledge-base API used by assistants.",
    descriptionRu: "RAG / API базы знаний для ассистентов.",
    group: "knowledge",
  },
  web_research: {
    labelEn: "Web research (chat tool)",
    labelRu: "Веб-исследование (инструмент чата)",
    descriptionEn: "Allows the assistant to use web research tools (opt-in).",
    descriptionRu: "Разрешает ассистенту веб-поиск (выдаётся отдельно).",
    group: "knowledge",
  },
};

const FEATURE_GROUP_LABELS: Record<AccessUiLang, Record<AccessFeatureGroup, string>> = {
  en: {
    workspace: "Workspace",
    automation: "Automation & agents",
    studio: "Studio",
    ai: "AI connections",
    kubernetes: "Kubernetes",
    knowledge: "Knowledge & research",
  },
  ru: {
    workspace: "Рабочая область",
    automation: "Автоматизация и агенты",
    studio: "Студия",
    ai: "AI-подключения",
    kubernetes: "Kubernetes",
    knowledge: "Знания и исследование",
  },
};

const FEATURE_GROUP_ORDER: AccessFeatureGroup[] = [
  "workspace",
  "automation",
  "studio",
  "ai",
  "kubernetes",
  "knowledge",
];

const STUDIO_SECTION_KEYS = [
  "studio_pipelines",
  "studio_runs",
  "studio_agents",
  "studio_skills",
  "studio_mcp",
  "studio_notifications",
] as const;

const K8S_CAPABILITY_KEYS = [
  "kubernetes_admin_read",
  "kubernetes_admin_write",
  "kubernetes_break_glass",
  "kubernetes_secret_read",
] as const;

const PROFILE_LABELS: Record<AccessUiLang, Record<string, string>> = {
  en: {
    pilot_user: "User",
    pilot_operator: "Operator",
    server_only: "Server only",
    operator_server_only: "Operator: servers",
    operator_studio_runner: "Operator: Studio runner",
    team_admin_no_secrets: "Team admin, no secrets",
    admin_full: "Admin full",
    platform_admin: "Platform admin",
    custom: "Custom",
    reset_defaults: "Reset defaults",
  },
  ru: {
    pilot_user: "Пользователь",
    pilot_operator: "Оператор",
    server_only: "Только серверы",
    operator_server_only: "Оператор: серверы",
    operator_studio_runner: "Оператор: Studio запуск",
    team_admin_no_secrets: "Админ команды без секретов",
    admin_full: "Полный админ",
    platform_admin: "Админ платформы",
    custom: "Кастомный",
    reset_defaults: "Сбросить по умолчанию",
  },
};

export const ACCESS_PROFILE_OPTIONS = [
  "operator_server_only",
  "operator_studio_runner",
  "team_admin_no_secrets",
  "platform_admin",
  "server_only",
  "admin_full",
  "custom",
  "reset_defaults",
] as const;

const SOURCE_LABELS: Record<AccessUiLang, Record<string, string>> = {
  en: {
    user_explicit: "user override",
    group_explicit: "group policy",
    staff_default: "staff default",
    staff_required: "staff only",
    settings_opt_in: "settings opt-in",
    default_allow: "default allow",
    default_deny: "default deny",
  },
  ru: {
    user_explicit: "личное правило",
    group_explicit: "политика группы",
    staff_default: "по умолчанию (админ)",
    staff_required: "только для администраторов",
    settings_opt_in: "по выдаче в настройках",
    default_allow: "разрешено по умолчанию",
    default_deny: "запрещено по умолчанию",
  },
};

export const ACCESS_UI_TEXT = {
  en: {
    common: {
      inherit: "Inherit",
      unset: "Unset",
      allow: "Allow",
      deny: "Deny",
      allowed: "Allowed",
      denied: "Denied",
      effective: "Effective",
      source: "Source",
      save: "Save",
      saving: "Saving...",
      cancel: "Cancel",
      delete: "Delete",
      toggle: "Toggle",
      none: "none",
      noEmail: "No email",
      groups: "Groups",
      members: "Members",
      profile: "Profile",
      staff: "staff",
      nonStaff: "non-staff",
      active: "active",
      inactive: "inactive",
      password: "Password",
    },
    users: {
      title: "Users",
      subtitle: "Create users, assign groups, and control explicit feature overrides from one place.",
      createTitle: "Create User",
      createHint: "Profile and groups can be changed later in the same GUI.",
      username: "Username",
      email: "Email",
      passwordPlaceholder: "Password",
      createAction: "Create User",
      creatingAction: "Creating...",
      editAction: "Edit Access",
      explicitOverrides: "Explicit feature overrides",
      explicitOverridesHint: "Inherit keeps the current value from staff defaults, group policy, or global defaults.",
      effectiveAccess: "Effective access",
      deleteConfirm: "Delete user {name}?",
      deleteDescription: "This removes {name}'s account, direct overrides, and group assignments from WebTerm. Server-side audit history remains available.",
      deleteAction: "Delete user",
      passwordPrompt: "New password for {name}",
      passwordUpdated: "Password updated",
      resetPasswordTitle: "Reset password",
      resetPasswordDescription: "Set a new local password for {name}. Share it through a secure channel after saving.",
      generatePassword: "Generate",
      manualPassword: "Manual",
      newPassword: "New password",
      showPassword: "Show password",
      hidePassword: "Hide password",
      copyPassword: "Copy password",
      regeneratePassword: "Generate another password",
      passwordPolicy: "Password policy",
      passwordRuleLength: "At least 12 characters",
      passwordRuleComplexity: "Use at least three of: uppercase, lowercase, number, symbol",
      passwordRuleUsername: "Does not contain the username",
      passwordCopied: "Password copied.",
      resetPasswordAction: "Update password",
      loading: "Loading users...",
      error: "Failed to load users.",
    },
    groupsPage: {
      title: "Groups",
      subtitle: "Manage shared memberships and group-level access policies that apply before per-user defaults.",
      createTitle: "Create Group",
      namePlaceholder: "Group name",
      policyTitle: "Group feature policy",
      createAction: "Create Group",
      creatingAction: "Creating...",
      editAction: "Edit Group",
      explicitPolicy: "Explicit policy",
      deleteConfirm: "Delete group {name}?",
      loading: "Loading groups...",
      error: "Failed to load groups.",
    },
    permissions: {
      title: "Permissions",
      subtitle: "Audit and edit explicit user overrides and group policies separately.",
      userOverrideTitle: "Add / Update User Override",
      groupPolicyTitle: "Add / Update Group Policy",
      userListTitle: "User Explicit Permissions",
      groupListTitle: "Group Explicit Permissions",
      noUserOverrides: "No explicit user overrides.",
      noGroupPolicies: "No explicit group policies.",
      deleteUserPermission: "Delete user permission?",
      deleteGroupPermission: "Delete group permission?",
      loading: "Loading permissions...",
      error: "Failed to load permissions.",
    },
  },
  ru: {
    common: {
      inherit: "Наследовать",
      unset: "Не задано",
      allow: "Разрешить",
      deny: "Запретить",
      allowed: "Разрешено",
      denied: "Запрещено",
      effective: "Итог",
      source: "Источник",
      save: "Сохранить",
      saving: "Сохранение...",
      cancel: "Отмена",
      delete: "Удалить",
      toggle: "Переключить",
      none: "нет",
      noEmail: "Без email",
      groups: "Группы",
      members: "Участники",
      profile: "Профиль",
      staff: "администратор",
      nonStaff: "пользователь",
      active: "активен",
      inactive: "неактивен",
      password: "Пароль",
    },
    users: {
      title: "Пользователи",
      subtitle: "Аккаунты, профили доступа и назначение групп.",
      createTitle: "Создать пользователя",
      createHint: "Профиль и группы можно изменить позже.",
      username: "Логин",
      email: "Email",
      passwordPlaceholder: "Пароль",
      createAction: "Создать пользователя",
      creatingAction: "Создание...",
      editAction: "Изменить доступ",
      explicitOverrides: "Переопределения прав доступа",
      explicitOverridesHint: "Наследование сохраняет значение из профиля администратора, политики группы или настроек по умолчанию.",
      effectiveAccess: "Итоговый доступ",
      deleteConfirm: "Удалить пользователя {name}?",
      deleteDescription: "Аккаунт {name}, личные правила и назначения групп будут удалены из WebTerm. Серверная история аудита сохранится.",
      deleteAction: "Удалить пользователя",
      passwordPrompt: "Новый пароль для {name}",
      passwordUpdated: "Пароль обновлён",
      resetPasswordTitle: "Сброс пароля",
      resetPasswordDescription: "Задайте новый локальный пароль для {name}. После сохранения передайте его пользователю безопасным каналом.",
      generatePassword: "Сгенерировать",
      manualPassword: "Вручную",
      newPassword: "Новый пароль",
      showPassword: "Показать пароль",
      hidePassword: "Скрыть пароль",
      copyPassword: "Скопировать пароль",
      regeneratePassword: "Сгенерировать другой пароль",
      passwordPolicy: "Политика пароля",
      passwordRuleLength: "Не меньше 12 символов",
      passwordRuleComplexity: "Минимум три типа символов: верхний регистр, нижний регистр, цифра, знак",
      passwordRuleUsername: "Не содержит логин пользователя",
      passwordCopied: "Пароль скопирован.",
      resetPasswordAction: "Обновить пароль",
      loading: "Загрузка пользователей...",
      error: "Не удалось загрузить пользователей.",
    },
    groupsPage: {
      title: "Группы",
      subtitle: "Участники и групповые политики доступа.",
      createTitle: "Создать группу",
      namePlaceholder: "Название группы",
      policyTitle: "Групповая политика прав",
      createAction: "Создать группу",
      creatingAction: "Создание...",
      editAction: "Изменить группу",
      explicitPolicy: "Явная политика",
      deleteConfirm: "Удалить группу {name}?",
      loading: "Загрузка групп...",
      error: "Не удалось загрузить группы.",
    },
    permissions: {
      title: "Права доступа",
      subtitle: "Точечные правила для пользователей и групп.",
      userOverrideTitle: "Правило для пользователя",
      groupPolicyTitle: "Политика для группы",
      userListTitle: "Явные права пользователей",
      groupListTitle: "Явные права групп",
      noUserOverrides: "Персональных правил нет.",
      noGroupPolicies: "Групповых политик нет.",
      deleteUserPermission: "Удалить правило пользователя?",
      deleteGroupPermission: "Удалить правило группы?",
      loading: "Загрузка прав...",
      error: "Не удалось загрузить права.",
    },
  },
} as const;

export function formatAccessText(template: string, values: Record<string, string | number>) {
  return Object.entries(values).reduce(
    (text, [key, value]) => text.replaceAll(`{${key}}`, String(value)),
    template,
  );
}

export function getAccessFeatureMeta(feature: string): AccessFeatureMeta | undefined {
  return ACCESS_FEATURE_META[feature];
}

export function getAccessFeatureLabel(lang: AccessUiLang, feature: string, fallback?: string) {
  const meta = ACCESS_FEATURE_META[feature];
  if (meta) return lang === "ru" ? meta.labelRu : meta.labelEn;
  return fallback || feature;
}

export function getAccessFeatureDescription(lang: AccessUiLang, feature: string) {
  const meta = ACCESS_FEATURE_META[feature];
  if (!meta) return "";
  return lang === "ru" ? meta.descriptionRu : meta.descriptionEn;
}

export function getAccessFeatureGroupLabel(lang: AccessUiLang, group: AccessFeatureGroup) {
  return FEATURE_GROUP_LABELS[lang][group];
}

export function getAccessFeatureChipLabel(lang: AccessUiLang, feature: string, fallback?: string) {
  const meta = ACCESS_FEATURE_META[feature];
  if (!meta) return getAccessFeatureLabel(lang, feature, fallback);
  const chip = lang === "ru" ? meta.chipRu : meta.chipEn;
  return chip || (lang === "ru" ? meta.labelRu : meta.labelEn);
}

export function groupAccessFeatures<T extends { value: string; label: string }>(
  lang: AccessUiLang,
  features: T[],
): Array<{ group: AccessFeatureGroup; title: string; features: T[] }> {
  const buckets = new Map<AccessFeatureGroup, T[]>();
  const orphan: T[] = [];

  for (const feature of features) {
    const group = ACCESS_FEATURE_META[feature.value]?.group;
    if (!group) {
      orphan.push(feature);
      continue;
    }
    const list = buckets.get(group) || [];
    list.push(feature);
    buckets.set(group, list);
  }

  const grouped = FEATURE_GROUP_ORDER.filter((group) => (buckets.get(group) || []).length > 0).map((group) => ({
    group,
    title: getAccessFeatureGroupLabel(lang, group),
    features: buckets.get(group) || [],
  }));

  if (orphan.length) {
    grouped.push({
      group: "workspace",
      title: lang === "ru" ? "Прочее" : "Other",
      features: orphan,
    });
  }

  return grouped;
}

/**
 * Collapse Studio parent+sections and shorten K8s capability chips for dense summaries.
 * Counts stay based on the original entries.
 */
export function collapsePermissionSummaryEntries(
  lang: AccessUiLang,
  entries: Array<[string, boolean]>,
  labelFor: (feature: string) => string,
): Array<{ key: string; label: string; allowed: boolean; title?: string }> {
  const map = new Map(entries);
  const used = new Set<string>();
  const result: Array<{ key: string; label: string; allowed: boolean; title?: string }> = [];

  const studioParent = map.get("studio");
  const studioSections = STUDIO_SECTION_KEYS.filter((key) => map.has(key));
  if (studioParent !== undefined || studioSections.length >= 2) {
    const allowedSections = studioSections.filter((key) => map.get(key)).length;
    const anyDenied = studioSections.some((key) => map.get(key) === false) || studioParent === false;
    const anyAllowed = studioParent === true || allowedSections > 0;
    const sectionCount = studioSections.length || STUDIO_SECTION_KEYS.length;
    used.add("studio");
    studioSections.forEach((key) => used.add(key));
    result.push({
      key: "studio_bundle",
      allowed: anyAllowed && !anyDenied ? true : anyAllowed,
      label:
        lang === "ru"
          ? `Студия (+${allowedSections || (studioParent ? sectionCount : 0)} секций)`
          : `Studio (+${allowedSections || (studioParent ? sectionCount : 0)} sections)`,
      title: studioSections.map((key) => `${labelFor(key)}: ${map.get(key) ? "✓" : "✗"}`).join("\n"),
    });
    // If mixed allow/deny within studio, still show one chip; details in title.
  }

  for (const key of K8S_CAPABILITY_KEYS) {
    if (!map.has(key)) continue;
    used.add(key);
    const allowed = Boolean(map.get(key));
    result.push({
      key,
      allowed,
      label: getAccessFeatureChipLabel(lang, key, labelFor(key)),
      title: getAccessFeatureDescription(lang, key),
    });
  }

  for (const [feature, allowed] of entries) {
    if (used.has(feature)) continue;
    result.push({
      key: feature,
      allowed,
      label: labelFor(feature),
      title: getAccessFeatureDescription(lang, feature),
    });
  }

  return result;
}

export function getAccessProfileLabel(lang: AccessUiLang, profile: string) {
  return PROFILE_LABELS[lang][profile] || profile.replaceAll("_", " ");
}

export function getAccessSourceLabel(lang: AccessUiLang, source?: string) {
  if (!source) return "";
  return SOURCE_LABELS[lang][source] || source.replaceAll("_", " ");
}

export function localizeAccessFeatures(
  lang: AccessUiLang,
  features: Array<{ value: string; label: string }>,
) {
  return features.map((feature) => ({
    ...feature,
    label: getAccessFeatureLabel(lang, feature.value, feature.label),
  }));
}

export function summarizeAllowedFeatures(
  lang: AccessUiLang,
  permissions?: Record<string, boolean>,
) {
  return Object.entries(permissions || {})
    .filter(([, allowed]) => allowed)
    .map(([feature]) => getAccessFeatureLabel(lang, feature))
    .join(", ");
}
