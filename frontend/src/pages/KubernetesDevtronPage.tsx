import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Layers3, RefreshCcw } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchKubernetesDevtronApps } from "@/api";
import { Button } from "@/components/ui/button";
import { EmptyState, MetricCard, MetricGrid, PageHero, PageShell, QueryStateBlock, SectionCard } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { AppRow, metricToneForHealth } from "@/pages/kubernetes-page/kubernetesPageSections";
import { useKubernetesDeepLinkAudit } from "@/pages/kubernetes-page/useKubernetesDeepLinkAudit";

export default function KubernetesDevtronPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const auditDeepLink = useKubernetesDeepLinkAudit();
  const appsQuery = useQuery({
    queryKey: ["kubernetes", "devtron", "apps"],
    queryFn: fetchKubernetesDevtronApps,
    staleTime: 15_000,
  });
  const apps = appsQuery.data?.apps || [];
  const degraded = apps.filter((app) => app.health === "degraded").length;
  const warning = apps.filter((app) => app.health === "warning").length;
  const healthy = apps.filter((app) => app.health === "healthy").length;
  const teams = new Set(apps.map((app) => app.team).filter(Boolean)).size;
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["kubernetes", "devtron", "apps"] });

  return (
    <PageShell width="7xl" className="space-y-5">
      <PageHero
        kicker={localize(lang, "Kubernetes AppOps", "Kubernetes AppOps")}
        title="Devtron applications"
        description={localize(lang, "Read-only Devtron application inventory, team ownership and version status.", "Read-only Devtron application inventory, team ownership, and version status.")}
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
        loading={appsQuery.isLoading}
        error={appsQuery.error}
        errorText={localize(lang, "Не удалось загрузить Devtron apps", "Failed to load Devtron apps")}
        onRetry={refresh}
      >
        <MetricGrid>
          <MetricCard label="Apps" value={apps.length} description={localize(lang, "synced Devtron apps", "synced Devtron apps")} tone="info" icon={<Layers3 className="h-4 w-4" />} />
          <MetricCard label="Healthy" value={healthy} description={localize(lang, "healthy apps", "healthy apps")} tone="success" icon={<Layers3 className="h-4 w-4" />} />
          <MetricCard label="Issues" value={degraded + warning} description={`${warning} warning, ${degraded} degraded`} tone={metricToneForHealth(degraded, warning)} icon={<Layers3 className="h-4 w-4" />} />
          <MetricCard label="Teams" value={teams} description={localize(lang, "with ownership labels", "with ownership labels")} tone="default" icon={<Layers3 className="h-4 w-4" />} />
        </MetricGrid>
        <SectionCard
          title="Devtron apps"
          description={localize(lang, "No deploy, rollback or terminal actions are exposed from this page.", "No deploy, rollback, or terminal actions are exposed from this page.")}
          icon={<Layers3 className="h-4 w-4" />}
        >
          {apps.length ? (
            <div className="space-y-2">
              {apps.map((app) => (
                <AppRow key={app.id} app={app} lang={lang} onOpenLink={auditDeepLink} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Layers3 className="h-5 w-5" />}
              title={localize(lang, "Devtron apps не синхронизированы", "Devtron apps are not synced")}
              description={localize(lang, "Запустите Devtron provider sync после настройки credentials.", "Run Devtron provider sync after credentials are configured.")}
            />
          )}
        </SectionCard>
      </QueryStateBlock>
    </PageShell>
  );
}
