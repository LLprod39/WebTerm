import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";

import {
  fetchAdminInsights,
  runAiInsights,
  type AdminInsightsResponse,
} from "@/api/monitoring-insights";
import { EmptyState, QueryStateBlock } from "@/components/ui/page-shell";
import { fetchAuthSession } from "@/lib/api";
import { useI18n, localize } from "@/lib/i18n";

import { CommandBar } from "./CommandBar";
import { FleetMetricsTable } from "./FleetMetricsTable";
import { ForecastTimeline } from "./ForecastTimeline";
import { InsightsRail } from "./InsightsRail";

const INSIGHTS_QUERY_KEY = ["admin", "insights"];

export default function MonitoringInsightsPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const sessionQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isStaff = Boolean(sessionQuery.data?.user?.is_staff);

  const insightsQuery = useQuery({
    queryKey: INSIGHTS_QUERY_KEY,
    queryFn: () => fetchAdminInsights(),
    enabled: isStaff,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const fresh = await fetchAdminInsights(true);
      queryClient.setQueryData<AdminInsightsResponse>(INSIGHTS_QUERY_KEY, fresh);
    } finally {
      setRefreshing(false);
    }
  };

  const [aiRunning, setAiRunning] = useState(false);
  const backendAiRunning = Boolean(insightsQuery.data?.ai?.running);

  // While an AI pass runs in the background, poll until the lock clears.
  useEffect(() => {
    if (!aiRunning && !backendAiRunning) return;
    const timer = window.setInterval(async () => {
      const fresh = await fetchAdminInsights(true);
      queryClient.setQueryData<AdminInsightsResponse>(INSIGHTS_QUERY_KEY, fresh);
      if (!fresh.ai?.running) {
        setAiRunning(false);
      }
    }, 6000);
    return () => window.clearInterval(timer);
  }, [aiRunning, backendAiRunning, queryClient]);

  const handleRunAi = async () => {
    setAiRunning(true);
    try {
      await runAiInsights();
    } catch {
      setAiRunning(false);
    }
  };

  if (sessionQuery.isSuccess && !isStaff) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <EmptyState
          icon={<ShieldAlert className="h-5 w-5" />}
          title={localize(lang, "Только для администраторов", "Admins only")}
          description={localize(
            lang,
            "Раздел «Метрики и прогнозы» доступен пользователям со статусом администратора.",
            "The Metrics & Forecasts section is available to admin users only.",
          )}
        />
      </div>
    );
  }

  const data = insightsQuery.data;
  const summary = data?.summary;

  return (
    <div className="mx-auto flex w-full max-w-[1800px] flex-col px-4 py-4 md:px-5 xl:h-[calc(100dvh-3rem)] xl:min-h-0">
      <QueryStateBlock
        loading={insightsQuery.isLoading || sessionQuery.isLoading}
        error={insightsQuery.error}
        onRetry={() => insightsQuery.refetch()}
      >
        {data && summary ? (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
            <CommandBar
              summary={summary}
              predictions={data.predictions}
              aiFleet={data.ai.fleet}
              generatedAt={data.generated_at}
              cached={Boolean(data.cached)}
              onRefresh={handleRefresh}
              refreshing={refreshing}
              onRunAi={handleRunAi}
              aiBusy={aiRunning || backendAiRunning}
              aiEnabled={data.ai.enabled}
            />

            <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-12">
              <div className="flex min-h-0 flex-col gap-3 xl:col-span-8">
                <ForecastTimeline predictions={data.predictions} />
                <FleetMetricsTable servers={data.servers} className="min-h-[16rem] xl:min-h-0 xl:flex-1" />
              </div>
              <InsightsRail
                data={data}
                aiRunning={aiRunning}
                className="min-h-[20rem] xl:col-span-4 xl:min-h-0"
              />
            </div>
          </div>
        ) : (
          <EmptyState
            title={localize(lang, "Нет данных", "No data")}
            description={localize(
              lang,
              "Запустите run_monitor, чтобы начать сбор расширенных метрик.",
              "Start run_monitor to begin collecting extended metrics.",
            )}
          />
        )}
      </QueryStateBlock>
    </div>
  );
}
