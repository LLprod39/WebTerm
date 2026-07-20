import { useEffect, useMemo, useState } from "react";

import type { FrontendServer } from "@/lib/api";

const COLLAPSED_GROUPS_KEY_PREFIX = "webterm.servers.collapsed-groups";

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
  // Groups are expanded by default; only groups the user explicitly collapses are
  // stored, and that choice is remembered across reloads / navigation.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => readCollapsedGroups(userKey));
  const [selectedServerId, setSelectedServerId] = useState<number | null>(null);

  const safeServers = servers ?? [];

  const filtered = useMemo(() => {
    if (!search) return safeServers;
    const q = search.toLowerCase();
    return safeServers.filter((server) => server.name.toLowerCase().includes(q) || server.host.includes(q));
  }, [safeServers, search]);

  const grouped = useMemo(() => {
    const map: Record<string, FrontendServer[]> = {};
    filtered.forEach((server) => {
      (map[server.group_name] ??= []).push(server);
    });
    return map;
  }, [filtered]);

  const onlineCount = useMemo(
    () => safeServers.filter((server) => server.status === "online").length,
    [safeServers],
  );

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
    grouped,
    onlineCount,
    search,
    selectedServerId,
    setSearch,
    toggleGroup,
  };
}
