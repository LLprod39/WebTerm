import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers3, Search } from "lucide-react";

import { fetchKubernetesDevtronApps } from "@/api";
import { EmptyState, QueryStateBlock, SectionCard } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { AppRow } from "@/pages/kubernetes-page/kubernetesPageSections";
import {
  CockpitChip,
  countHealth,
  HealthDonut,
  HealthLegend,
  KpiTile,
} from "@/pages/kubernetes-page/KubernetesCockpitPrimitives";
import {
  K8sRefreshButton,
  KubernetesPageHeader,
  KubernetesShell,
} from "@/pages/kubernetes-page/KubernetesShell";
import { useKubernetesDeepLinkAudit } from "@/pages/kubernetes-page/useKubernetesDeepLinkAudit";

type AppFilter = "all" | "healthy" | "warning" | "degraded";

export default function KubernetesDevtronPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const auditDeepLink = useKubernetesDeepLinkAudit();
  const [filter, setFilter] = useState<AppFilter>("all");
  const [q, setQ] = useState("");
  const appsQuery = useQuery({
    queryKey: ["kubernetes", "devtron", "apps"],
    queryFn: fetchKubernetesDevtronApps,
    staleTime: 15_000,
  });
  const apps = useMemo(() => appsQuery.data?.apps || [], [appsQuery.data?.apps]);
  const buckets = countHealth(apps);
  const teams = new Set(apps.map((app) => app.team).filter(Boolean)).size;
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["kubernetes", "devtron", "apps"] });

  const filtered = useMemo(() => {
    let rows = apps;
    if (filter !== "all") rows = rows.filter((a) => a.health === filter);
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      rows = rows.filter(
        (a) =>
          a.name.toLowerCase().includes(needle) ||
          a.namespace.toLowerCase().includes(needle) ||
          a.team.toLowerCase().includes(needle) ||
          a.version.toLowerCase().includes(needle),
      );
    }
    return rows;
  }, [apps, filter, q]);

  const slices = [
    { key: "healthy", label: "Healthy", value: buckets.healthy, color: "#34d399" },
    { key: "warning", label: "Warning", value: buckets.warning, color: "#fbbf24" },
    { key: "degraded", label: "Degraded", value: buckets.degraded, color: "#f87171" },
    { key: "unknown", label: "Unknown", value: buckets.unknown, color: "#64748b" },
  ];

  return (
    <KubernetesShell>
      <KubernetesPageHeader
        kicker={localize(lang, "AppOps", "AppOps")}
        title={localize(lang, "Devtron · приложения", "Devtron · applications")}
        description={localize(
          lang,
          "Версии, ownership, health. Deploy/rollback — через approval, не с этой карточки.",
          "Versions, ownership, health. Deploy/rollback via approval — not from this card.",
        )}
        actions={<K8sRefreshButton onClick={refresh} label={localize(lang, "Обновить", "Refresh")} />}
      />

      <QueryStateBlock
        loading={appsQuery.isLoading}
        error={appsQuery.error}
        errorText={localize(lang, "Не удалось загрузить Devtron apps", "Failed to load Devtron apps")}
        onRetry={refresh}
      >
        <div className="grid gap-4 xl:grid-cols-[auto_minmax(0,1fr)]">
          <SectionCard title={localize(lang, "Здоровье apps", "App health")} icon={<Layers3 className="h-4 w-4" />}>
            <div className="flex flex-col items-center gap-4 sm:flex-row">
              <HealthDonut
                slices={slices}
                centerValue={apps.length}
                centerLabel="apps"
              />
              <HealthLegend slices={slices} />
            </div>
          </SectionCard>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiTile label="Apps" value={apps.length} tone="info" />
            <KpiTile label="Healthy" value={buckets.healthy} tone="success" />
            <KpiTile
              label="Issues"
              value={buckets.degraded + buckets.warning}
              tone={buckets.degraded + buckets.warning ? "danger" : "success"}
            />
            <KpiTile label="Teams" value={teams} />
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["all", localize(lang, "Все", "All")],
                ["healthy", "Healthy"],
                ["warning", "Warning"],
                ["degraded", "Degraded"],
              ] as const
            ).map(([id, label]) => (
              <CockpitChip key={id} active={filter === id} onClick={() => setFilter(id)}>
                {label}
              </CockpitChip>
            ))}
          </div>
          <label className="relative block w-full sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={localize(lang, "Поиск app / ns / team…", "Search app / ns / team…")}
              className="h-9 w-full rounded-sm border border-border bg-surface-0 pl-9 pr-3 font-mono text-xs outline-none focus:ring-2 focus:ring-primary/40"
            />
          </label>
        </div>

        <SectionCard
          title={localize(lang, "Приложения", "Applications")}
          description={localize(lang, "Клик → внешний deep link / diagnose с пульта.", "Click → deep link / diagnose from cockpit.")}
          icon={<Layers3 className="h-4 w-4" />}
        >
          {filtered.length ? (
            <div className="space-y-2">
              {filtered.map((app) => (
                <AppRow key={app.id} app={app} lang={lang} onOpenLink={auditDeepLink} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Layers3 className="h-5 w-5" />}
              title={localize(lang, "Devtron apps не найдены", "No Devtron apps")}
              description={localize(
                lang,
                "Синхронизируйте Devtron provider после credentials.",
                "Sync Devtron after credentials are configured.",
              )}
            />
          )}
        </SectionCard>
      </QueryStateBlock>
    </KubernetesShell>
  );
}
