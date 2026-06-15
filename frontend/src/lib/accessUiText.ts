export type AccessUiLang = "en" | "ru";

const FEATURE_LABELS: Record<AccessUiLang, Record<string, string>> = {
  en: {
    servers: "Servers",
    dashboard: "Dashboard",
    agents: "Agents",
    studio: "Studio",
    studio_pipelines: "Studio: Pipelines",
    studio_runs: "Studio: Runs",
    studio_agents: "Studio: Agents",
    studio_skills: "Studio: Skills",
    studio_mcp: "Studio: MCP",
    studio_notifications: "Studio: Notifications",
    kubernetes: "Kubernetes",
    mars: "MARS",
    settings: "Settings",
    orchestrator: "Orchestrator",
    knowledge_base: "Knowledge Base",
  },
  ru: {
    servers: "Серверы",
    dashboard: "Панель",
    agents: "Агенты",
    studio: "Студия",
    studio_pipelines: "Студия: Пайплайны",
    studio_runs: "Студия: Запуски",
    studio_agents: "Студия: Агент-конфиги",
    studio_skills: "Студия: Скиллы",
    studio_mcp: "Студия: MCP",
    studio_notifications: "Студия: Уведомления",
    kubernetes: "Кубернетес",
    mars: "MARS",
    settings: "Настройки",
    orchestrator: "Оркестратор",
    knowledge_base: "База знаний",
  },
};

const PROFILE_LABELS: Record<AccessUiLang, Record<string, string>> = {
  en: {
    server_only: "Server only",
    admin_full: "Admin full",
    custom: "Custom",
    reset_defaults: "Reset defaults",
  },
  ru: {
    server_only: "Только серверы",
    admin_full: "Полный админ",
    custom: "Кастомный",
    reset_defaults: "Сбросить по умолчанию",
  },
};

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
      passwordPrompt: "New password for {name}",
      passwordUpdated: "Password updated",
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
      passwordPrompt: "Новый пароль для {name}",
      passwordUpdated: "Пароль обновлён",
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

export function getAccessFeatureLabel(lang: AccessUiLang, feature: string, fallback?: string) {
  return FEATURE_LABELS[lang][feature] || fallback || feature;
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
