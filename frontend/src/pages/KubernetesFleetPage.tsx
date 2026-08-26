import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Search } from "lucide-react";

import { fetchKubernetesFleetBundles } from "@/api";
import { EmptyState, QueryStateBlock, SectionCard } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { FleetRow } from "@/pages/kubernetes-page/kubernetesPageSections";
import {
  CockpitChip,
  HealthDonut,
  HealthLegend,
  KpiTile,
  WorkloadReadyBar,
} from "@/pages/kubernetes-page/KubernetesCockpitPrimitives";
import {
  K8sRefreshButton,
  KubernetesPageHeader,
  KubernetesShell,
} from "@/pages/kubernetes-page/KubernetesShell";
import { useKubernetesDeepLinkAudit } from "@/pages/kubernetes-page/useKubernetesDeepLinkAudit";

type FleetFilter = "all" | "rolling" | "degraded" | "ready";

export default function KubernetesFleetPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const auditDeepLink = useKubernetesDeepLinkAudit();
  const [filter, setFilter] = useState<FleetFilter>("all");
  const [q, setQ] = useState("");
  const bundlesQuery = useQuery({
    queryKey: ["kubernetes", "fleet", "bundles"],
    queryFn: fetchKubernetesFleetBundles,
    staleTime: 15_000,
  });
  const bundles = useMemo(() => bundlesQuery.data?.bundles || [], [bundlesQuery.data?.bundles]);
  const rolling = bundles.filter((b) => b.status === "rolling").length;
  const degraded = bundles.filter((b) => b.status === "degraded").length;
  const ready = bundles.filter((b) => b.status === "ready").length;
  const paused = bundles.filter((b) => b.status === "paused").length;
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["kubernetes", "fleet", "bundles"] });

  const filtered = useMemo(() => {
    let rows = bundles;
    if (filter !== "all") rows = rows.filter((b) => b.status === filter);
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      rows = rows.filter(
        (b) =>
          b.name.toLowerCase().includes(needle) ||
          b.source.toLowerCase().includes(needle) ||
          b.target.toLowerCase().includes(needle),
      );
    }
    return rows;
  }, [bundles, filter, q]);

  const slices = [
    { key: "ready", label: localize(lang, "Готово", "Ready"), value: ready, color: "#34d399" },
    { key: "rolling", label: localize(lang, "Выкатывается", "Rolling"), value: rolling, color: "#fbbf24" },
    { key: "degraded", label: localize(lang, "Проблемы", "Degraded"), value: degraded, color: "#f87171" },
    { key: "paused", label: localize(lang, "Приостановлено", "Paused"), value: paused, color: "#64748b" },
  ];

  return (
    <KubernetesShell>
      <KubernetesPageHeader
        kicker={localize(lang, "GitOps", "GitOps")}
        title={localize(lang, "Выкатки Fleet", "Fleet rollouts")}
        description={localize(
          lang,
          "Состояние пакетов и целевых кластеров. Только просмотр.",
          "Bundle and target cluster status. Read-only.",
        )}
        actions={<K8sRefreshButton onClick={refresh} label={localize(lang, "Обновить", "Refresh")} />}
      />

      <QueryStateBlock
        loading={bundlesQuery.isLoading}
        error={bundlesQuery.error}
        errorText={localize(lang, "Не удалось загрузить пакеты Fleet", "Failed to load Fleet bundles")}
        onRetry={refresh}
      >
        <div className="grid gap-4 xl:grid-cols-[auto_minmax(0,1fr)]">
          <SectionCard title={localize(lang, "Состояние", "State")} icon={<GitBranch className="h-4 w-4" />}>
            <div className="flex flex-col items-center gap-4 sm:flex-row">
              <HealthDonut
                slices={slices}
                centerValue={bundles.length}
                centerLabel={localize(lang, "пакетов", "bundles")}
              />
              <HealthLegend slices={slices} />
            </div>
          </SectionCard>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiTile label={localize(lang, "Всего", "Total")} value={bundles.length} tone="info" />
            <KpiTile label={localize(lang, "Готово", "Ready")} value={ready} tone="success" />
            <KpiTile label={localize(lang, "Выкатывается", "Rolling")} value={rolling} tone={rolling ? "warning" : "success"} />
            <KpiTile label={localize(lang, "Проблемы", "Degraded")} value={degraded} tone={degraded ? "danger" : "success"} />
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["all", localize(lang, "Все", "All")],
                ["ready", localize(lang, "Готово", "Ready")],
                ["rolling", localize(lang, "Выкатывается", "Rolling")],
                ["degraded", localize(lang, "Проблемы", "Degraded")],
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
              placeholder={localize(lang, "Пакет, источник или кластер", "Bundle, source, or cluster")}
              className="h-9 w-full rounded-sm border border-border bg-surface-0 pl-9 pr-3 font-mono text-xs outline-none focus:ring-2 focus:ring-primary/40"
            />
          </label>
        </div>

        <SectionCard
          title={localize(lang, "Пакеты Fleet", "Fleet bundles")}
          description={localize(lang, "Изменения требуют подтверждения администратора.", "Changes require administrator approval.")}
          icon={<GitBranch className="h-4 w-4" />}
        >
          {filtered.length ? (
            <div className="space-y-3">
              {filtered.map((bundle) => (
                <div key={bundle.id} className="space-y-2 rounded-sm border border-border bg-surface-0 p-3 shadow-elev-1">
                  <FleetRow bundle={bundle} lang={lang} onOpenLink={auditDeepLink} />
                  <WorkloadReadyBar ready={bundle.ready} desired={bundle.desired} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<GitBranch className="h-5 w-5" />}
              title={localize(lang, "Пакеты Fleet не найдены", "No Fleet bundles")}
              description={localize(
                lang,
                "Настройте подключение Rancher/Fleet и запустите синхронизацию.",
                "Configure the Rancher/Fleet connection and run a sync.",
              )}
            />
          )}
        </SectionCard>
      </QueryStateBlock>
    </KubernetesShell>
  );
}
