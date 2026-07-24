import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  MessageSquare,
  Package,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import {
  createKubernetesActionRequest,
  createKubernetesDiagnosisDraft,
  fetchKubernetesOverview,
  type KubernetesActionRequestRecord,
  type KubernetesAppRef,
} from "@/api";
import { Button } from "@/components/ui/button";
import {
  QueryStateBlock,
  StatusBadge,
} from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { statusTone } from "@/pages/kubernetes-page/kubernetesPageSections";
import { countHealth } from "@/pages/kubernetes-page/KubernetesCockpitPrimitives";
import { KubernetesAgentDrawer } from "@/pages/kubernetes-page/KubernetesAgentDrawer";
import { KubernetesCockpitBody } from "@/pages/kubernetes-page/KubernetesCockpitBody";
import { KubernetesHelmWizard } from "@/pages/kubernetes-page/KubernetesHelmWizard";
import {
  K8sRefreshButton,
  KubernetesPageHeader,
  KubernetesShell,
} from "@/pages/kubernetes-page/KubernetesShell";
import { useKubernetesDeepLinkAudit } from "@/pages/kubernetes-page/useKubernetesDeepLinkAudit";

type FocusFilter = "all" | "problems" | "rollouts";

export default function KubernetesPage() {
  const { lang } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const auditDeepLink = useKubernetesDeepLinkAudit();
  const [diagnosisAppId, setDiagnosisAppId] = useState<string | null>(null);
  const [actionRequestTargetId, setActionRequestTargetId] = useState("");
  const [actionRequestResult, setActionRequestResult] = useState<KubernetesActionRequestRecord | null>(null);
  const [agentPrompt, setAgentPrompt] = useState("");
  const [focus, setFocus] = useState<FocusFilter>("all");
  const [agentOpen, setAgentOpen] = useState(false);
  const [helmOpen, setHelmOpen] = useState(false);

  const overviewQuery = useQuery({
    queryKey: ["kubernetes", "overview"],
    queryFn: fetchKubernetesOverview,
    staleTime: 15_000,
  });
  const data = overviewQuery.data;
  const summary = data?.summary;
  const readiness = data?.readiness;

  const healthItems = useMemo(
    () => [...(data?.workloads || []), ...(data?.apps || [])],
    [data?.workloads, data?.apps],
  );
  const healthBuckets = useMemo(() => countHealth(healthItems), [healthItems]);
  const healthSlices = useMemo(
    () => [
      {
        key: "healthy",
        label: localize(lang, "Healthy", "Healthy"),
        value: healthBuckets.healthy,
        color: "#34d399",
      },
      {
        key: "warning",
        label: localize(lang, "Warning", "Warning"),
        value: healthBuckets.warning,
        color: "#fbbf24",
      },
      {
        key: "degraded",
        label: localize(lang, "Degraded", "Degraded"),
        value: healthBuckets.degraded,
        color: "#f87171",
      },
      {
        key: "unknown",
        label: localize(lang, "Unknown", "Unknown"),
        value: healthBuckets.unknown,
        color: "#64748b",
      },
    ],
    [healthBuckets, lang],
  );

  const problemApps = (data?.apps || []).filter((app) => ["warning", "degraded"].includes(app.health)).slice(0, 6);
  const problemWorkloads = (data?.workloads || [])
    .filter((workload) => ["warning", "degraded"].includes(workload.health))
    .slice(0, 6);
  const attentionRows = [...problemWorkloads, ...problemApps].slice(0, 6);
  const visibleApps = focus === "problems" ? problemApps : data?.apps || [];
  const visibleRollouts =
    focus === "problems"
      ? (data?.fleet_rollouts || []).filter((b) => ["degraded", "paused", "rolling"].includes(String(b.status)))
      : data?.fleet_rollouts || [];

  const refreshOverview = () => queryClient.invalidateQueries({ queryKey: ["kubernetes", "overview"] });

  const diagnosisMutation = useMutation({
    mutationFn: (appId: string) => createKubernetesDiagnosisDraft({ app_id: appId }),
    onMutate: (appId) => setDiagnosisAppId(appId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      navigate(result.target_url || `/studio/drafts?draft=${result.draft.id}`);
    },
    onSettled: () => setDiagnosisAppId(null),
  });

  const freeformDiagnosisMutation = useMutation({
    mutationFn: async (prompt: string) => {
      const firstProblem = attentionRows[0] || (data?.apps || [])[0];
      if (!firstProblem || !String(firstProblem.id || "").startsWith("app_")) {
        throw new Error(
          localize(
            lang,
            "Нет app target для диагностики. Выберите приложение ниже или откройте Agents.",
            "No app target for diagnosis. Pick an app below or open Agents.",
          ),
        );
      }
      // Backend diagnosis draft is app-scoped; free-text is stored in UI history
      // and the draft title/context comes from the selected problem app.
      return createKubernetesDiagnosisDraft({ app_id: firstProblem.id });
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      const url = result.target_url || `/studio/drafts?draft=${result.draft.id}`;
      // Preserve operator intent in query for Studio draft UX if supported later.
      const withPrompt = agentPrompt.trim()
        ? `${url}${url.includes("?") ? "&" : "?"}intent=${encodeURIComponent(agentPrompt.trim().slice(0, 200))}`
        : url;
      navigate(withPrompt);
      setAgentPrompt("");
    },
  });

  const actionRequestMutation = useMutation({
    mutationFn: (app: KubernetesAppRef) =>
      createKubernetesActionRequest({
        action: "k8s.rollout.restart",
        reason: `Operator requested restart approval for ${app.namespace}/${app.name}`,
        target: { workload_id: app.id },
      }),
    onMutate: (app) => {
      setActionRequestTargetId(app.id);
      setActionRequestResult(null);
    },
    onSuccess: (result) => setActionRequestResult(result.request),
    onSettled: () => setActionRequestTargetId(""),
  });

  const totalHealth = healthItems.length || 1;
  const healthyPct = Math.round((healthBuckets.healthy / totalHealth) * 100);
  const sidebarOpen = Boolean(readiness?.ready_for_sidebar);
  const pilotMode = Boolean((readiness as { pilot_sidebar?: boolean } | undefined)?.pilot_sidebar);

  return (
    <KubernetesShell>
      <KubernetesPageHeader
        kicker={localize(lang, "Kubernetes Ops", "Kubernetes Ops")}
        title={localize(lang, "Кластерный пульт", "Cluster cockpit")}
        description={localize(
          lang,
          "Здоровье, проблемы, выкатки, GitOps и агент — без шума. Ручной fix и AI в одном пульте.",
          "Health, issues, rollouts, GitOps and agent — no clutter. Hands-on fix and AI in one cockpit.",
        )}
        meta={
          <StatusBadge
            label={
              overviewQuery.isLoading
                ? localize(lang, "Проверка", "Checking")
                : overviewQuery.error
                  ? localize(lang, "Backend недоступен", "Backend unavailable")
                  : sidebarOpen
                    ? pilotMode
                      ? localize(lang, "Pilot · в меню", "Pilot · in menu")
                      : localize(lang, "В меню", "In menu")
                    : localize(lang, "Sidebar выкл.", "Sidebar off")
            }
            tone={overviewQuery.error ? "danger" : sidebarOpen ? "success" : statusTone(readiness?.status || "not_configured")}
          />
        }
        actions={
          <>
            <Button type="button" variant="outline" size="sm" className="h-10 gap-2" onClick={() => setAgentOpen(true)}>
              <MessageSquare className="h-4 w-4" />
              {localize(lang, "Агент", "Agent")}
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-10 gap-2" onClick={() => setHelmOpen(true)}>
              <Package className="h-4 w-4" />
              Helm
            </Button>
            {readiness?.access_policy?.can_admin_read ? (
              <Button asChild variant="outline" size="sm" className="h-10 gap-2">
                <Link to="/kubernetes/admin">
                  <ShieldCheck className="h-4 w-4" />
                  Admin
                </Link>
              </Button>
            ) : null}
            <Button asChild variant="outline" size="sm" className="h-10 gap-2">
              <Link to="/settings/kubernetes">
                <Settings2 className="h-4 w-4" />
                {localize(lang, "Настройка", "Setup")}
              </Link>
            </Button>
            <K8sRefreshButton onClick={refreshOverview} label={localize(lang, "Обновить", "Refresh")} />
          </>
        }
      />

      <QueryStateBlock
        loading={overviewQuery.isLoading}
        error={
          overviewQuery.error ||
          (!overviewQuery.isLoading && data && !data.success ? new Error("Kubernetes overview failed") : undefined)
        }
        errorText={localize(lang, "Не удалось загрузить Kubernetes overview", "Failed to load Kubernetes overview")}
        onRetry={refreshOverview}
      >
        {summary && readiness && data ? (
          <KubernetesCockpitBody
            lang={lang}
            data={data}
            summary={summary}
            readiness={readiness}
            focus={focus}
            setFocus={setFocus}
            agentPrompt={agentPrompt}
            setAgentPrompt={setAgentPrompt}
            healthBuckets={healthBuckets}
            healthSlices={healthSlices}
            healthyPct={healthyPct}
            attentionRows={attentionRows}
            visibleApps={visibleApps}
            visibleRollouts={visibleRollouts}
            diagnosisAppId={diagnosisAppId}
            actionRequestTargetId={actionRequestTargetId}
            actionRequestResult={actionRequestResult}
            setActionRequestResult={setActionRequestResult}
            setHelmOpen={setHelmOpen}
            auditDeepLink={auditDeepLink}
            freeformDiagnosisMutation={freeformDiagnosisMutation}
            diagnosisMutation={diagnosisMutation}
            actionRequestMutation={actionRequestMutation}
          />
        ) : null}
      </QueryStateBlock>

      <KubernetesAgentDrawer
        open={agentOpen}
        onClose={() => setAgentOpen(false)}
        contextHint={
          data
            ? `clusters=${data.summary?.clusters ?? 0}, apps=${data.summary?.apps ?? 0}, incidents=${data.summary?.incidents ?? 0}`
            : undefined
        }
      />
      <KubernetesHelmWizard open={helmOpen} onClose={() => setHelmOpen(false)} clusters={data?.clusters || []} />
    </KubernetesShell>
  );
}
