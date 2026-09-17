import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";

import { fetchAuthSession, fetchSettingsReadiness } from "@/api";
import { hasFeatureAccess } from "@/lib/featureAccess";
import {
  hasSeenFirstRunReadiness,
  markFirstRunReadinessSeen,
} from "@/lib/first-run-readiness";
import { localize, useI18n } from "@/lib/i18n";

export function FirstRunReadinessGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { lang } = useI18n();
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const user = authData?.user;
  const shouldCheck = Boolean(
    user?.is_staff
      && hasFeatureAccess(user, "settings")
      && !location.pathname.startsWith("/settings")
      && !hasSeenFirstRunReadiness(user.id),
  );
  const readiness = useQuery({
    queryKey: ["settings", "readiness", "first-run"],
    queryFn: fetchSettingsReadiness,
    enabled: shouldCheck,
    staleTime: 15_000,
    retry: false,
  });

  useEffect(() => {
    if (shouldCheck && readiness.data?.success && readiness.data.status === "ready" && user) {
      markFirstRunReadinessSeen(user.id);
    }
  }, [readiness.data, shouldCheck, user]);

  if (!shouldCheck || readiness.data?.status === "ready") return <>{children}</>;

  if (readiness.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6 text-sm text-muted-foreground" role="status">
        {localize(lang, "Проверяем готовность первого запуска…", "Checking first-run readiness…")}
      </div>
    );
  }

  const next = encodeURIComponent(location.pathname + location.search);
  const degraded = readiness.isError || !readiness.data?.success ? "&degraded=1" : "";
  return <Navigate to={`/settings/readiness?firstRun=1&next=${next}${degraded}`} replace />;
}
