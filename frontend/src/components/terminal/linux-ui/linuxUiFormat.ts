import type { LinuxUiCapabilities } from "@/lib/api";

export function formatUptime(seconds: number | null) {
  if (!seconds || seconds <= 0) return "Нет данных";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days} д ${hours} ч`;
  if (hours > 0) return `${hours} ч ${minutes} мин`;
  return `${minutes} мин`;
}

export function formatMetric(value: number | null, suffix = "", digits = 0) {
  if (value == null || Number.isNaN(value)) return "N/A";
  return `${value.toFixed(digits)}${suffix}`;
}

export function capabilityPills(capabilities: LinuxUiCapabilities | undefined) {
  if (!capabilities) return [];
  return [
    capabilities.commands.systemctl ? "systemctl" : null,
    capabilities.commands.journalctl ? "journalctl" : null,
    capabilities.commands.docker ? "docker" : null,
    capabilities.commands.ss ? "ss" : null,
    capabilities.commands.ip ? "ip" : null,
    capabilities.package_manager ? `pkg:${capabilities.package_manager}` : null,
    capabilities.is_systemd ? "systemd" : null,
  ].filter(Boolean) as string[];
}
