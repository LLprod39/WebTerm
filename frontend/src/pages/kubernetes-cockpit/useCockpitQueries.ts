import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchKubernetesClusterEvents,
  fetchKubernetesClusterNamespaces,
  fetchKubernetesClusterPods,
  fetchKubernetesClusters,
  fetchKubernetesPodLogs,
} from "@/api";
import { filterEventsByNamespace, filterPodsByNamespace, LOG_TAIL } from "./types";

export function useCockpitQueries(clusterId: string, namespace: string, podId: string) {
  const queryClient = useQueryClient();

  const clustersQuery = useQuery({
    queryKey: ["kubernetes", "clusters"],
    queryFn: fetchKubernetesClusters,
    staleTime: 30_000,
  });

  const namespacesQuery = useQuery({
    queryKey: ["kubernetes", "namespaces", clusterId],
    queryFn: () => fetchKubernetesClusterNamespaces(clusterId),
    enabled: Boolean(clusterId),
    staleTime: 20_000,
  });

  const podsQuery = useQuery({
    queryKey: ["kubernetes", "pods", clusterId],
    queryFn: () => fetchKubernetesClusterPods(clusterId),
    enabled: Boolean(clusterId),
    staleTime: 15_000,
  });

  const eventsQuery = useQuery({
    queryKey: ["kubernetes", "events", clusterId],
    queryFn: () => fetchKubernetesClusterEvents(clusterId),
    enabled: Boolean(clusterId),
    staleTime: 15_000,
  });

  const logsQuery = useQuery({
    queryKey: ["kubernetes", "pod-logs", podId, LOG_TAIL],
    queryFn: () => fetchKubernetesPodLogs(podId, LOG_TAIL),
    enabled: Boolean(podId),
    staleTime: 10_000,
  });

  const clusters = clustersQuery.data?.clusters ?? [];
  const namespaces = namespacesQuery.data?.namespaces ?? [];
  const allPods = podsQuery.data?.pods ?? [];
  const allEvents = eventsQuery.data?.events ?? [];

  const pods = useMemo(() => filterPodsByNamespace(allPods, namespace), [allPods, namespace]);
  const events = useMemo(() => filterEventsByNamespace(allEvents, namespace), [allEvents, namespace]);
  const selectedPod = useMemo(() => pods.find((pod) => pod.id === podId) ?? null, [pods, podId]);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["kubernetes", "clusters"] });
    if (clusterId) {
      void queryClient.invalidateQueries({ queryKey: ["kubernetes", "namespaces", clusterId] });
      void queryClient.invalidateQueries({ queryKey: ["kubernetes", "pods", clusterId] });
      void queryClient.invalidateQueries({ queryKey: ["kubernetes", "events", clusterId] });
    }
    if (podId) {
      void queryClient.invalidateQueries({ queryKey: ["kubernetes", "pod-logs", podId, LOG_TAIL] });
    }
  };

  return {
    clustersQuery,
    namespacesQuery,
    podsQuery,
    eventsQuery,
    logsQuery,
    clusters,
    namespaces,
    pods,
    events,
    selectedPod,
    refresh,
  };
}
