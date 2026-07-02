import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";
import {
  fetchKubernetesAdminResourceDetail,
  fetchKubernetesAdminResourceWatch,
  fetchKubernetesAdminResourceYaml,
  fetchKubernetesAdminResources,
} from "@/api/kubernetes-admin";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(async (path: string) => ({ path })),
}));

describe("kubernetes-admin API client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("passes exact resource plural for custom resources", async () => {
    const query = {
      session_id: "session-1",
      api_version: "example.com/v1",
      kind: "Index",
      resource: "indices",
      namespace: "search",
      name: "main",
    };

    await fetchKubernetesAdminResources("cluster_1", query);
    await fetchKubernetesAdminResourceYaml("cluster_1", query);
    await fetchKubernetesAdminResourceDetail("cluster_1", query);
    await fetchKubernetesAdminResourceWatch("cluster_1", query);

    const urls = vi.mocked(apiFetch).mock.calls.map(([url]) => String(url));
    expect(urls).toEqual([
      "/api/kubernetes/admin/clusters/cluster_1/resources/?session_id=session-1&api_version=example.com%2Fv1&kind=Index&resource=indices&namespace=search&name=main",
      "/api/kubernetes/admin/clusters/cluster_1/yaml/?session_id=session-1&api_version=example.com%2Fv1&kind=Index&resource=indices&namespace=search&name=main",
      "/api/kubernetes/admin/clusters/cluster_1/resources/detail/?session_id=session-1&api_version=example.com%2Fv1&kind=Index&resource=indices&namespace=search&name=main",
      "/api/kubernetes/admin/clusters/cluster_1/watch/?session_id=session-1&api_version=example.com%2Fv1&kind=Index&resource=indices&namespace=search&name=main&limit=20&timeout_seconds=10",
    ]);
  });
});
