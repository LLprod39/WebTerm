import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleX,
  Gauge,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";

import { fetchSettingsReadiness, type SettingsReadinessCheck, type SettingsReadinessSeverity } from "@/api";
import { Button } from "@/components/ui/button";
import { MetricCard, MetricGrid, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { canUseDemoMode, isDemoMode } from "@/lib/demo";

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
  if (severity === "ready") return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
  if (severity === "warning") return <AlertTriangle className="h-4 w-4 text-amber-400" />;
  return <CircleX className="h-4 w-4 text-red-400" />;
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
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function ReadinessCheckRow({ check }: { check: SettingsReadinessCheck }) {
  const details = summarizeDetails(check.details);
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
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
          <Button asChild variant="outline" size="sm" className="shrink-0">
            <Link to={check.action_path}>{check.action_label || "Открыть"}</Link>
          </Button>
        ) : null}
      </div>

      {details.length ? (
        <details className="mt-3 rounded-md border border-border/50 bg-secondary/20 px-3 py-2 text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none font-medium text-foreground/80">Технические детали</summary>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {details.map(([key, value]) => (
              <div key={key} className="min-w-0 rounded-md bg-background/50 px-2.5 py-2">
                <div className="font-mono text-[11px] text-muted-foreground/75">{key}</div>
                <div className="mt-1 break-words font-mono text-[11px] leading-4 text-foreground/75">
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

export default function SettingsReadinessPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["settings", "readiness"],
    queryFn: fetchSettingsReadiness,
    staleTime: 15_000,
  });

  const clientChecks: SettingsReadinessCheck[] = [
    {
      key: "frontend_demo_mode",
      title: "Frontend demo mode",
      status: canUseDemoMode() ? "warning" : "ready",
      severity: canUseDemoMode() ? "warning" : "ready",
      message: canUseDemoMode()
        ? "VITE_ENABLE_DEMO_MODE=true в frontend build. Для внутреннего PROD запуска demo fallback должен быть выключен."
        : "VITE_ENABLE_DEMO_MODE не включен в frontend build.",
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

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-secondary text-foreground">
            <Gauge className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-foreground">Готовность запуска</h1>
            <p className="text-xs text-muted-foreground">
              Секреты, AI, SSO, уведомления, лимиты, workers, доступы и Marketplace.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
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
        </div>
      </div>

      <QueryStateBlock
        loading={isLoading}
        error={error || (!isLoading && !data?.success ? new Error("Не удалось загрузить readiness report") : undefined)}
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
                description="Нужно проверить перед запуском"
                tone="warning"
                icon={<AlertTriangle className="h-4 w-4" />}
              />
              <MetricCard
                label="Ошибки"
                value={summary.error}
                description="Блокируют нормальный PROD-запуск"
                tone="danger"
                icon={<CircleX className="h-4 w-4" />}
              />
            </MetricGrid>

            <SectionCard
              title="Проблемные зоны"
              description="Проверки отсортированы по критичности, чтобы сначала закрыть блокеры."
              icon={<Gauge className="h-5 w-5 text-primary" />}
            >
              <div className="space-y-3">
                {checks
                  .sort((a, b) => {
                    const order = { error: 0, warning: 1, ready: 2 };
                    return order[a.severity] - order[b.severity] || a.title.localeCompare(b.title);
                  })
                  .map((check) => (
                    <ReadinessCheckRow key={check.key} check={check} />
                  ))}
              </div>
            </SectionCard>
          </>
        ) : null}
      </QueryStateBlock>
    </div>
  );
}
