import { apiFetch } from "@/lib/api";
import type {
  LinuxUiCapabilitiesResponse,
  LinuxUiDiskResponse,
  LinuxUiDockerActionPayload,
  LinuxUiDockerActionResponse,
  LinuxUiDockerLogsResponse,
  LinuxUiDockerResponse,
  LinuxUiLogsResponse,
  LinuxUiNetworkResponse,
  LinuxUiOverviewResponse,
  LinuxUiPackagesResponse,
  LinuxUiProcessActionPayload,
  LinuxUiProcessActionResponse,
  LinuxUiProcessesResponse,
  LinuxUiServiceActionPayload,
  LinuxUiServiceActionResponse,
  LinuxUiServiceLogsResponse,
  LinuxUiServicesResponse,
  LinuxUiSettingsResponse,
} from "./linux-ui-types";

export type * from "./linux-ui-types";

export async function fetchLinuxUiCapabilities(serverId: number) {
  return apiFetch<LinuxUiCapabilitiesResponse>(`/servers/api/${serverId}/ui/capabilities/`);
}

export async function fetchLinuxUiSettings(serverId: number) {
  return apiFetch<LinuxUiSettingsResponse>(`/servers/api/${serverId}/ui/settings/`);
}

export async function fetchLinuxUiOverview(serverId: number) {
  return apiFetch<LinuxUiOverviewResponse>(`/servers/api/${serverId}/ui/overview/`);
}

export async function fetchLinuxUiServices(serverId: number, limit = 120) {
  return apiFetch<LinuxUiServicesResponse>(`/servers/api/${serverId}/ui/services/?limit=${limit}`);
}

export async function fetchLinuxUiServiceLogs(serverId: number, service: string, lines = 80) {
  const params = new URLSearchParams({ service, lines: String(lines) }).toString();
  return apiFetch<LinuxUiServiceLogsResponse>(`/servers/api/${serverId}/ui/services/logs/?${params}`);
}

export async function runLinuxUiServiceAction(serverId: number, payload: LinuxUiServiceActionPayload) {
  return apiFetch<LinuxUiServiceActionResponse>(`/servers/api/${serverId}/ui/services/action/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchLinuxUiProcesses(serverId: number, limit = 80) {
  return apiFetch<LinuxUiProcessesResponse>(`/servers/api/${serverId}/ui/processes/?limit=${limit}`);
}

export async function runLinuxUiProcessAction(serverId: number, payload: LinuxUiProcessActionPayload) {
  return apiFetch<LinuxUiProcessActionResponse>(`/servers/api/${serverId}/ui/processes/action/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchLinuxUiLogs(serverId: number, options?: { source?: string; service?: string; lines?: number }) {
  const params = new URLSearchParams();
  if (options?.source) params.set("source", options.source);
  if (options?.service) params.set("service", options.service);
  if (options?.lines) params.set("lines", String(options.lines));
  const query = params.toString();
  return apiFetch<LinuxUiLogsResponse>(`/servers/api/${serverId}/ui/logs/${query ? `?${query}` : ""}`);
}

export async function fetchLinuxUiDisk(serverId: number) {
  return apiFetch<LinuxUiDiskResponse>(`/servers/api/${serverId}/ui/disk/`);
}

export async function fetchLinuxUiPackages(serverId: number) {
  return apiFetch<LinuxUiPackagesResponse>(`/servers/api/${serverId}/ui/packages/`);
}

export async function fetchLinuxUiDocker(serverId: number) {
  return apiFetch<LinuxUiDockerResponse>(`/servers/api/${serverId}/ui/docker/`);
}

export async function fetchLinuxUiDockerLogs(serverId: number, container: string, lines = 80) {
  const params = new URLSearchParams({ container, lines: String(lines) }).toString();
  return apiFetch<LinuxUiDockerLogsResponse>(`/servers/api/${serverId}/ui/docker/logs/?${params}`);
}

export async function runLinuxUiDockerAction(serverId: number, payload: LinuxUiDockerActionPayload) {
  return apiFetch<LinuxUiDockerActionResponse>(`/servers/api/${serverId}/ui/docker/action/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchLinuxUiNetwork(serverId: number) {
  return apiFetch<LinuxUiNetworkResponse>(`/servers/api/${serverId}/ui/network/`);
}
