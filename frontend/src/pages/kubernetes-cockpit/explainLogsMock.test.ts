import { describe, expect, it } from "vitest";

import { explainLogsMock } from "@/pages/kubernetes-cockpit/explainLogsMock";
import { filterEventsByNamespace, filterPodsByNamespace } from "@/pages/kubernetes-cockpit/types";
import type { KubernetesClusterEvent, KubernetesPodRef } from "@/api";

function pod(partial: Partial<KubernetesPodRef> & Pick<KubernetesPodRef, "id" | "name" | "namespace">): KubernetesPodRef {
  return {
    database_id: 1,
    cluster_id: "c1",
    cluster_name: "prod",
    environment: "prod",
    health: "healthy",
    phase: "Running",
    node_name: "node-a",
    pod_ip: "10.0.0.1",
    host_ip: "10.0.0.2",
    owner_kind: "ReplicaSet",
    owner_name: "app",
    ready_containers: 1,
    total_containers: 1,
    restart_count: 0,
    images: ["app:1"],
    links: {},
    labels: {},
    last_sync_at: null,
    sync_status: "fresh",
    is_stale: false,
    sync_age_seconds: 1,
    sync_stale_after_seconds: 300,
    ...partial,
  };
}

describe("explainLogsMock", () => {
  it("detects CrashLoop + connection refused with high confidence", () => {
    const result = explainLogsMock(
      {
        podName: "checkout-api",
        namespace: "production",
        phase: "CrashLoopBackOff",
        restartCount: 14,
        lines: [
          "ERROR dial tcp 10.0.4.22:5432: connect: connection refused",
          "Back-off restarting failed container app",
          "Liveness probe failed: HTTP 500",
        ],
      },
      "ru",
    );
    expect(result.confidence).toBe("high");
    expect(result.signals).toEqual(expect.arrayContaining(["CrashLoopBackOff", "connection_refused", "probe_failed"]));
    expect(result.likelyCause.toLowerCase()).toMatch(/tcp|crash|соединен/i);
    expect(result.disclaimer).toMatch(/mock/i);
  });

  it("returns low confidence when log has no markers", () => {
    const result = explainLogsMock(
      {
        podName: "web",
        namespace: "default",
        phase: "Running",
        restartCount: 0,
        lines: ["INFO listening on :8080", "GET /healthz 200"],
      },
      "en",
    );
    expect(result.confidence).toBe("low");
    expect(result.signals).toEqual([]);
  });
});

describe("namespace filters", () => {
  it("filters pods by namespace", () => {
    const pods = [
      pod({ id: "1", name: "a", namespace: "production" }),
      pod({ id: "2", name: "b", namespace: "default" }),
    ];
    expect(filterPodsByNamespace(pods, "production")).toHaveLength(1);
    expect(filterPodsByNamespace(pods, "")).toHaveLength(0);
  });

  it("filters events by namespace and keeps events without namespace", () => {
    const events = [
      { id: "e1", namespace: "production", severity: "warning", reason: "BackOff", message: "x", source: "k8s", username: "", payload: {}, created_at: null },
      { id: "e2", namespace: "default", severity: "info", reason: "Pulled", message: "y", source: "k8s", username: "", payload: {}, created_at: null },
      { id: "e3", severity: "info", reason: "Synced", message: "z", source: "k8s", username: "", payload: {}, created_at: null },
    ] as KubernetesClusterEvent[];
    const filtered = filterEventsByNamespace(events, "production");
    expect(filtered.map((e) => e.id).sort()).toEqual(["e1", "e3"]);
  });
});
