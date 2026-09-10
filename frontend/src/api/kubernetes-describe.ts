import { api } from "./client";
import { kubeQuery, type KubeData, type ResourceTarget } from "./kubernetes";

export interface ResourceOwner {
  api_version: string;
  kind: string;
  name: string;
  controller: boolean;
}

export interface ResourceCondition {
  type: string;
  status: string;
  reason: string;
  message: string;
  last_transition_time: string;
}

export interface RelatedPod {
  name: string;
  namespace: string;
  phase: string;
  ready: boolean;
  restart_count: number;
  node_name: string;
  pod_ip: string;
  resource_version: string;
}

export interface RelatedController {
  kind: string;
  name: string;
  namespace: string;
  replicas: number | null;
  ready_replicas: number | null;
  available_replicas: number | null;
  owner_references: ResourceOwner[];
  resource_version: string;
}

export interface DescribeAvailability {
  available: boolean;
  requested?: boolean;
  truncated?: boolean;
  redacted?: boolean;
  skipped_reason?: string;
  error?: { code: string; status: number; message: string };
}

export interface RelatedResources<T> extends DescribeAvailability {
  items: T[];
  item_count: number;
  selector_keys?: string[];
  kind?: string;
}

export interface ResourceDescription {
  target: ResourceTarget;
  provider: { id: number; name: string; kind: string };
  cluster: { id: string; name: string; rancher_cluster_id: string };
  summary: {
    identity: {
      api_version: string;
      kind: string;
      namespace: string;
      name: string;
      uid: string;
      resource_version: string;
      generation: number | null;
      creation_timestamp: string;
    };
    metadata: {
      label_keys: string[];
      annotation_keys: string[];
      owner_references: ResourceOwner[];
    };
    spec: {
      replicas: number | null;
      strategy: string;
      selector_keys: string[];
      container_count: number;
      container_names: string[];
      service_type: string;
      ports: {
        name: string;
        protocol: string;
        port: number | null;
        target_port: string | number | null;
      }[];
    };
    status: {
      phase: string;
      reason: string;
      message: string;
      observed_generation: number | null;
      replicas: number | null;
      ready_replicas: number | null;
      available_replicas: number | null;
      updated_replicas: number | null;
      conditions: ResourceCondition[];
      conditions_truncated: boolean;
    };
  };
  events: DescribeAvailability & { events: KubeData[]; event_count: number };
  related: {
    requested: boolean;
    redacted: boolean;
    skipped_reasons: string[];
    pods: RelatedResources<RelatedPod>;
    controllers: RelatedResources<RelatedController>;
  };
  redacted: boolean;
}

export function describeResource(
  cluster: string,
  session: string,
  target: ResourceTarget,
) {
  return api.get<ResourceDescription>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(cluster)}/resources/describe/` +
      kubeQuery({
        session_id: session,
        ...target,
        include_events: true,
        include_related: true,
        event_limit: 50,
      }),
  );
}
