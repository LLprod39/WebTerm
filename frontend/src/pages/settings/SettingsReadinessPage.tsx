import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleX,
  Gauge,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";

import {
  fetchAuthSession,
  fetchSettingsReadiness,
  type SettingsReadinessCheck,
  type SettingsReadinessSeverity,
} from "@/api";
import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
import { Button } from "@/components/ui/button";
import { MetricCard, MetricGrid, QueryStateBlock, StatusBadge } from "@/components/ui/page-shell";
import { canUseDemoMode, isDemoMode } from "@/lib/demo";
import { cn } from "@/lib/utils";
import { markFirstRunReadinessSeen, safeFirstRunNextPath } from "@/lib/first-run-readiness";
import { localize, useI18n } from "@/lib/i18n";

function severityTone(severity: SettingsReadinessSeverity): "success" | "warning" | "danger" {
  if (severity === "ready") return "success";
  if (severity === "warning") return "warning";
  return "danger";
}

function severityLabel(severity: SettingsReadinessSeverity) {
  if (severity === "ready") return "Готово";
  if (severity === "warning") return "Внимание";
  return "Ошибка";
}

const SEVERITY_RANK: Record<SettingsReadinessSeverity, number> = { ready: 0, warning: 1, error: 2 };

function SeverityIcon({ severity }: { severity: SettingsReadinessSeverity }) {
  if (severity === "ready") return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (severity === "warning") return <AlertTriangle className="h-4 w-4 text-warning" />;
  return <CircleX className="h-4 w-4 text-destructive" />;
}

function summarizeDetails(details?: Record<string, unknown>) {
  if (!details) return [];
  return Object.entries(details)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .slice(0, 8);
}

function formatDetailValue(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.map((item) => (typeof item === "object" ? JSON.stringify(item) : String(item))).join(", ") : "[]";
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "да" : "нет";
  return String(value);
}

function ReadinessCheckRow({ check }: { check: SettingsReadinessCheck }) {
  const details = summarizeDetails(check.details);
  return (
    <div className="rounded-sm border border-border bg-surface-0/60 px-4 py-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityIcon severity={check.severity} />
            <h2 className="text-sm font-semibold text-foreground">{check.title}</h2>
            <StatusBadge label={severityLabel(check.severity)} tone={severityTone(check.severity)} />
          </div>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{check.message}</p>
        </div>
        {check.action_path ? (
          <Button asChild variant="outline" size="sm" className="shrink-0 gap-1.5">
            <Link to={check.action_path}>
              {check.action_label || "Настроить"}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        ) : null}
      </div>

      {details.length ? (
        <details className="mt-3 rounded-sm border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none font-medium text-foreground/80">Технические детали</summary>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {details.map(([key, value]) => (
              <div key={key} className="min-w-0 rounded-sm bg-surface-0 px-2.5 py-2">
                <div className="font-mono text-2xs text-muted-foreground/75">{key}</div>
                <div className="mt-1 break-words font-mono text-2xs leading-4 text-foreground/75">
                  {formatDetailValue(value)}
                </div>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

const SETUP_PATH = [
  { path: "/settings/ai", title: "1. ИИ и модели", body: "Провайдеры, ключи и модели" },
  { path: "/settings/notifications", title: "2. Оповещения", body: "Telegram, почта и внешний адрес" },
  { path: "/settings/users", title: "3. Пользователи", body: "Аккаунты команды и профили доступа" },
  { path: "/settings/limits", title: "4. Лимиты", body: "Запуски, SSH-сессии и токены" },
  { path: "/settings/sso", title: "5. SSO (необязательно)", body: "Корпоративный вход и LDAP" },
  { path: "/settings/plugins", title: "6. Плагины", body: "Каталог и локальные расширения" },
];

export default function SettingsReadinessPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { lang } = useI18n();
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const { data, isLoading, error } = useQuery({
    queryKey: ["settings", "readiness"],
    queryFn: fetchSettingsReadiness,
    staleTime: 15_000,
  });

  const clientChecks: SettingsReadinessCheck[] = [
    {
      key: "frontend_demo_mode",
      title: "Демонстрационный режим",
      status: canUseDemoMode() ? "warning" : "ready",
      severity: canUseDemoMode() ? "warning" : "ready",
      message: canUseDemoMode()
        ? "Демонстрационный вход включён в сборке. Перед рабочим запуском отключите его."
        : "Демонстрационный вход выключен.",
      details: {
        vite_enable_demo_mode: canUseDemoMode(),
        demo_mode_active: isDemoMode(),
      },
    },
  ];
  const checks = [...clientChecks, ...(data?.checks || [])];
  const summary = data?.summary
    ? {
        ready: checks.filter((item) => item.severity === "ready").length,
        warning: checks.filter((item) => item.severity === "warning").length,
        error: checks.filter((item) => item.severity === "error").length,
        total: checks.length,
      }
    : undefined;
  const status = checks.reduce<SettingsReadinessSeverity>(
    (worst, item) => (SEVERITY_RANK[item.severity] > SEVERITY_RANK[worst] ? item.severity : worst),
    data?.status || "warning",
  );

  const setupPath = authData?.user?.features.plugins
    ? SETUP_PATH
    : SETUP_PATH.filter((step) => step.path !== "/settings/plugins");
  const firstRun = searchParams.get("firstRun") === "1";
  const degradedFirstRun = searchParams.get("degraded") === "1";
  const continuePath = safeFirstRunNextPath(searchParams.get("next"));

  const continueToWorkspace = () => {
    if (authData?.user?.id) markFirstRunReadinessSeen(authData.user.id);
    navigate(continuePath, { replace: true });
  };

  return (
    <div className="space-y-5 pb-10">
      {firstRun ? (
        <section className="rounded-sm border border-primary/40 bg-primary/8 p-4 shadow-elev-1 sm:p-5" aria-labelledby="first-run-readiness-title">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-primary">
                {localize(lang, "Первый запуск", "First run")}
              </p>
              <h1 id="first-run-readiness-title" className="mt-2 font-display text-xl font-bold tracking-tight text-foreground">
                {localize(lang, "Подготовьте WebTerm к работе", "Prepare WebTerm for operations")}
              </h1>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {localize(
                  lang,
                  "Проверьте обязательные настройки, затем добавьте первый сервер. Ошибки останутся видимыми.",
                  "Review the required settings, then add your first server. This wizard uses live backend readiness and does not hide failures.",
                )}
              </p>
              {degradedFirstRun ? (
                <p className="mt-3 rounded-sm border border-warning/35 bg-warning/10 px-3 py-2 text-xs text-warning-foreground" role="alert">
                  {localize(lang, "Проверка готовности недоступна. Восстановите соединение или продолжите с ограничениями.", "The readiness check is unavailable. Restore connectivity or continue in degraded mode.")}
                </p>
              ) : null}
            </div>
            <Button variant="outline" className="shrink-0" onClick={continueToWorkspace}>
              {localize(lang, "Продолжить в рабочую область", "Continue to workspace")}
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
          </div>
        </section>
      ) : null}

      <SettingsPageHeader
        icon={Gauge}
        title="Готовность платформы"
        description="Проверьте обязательные настройки перед началом работы."
        actions={
          <>
            <StatusBadge label={severityLabel(status)} tone={severityTone(status)} />
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => queryClient.invalidateQueries({ queryKey: ["settings", "readiness"] })}
            >
              <RefreshCcw className="h-4 w-4" />
              Обновить
            </Button>
          </>
        }
      />

      {/* Guided setup path */}
      <section className="rounded-sm border border-border bg-card p-4 shadow-elev-1 sm:p-5">
        <div className="mb-4">
          <h2 className="font-display text-sm font-bold tracking-tight text-foreground">
            Порядок настройки
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Настройте основные разделы по порядку.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {setupPath.map((step) => (
            <Link
              key={step.path}
              to={step.path}
              className={cn(
                "group flex flex-col rounded-sm border border-border bg-surface-0 p-3.5 transition-colors",
                "hover:border-primary/45 hover:bg-primary/5",
              )}
            >
              <span className="text-sm font-semibold text-foreground group-hover:text-primary">
                {step.title}
              </span>
              <span className="mt-1 text-xs leading-5 text-muted-foreground">{step.body}</span>
              <span className="mt-3 inline-flex items-center gap-1 text-2xs font-medium text-primary">
                Открыть <ArrowRight className="h-3 w-3" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <QueryStateBlock
        loading={isLoading}
        error={error || (!isLoading && !data?.success ? new Error("Не удалось загрузить отчёт о готовности") : undefined)}
        errorText="Не удалось загрузить проверку готовности"
        onRetry={() => queryClient.invalidateQueries({ queryKey: ["settings", "readiness"] })}
      >
        {summary ? (
          <>
            <MetricGrid>
              <MetricCard
                label="Всего"
                value={summary.total}
                description="Проверок платформы"
                tone="info"
                icon={<ShieldCheck className="h-4 w-4" />}
              />
              <MetricCard
                label="Готово"
                value={summary.ready}
                description="Не требуют действий"
                tone="success"
                icon={<CheckCircle2 className="h-4 w-4" />}
              />
              <MetricCard
                label="Внимание"
                value={summary.warning}
                description="Требуют проверки"
                tone="warning"
                icon={<AlertTriangle className="h-4 w-4" />}
              />
              <MetricCard
                label="Ошибки"
                value={summary.error}
                description="Блокируют нормальный запуск"
                tone="danger"
                icon={<CircleX className="h-4 w-4" />}
              />
            </MetricGrid>

            <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
              <div className="border-b border-border bg-surface-0/50 px-5 py-4">
                <h2 className="text-sm font-semibold text-foreground">Что требует внимания</h2>
              </div>
              <div className="space-y-3 p-4 sm:p-5">
                {checks
                  .slice()
                  .sort((a, b) => {
                    const order = { error: 0, warning: 1, ready: 2 };
                    return order[a.severity] - order[b.severity] || a.title.localeCompare(b.title);
                  })
                  .map((check) => (
                    <ReadinessCheckRow key={check.key} check={check} />
                  ))}
              </div>
            </section>
          </>
        ) : null}
      </QueryStateBlock>
    </div>
  );
}
