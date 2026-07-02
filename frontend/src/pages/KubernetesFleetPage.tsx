import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, GitBranch, RefreshCcw } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchKubernetesFleetBundles } from "@/api";
import { Button } from "@/components/ui/button";
import { EmptyState, MetricCard, MetricGrid, PageHero, PageShell, QueryStateBlock, SectionCard } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { FleetRow, statusTone } from "@/pages/kubernetes-page/kubernetesPageSections";
import { useKubernetesDeepLinkAudit } from "@/pages/kubernetes-page/useKubernetesDeepLinkAudit";

export default function KubernetesFleetPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const auditDeepLink = useKubernetesDeepLinkAudit();
  const bundlesQuery = useQuery({
    queryKey: ["kubernetes", "fleet", "bundles"],
    queryFn: fetchKubernetesFleetBundles,
    staleTime: 15_000,
  });
  const bundles = bundlesQuery.data?.bundles || [];
  const rolling = bundles.filter((bundle) => bundle.status === "rolling").length;
  const degraded = bundles.filter((bundle) => bundle.status === "degraded").length;
  const ready = bundles.filter((bundle) => bundle.status === "ready").length;
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["kubernetes", "fleet", "bundles"] });

  return (
    <PageShell width="7xl" className="space-y-5">
      <PageHero
        kicker={localize(lang, "Kubernetes GitOps", "Kubernetes GitOps")}
        title="Fleet rollouts"
        description={localize(lang, "Read-only Fleet bundle inventory, rollout status and target readiness.", "Read-only Fleet bundle inventory, rollout status, and target readiness.")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/kubernetes">
                <ArrowLeft className="h-4 w-4" />
                {localize(lang, "Overview", "Overview")}
              </Link>
            </Button>
            <Button variant="outline" size="sm" onClick={refresh}>
              <RefreshCcw className="h-4 w-4" />
              {localize(lang, "Обновить", "Refresh")}
            </Button>
          </div>
        }
      />
      <QueryStateBlock
        loading={bundlesQuery.isLoading}
        error={bundlesQuery.error}
        errorText={localize(lang, "Не удалось загрузить Fleet bundles", "Failed to load Fleet bundles")}
        onRetry={refresh}
      >
        <MetricGrid>
          <MetricCard label="Total" value={bundles.length} description={localize(lang, "synced bundles", "synced bundles")} tone="info" icon={<GitBranch className="h-4 w-4" />} />
          <MetricCard label="Ready" value={ready} description={localize(lang, "ready bundles", "ready bundles")} tone="success" icon={<GitBranch className="h-4 w-4" />} />
          <MetricCard label="Rolling" value={rolling} description={localize(lang, "active rollouts", "active rollouts")} tone={rolling ? "warning" : "default"} icon={<GitBranch className="h-4 w-4" />} />
          <MetricCard label="Degraded" value={degraded} description={localize(lang, "needs attention", "needs attention")} tone={statusTone(degraded ? "degraded" : "healthy") === "danger" ? "danger" : "success"} icon={<GitBranch className="h-4 w-4" />} />
        </MetricGrid>
        <SectionCard
          title="Fleet bundles"
          description={localize(lang, "No write actions are exposed from this page.", "No write actions are exposed from this page.")}
          icon={<GitBranch className="h-4 w-4" />}
        >
          {bundles.length ? (
            <div className="space-y-3">
              {bundles.map((bundle) => (
                <FleetRow key={bundle.id} bundle={bundle} lang={lang} onOpenLink={auditDeepLink} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<GitBranch className="h-5 w-5" />}
              title={localize(lang, "Fleet bundles не синхронизированы", "Fleet bundles are not synced")}
              description={localize(lang, "Запустите Rancher/Fleet provider sync после настройки credentials.", "Run Rancher/Fleet provider sync after credentials are configured.")}
            />
          )}
        </SectionCard>
      </QueryStateBlock>
    </PageShell>
  );
}
