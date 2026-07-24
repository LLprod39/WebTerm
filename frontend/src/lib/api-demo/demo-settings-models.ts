import {
  DEMO_ACTIVITY_LOGS,
  DEMO_MODELS,
  DEMO_SETTINGS,
} from "../demo";

/** Settings + models demo fallbacks. */
export function demoSettingsModelsFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  // Settings page
  if (path.includes("/api/settings/activity")) return DEMO_ACTIVITY_LOGS as T;
  if (path.includes("/api/settings/readiness")) return {
    success: true,
    status: "warning",
    summary: { ready: 3, warning: 2, error: 0, total: 5 },
    checks: [
      {
        key: "deployment_mode",
        title: "Режим Django",
        status: "warning",
        severity: "warning",
        message: "Demo mode использует dev-настройки. Для PROD запуска включите DJANGO_DEBUG=false.",
        details: { debug: true },
      },
      {
        key: "ai_providers",
        title: "AI providers",
        status: "ready",
        severity: "ready",
        message: "Demo provider готов для интерфейсной проверки.",
        action_path: "/settings/ai",
        action_label: "Открыть модели",
      },
      {
        key: "notifications",
        title: "Уведомления",
        status: "warning",
        severity: "warning",
        message: "В demo mode внешняя отправка уведомлений не выполняется.",
        action_path: "/settings/notifications",
        action_label: "Открыть уведомления",
      },
      {
        key: "ldap_login",
        title: "LDAP Login",
        status: "ready",
        severity: "ready",
        message: "LDAP login выключен в demo mode и показывается как env/startup настройка.",
        action_path: "/settings/sso",
        action_label: "Открыть SSO",
      },
      {
        key: "runtime_limits",
        title: "Runtime limits",
        status: "ready",
        severity: "ready",
        message: "Demo soft limits и LLM budget заданы.",
        action_path: "/settings/limits",
        action_label: "Открыть лимиты",
      },
    ],
  } as T;
  if (path.includes("/api/settings")) return DEMO_SETTINGS as T;
  if (path.includes("/api/models/refresh")) {
    const requestedProvider = (() => {
      try {
        const raw = typeof _options.body === "string" ? JSON.parse(_options.body) : null;
        return typeof raw?.provider === "string" ? raw.provider : "gemini";
      } catch {
        return "gemini";
      }
    })();
    const demoModels =
      requestedProvider === "ollama"
        ? ["llama3.2:latest", "qwen2.5-coder:7b"]
        : requestedProvider === "openai"
          ? ["gpt-5-mini"]
          : requestedProvider === "claude"
            ? ["claude-sonnet-4-6"]
            : requestedProvider === "grok"
              ? ["grok-3"]
              : ["gemini-2.0-flash"];
    return { success: true, provider: requestedProvider, models: demoModels, count: demoModels.length } as T;
  }
  if (path.includes("/api/models")) return DEMO_MODELS as T;
  return undefined;
}
