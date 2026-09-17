import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { CockpitMainTab, CockpitUrlState } from "./types";

function readParam(params: URLSearchParams, key: string): string {
  return (params.get(key) || "").trim();
}

function readTab(params: URLSearchParams): CockpitMainTab {
  const raw = readParam(params, "tab");
  if (raw === "events" || raw === "connect") return raw;
  return "pods";
}

export function useCockpitUrlState() {
  const [searchParams, setSearchParams] = useSearchParams();

  const state = useMemo<CockpitUrlState>(
    () => ({
      clusterId: readParam(searchParams, "cluster"),
      namespace: readParam(searchParams, "ns"),
      podId: readParam(searchParams, "pod"),
      tab: readTab(searchParams),
    }),
    [searchParams],
  );

  const patch = useCallback(
    (
      next: Partial<CockpitUrlState>,
      options?: { history?: "replace" | "push"; clearPod?: boolean },
    ) => {
      const history = options?.history ?? "replace";
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          const clusterId = next.clusterId !== undefined ? next.clusterId : readParam(params, "cluster");
          const namespace = next.namespace !== undefined ? next.namespace : readParam(params, "ns");
          let podId = next.podId !== undefined ? next.podId : readParam(params, "pod");
          if (options?.clearPod) podId = "";
          const tab = next.tab !== undefined ? next.tab : readTab(params);

          const write = (key: string, value: string) => {
            if (value) params.set(key, value);
            else params.delete(key);
          };
          write("cluster", clusterId);
          write("ns", namespace);
          write("pod", podId);
          if (tab && tab !== "pods") params.set("tab", tab);
          else params.delete("tab");
          return params;
        },
        { replace: history === "replace" },
      );
    },
    [setSearchParams],
  );

  const setTab = useCallback(
    (tab: CockpitMainTab) => {
      patch({ tab }, { history: "replace" });
    },
    [patch],
  );

  const setCluster = useCallback(
    (clusterId: string) => {
      patch({ clusterId, namespace: "", podId: "" }, { history: "push", clearPod: true });
    },
    [patch],
  );

  const setNamespace = useCallback(
    (namespace: string) => {
      patch({ namespace, podId: "" }, { history: "replace", clearPod: true });
    },
    [patch],
  );

  const setPod = useCallback(
    (podId: string) => {
      patch({ podId }, { history: "replace" });
    },
    [patch],
  );

  return {
    ...state,
    setCluster,
    setNamespace,
    setPod,
    setTab,
    patch,
  };
}
