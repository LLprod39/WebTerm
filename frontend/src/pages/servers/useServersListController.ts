import { useEffect, useMemo, useState } from "react";

import type { FrontendServer } from "@/lib/api";

const COLLAPSED_GROUPS_KEY_PREFIX = "webterm.servers.collapsed-groups";
const ALL_GROUPS = "__all_groups__";
const UNGROUPED = "__ungrouped__";

function groupFilterValue(groupName: string) {
  return groupName.trim() ? groupName : UNGROUPED;
}

function storageKeyFor(userKey?: string) {
  return userKey ? `${COLLAPSED_GROUPS_KEY_PREFIX}.${userKey}` : COLLAPSED_GROUPS_KEY_PREFIX;
}

/** Load the persisted collapsed-groups map for this user (empty = all expanded). */
function readCollapsedGroups(userKey?: string): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(storageKeyFor(userKey));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object") return {};
    const out: Record<string, boolean> = {};
    for (const [group, value] of Object.entries(parsed)) {
      if (typeof value === "boolean") out[group] = value;
    }
    return out;
  } catch {
    return {};
  }
}

export function useServersListController(servers: FrontendServer[], userKey?: string) {
  const [search, setSearch] = useState("");
  const [groupFilter, setGroupFilter] = useState(ALL_GROUPS);
  // Groups are expanded by default; only groups the user explicitly collapses are
  // stored, and that choice is remembered across reloads / navigation.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => readCollapsedGroups(userKey));
  const [selectedServerId, setSelectedServerId] = useState<number | null>(null);

  const safeServers = servers;

  const groupOptions = useMemo(() => {
    const groups = new Set(safeServers.map((server) => server.group_name || ""));
    return Array.from(groups)
      .sort((left, right) => left.localeCompare(right))
      .map((groupName) => ({
        label: groupName,
        value: groupFilterValue(groupName),
      }));
  }, [safeServers]);

  const filtered = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return safeServers.filter((server) => {
      if (groupFilter !== ALL_GROUPS && groupFilterValue(server.group_name || "") !== groupFilter) {
        return false;
      }
      if (!query) return true;
      return [
        server.name,
        server.host,
        server.username,
        server.group_name,
        server.detected_os,
        server.detected_os_pretty,
      ].some((value) => String(value || "").toLocaleLowerCase().includes(query));
    });
  }, [groupFilter, safeServers, search]);

  const grouped = useMemo(() => {
    const map: Record<string, FrontendServer[]> = {};
    filtered.forEach((server) => {
      (map[server.group_name] ??= []).push(server);
    });
    return map;
  }, [filtered]);

  const toggleGroup = (groupName: string) => {
    setCollapsed((current) => ({ ...current, [groupName]: !current[groupName] }));
  };

  // Re-load the remembered state when the signed-in user changes (login / switch).
  useEffect(() => {
    setCollapsed(readCollapsedGroups(userKey));
  }, [userKey]);

  // Persist collapse choices so a reload or navigation keeps groups the way the
  // user left them (collapsed groups stay collapsed until they expand again).
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(storageKeyFor(userKey), JSON.stringify(collapsed));
    } catch {
      // ignore quota / disabled storage
    }
  }, [collapsed, userKey]);

  useEffect(() => {
    if (!filtered.length) {
      setSelectedServerId(null);
      return;
    }
    if (!selectedServerId || !filtered.some((server) => server.id === selectedServerId)) {
      setSelectedServerId(filtered[0].id);
    }
  }, [filtered, selectedServerId]);

  return {
    collapsed,
    filtered,
    groupFilter,
    groupOptions,
    grouped,
    search,
    selectedServerId,
    setGroupFilter,
    setSearch,
    toggleGroup,
  };
}
