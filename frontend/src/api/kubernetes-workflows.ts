import { api } from "./client";
import { kubeQuery, type KubeData } from "./kubernetes";
export interface KubeRequest {
  id: string;
  action: string;
  status: string;
  risk_tier: string;
  cluster: string;
  target: KubeData;
  preview: KubeData;
  execution_policy: KubeData;
  report: KubeData;
  reason: string;
  approval_ref: string;
  requested_by: string;
  created_at: string;
  updated_at: string;
}
const base = "/api/kubernetes/";
export const kubeWorkflows = {
  requests: (all = false, status = "") =>
    api.get<{ requests: KubeRequest[]; count: number; limit: number }>(
      base + "actions/" + kubeQuery({ all, status, limit: 100 }),
    ),
  request: (id: string) =>
    api.get<{ request: KubeRequest }>(
      base + `actions/${encodeURIComponent(id)}/status/`,
    ),
  report: (id: string) =>
    api.get<KubeData>(base + `actions/${encodeURIComponent(id)}/report/`),
  create: (action: string, target: KubeData, reason: string) =>
    api.post<{ request: KubeRequest }>(base + "actions/request-approval/", {
      action,
      target,
      reason,
    }),
  approve: (id: string, body: KubeData) =>
    api.post<{ request: KubeRequest }>(
      base + `actions/${encodeURIComponent(id)}/approve-external/`,
      body,
    ),
  verify: (id: string, body: KubeData) =>
    api.post<{ request: KubeRequest }>(
      base + `actions/${encodeURIComponent(id)}/verify-external/`,
      body,
    ),
  execute: (id: string, body: KubeData) =>
    api.post<{ request: KubeRequest }>(base + "actions/execute-approved/", {
      ...body,
      request_id: id,
    }),
  delivery: (kind: "helm" | "fleet" | "devtron", cluster = "") =>
    api.get<KubeData>(
      base +
        {
          helm: "helm/releases/",
          fleet: "fleet/bundles/",
          devtron: "devtron/apps/",
        }[kind] +
        kubeQuery({ cluster_id: cluster, limit: 100 }),
    ),
  deliveryDetail: (kind: "fleet" | "devtron", id: string) =>
    api.get<KubeData>(
      base +
        `${kind}/${kind === "fleet" ? "bundles" : "apps"}/${encodeURIComponent(id)}/`,
    ),
  diagnose: (app_id: string) =>
    api.post<{ draft: KubeData }>(base + "actions/diagnose/", { app_id }),
  auditLink: (body: KubeData) =>
    api.post<KubeData>(base + "audit/deeplink/", body),
};
