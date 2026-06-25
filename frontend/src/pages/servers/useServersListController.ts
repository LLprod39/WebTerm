import { useEffect, useMemo, useState } from "react";

import type { FrontendServer } from "@/lib/api";

export function useServersListController(servers: FrontendServer[]) {
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedServerId, setSelectedServerId] = useState<number | null>(null);

  const filtered = useMemo(() => {
    if (!search) return servers;
    const q = search.toLowerCase();
    return servers.filter((server) => server.name.toLowerCase().includes(q) || server.host.includes(q));
  }, [servers, search]);

  const grouped = useMemo(() => {
    const map: Record<string, FrontendServer[]> = {};
    filtered.forEach((server) => {
      (map[server.group_name] ??= []).push(server);
    });
    return map;
  }, [filtered]);

  const onlineCount = useMemo(
    () => servers.filter((server) => server.status === "online").length,
    [servers],
  );

  const toggleGroup = (groupName: string) => {
    setCollapsed((current) => ({ ...current, [groupName]: !current[groupName] }));
  };

  useEffect(() => {
    const entries = Object.entries(grouped);
    if (entries.length <= 1) return;

    setCollapsed((current) => {
      let changed = false;
      const next = { ...current };

      for (const [groupName, groupServers] of entries) {
        if (next[groupName] !== undefined || groupServers.length > 2) continue;
        next[groupName] = true;
        changed = true;
      }

      return changed ? next : current;
    });
  }, [grouped]);

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
