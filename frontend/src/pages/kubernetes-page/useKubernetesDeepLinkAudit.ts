import { useCallback } from "react";

import { recordKubernetesDeepLink, type KubernetesDeepLinkPayload } from "@/api";

export function useKubernetesDeepLinkAudit() {
  return useCallback((payload: KubernetesDeepLinkPayload) => {
    void recordKubernetesDeepLink(payload).catch(() => {
      // Opening the external provider UI should not be blocked by audit telemetry failure.
    });
  }, []);
}
