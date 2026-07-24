import { useCallback, useEffect, useState } from "react";
import type { QueryClient } from "@tanstack/react-query";

import { updateAssistantChat, type AssistantChatSession } from "@/api";

import type { PinnedServer, PinnedUser } from "./ComposeCommandPalette";

export function useChatPagePins({
  activeChatId,
  activeChat,
  queryClient,
}: {
  activeChatId: number | null;
  activeChat: AssistantChatSession | undefined;
  queryClient: QueryClient;
}) {
  const [pinnedServers, setPinnedServers] = useState<PinnedServer[]>([]);
  const [pinnedUsers, setPinnedUsers] = useState<PinnedUser[]>([]);

  // Hydrate pins from session.pinned_context
  useEffect(() => {
    const pinned = activeChat?.pinned_context || {};
    const serversRaw = (pinned.servers || pinned.pinned_servers || []) as Array<{
      id?: number;
      name?: string;
      host?: string;
    }>;
    const usersRaw = (pinned.users || []) as Array<{ id?: number; username?: string }>;
    setPinnedServers(
      serversRaw
        .filter((s) => s && s.id && s.name)
        .map((s) => ({ id: Number(s.id), name: String(s.name), host: s.host ? String(s.host) : undefined })),
    );
    setPinnedUsers(
      usersRaw
        .filter((u) => u && u.id && u.username)
        .map((u) => ({ id: Number(u.id), username: String(u.username) })),
    );
  }, [activeChatId, activeChat?.pinned_context]);

  const persistPins = useCallback(
    async (servers: PinnedServer[], users: PinnedUser[]) => {
      if (!activeChatId) return;
      const pinned_context = {
        ...(activeChat?.pinned_context || {}),
        servers: servers.map((s) => ({ id: s.id, name: s.name, host: s.host || "" })),
        users: users.map((u) => ({ id: u.id, username: u.username })),
      };
      try {
        const updated = await updateAssistantChat(activeChatId, { pinned_context });
        queryClient.setQueryData(["assistant", "chat", activeChatId], (prev: AssistantChatSession | undefined) =>
          prev ? { ...prev, pinned_context: updated.pinned_context } : prev,
        );
      } catch {
        // best-effort — local chips still work for the message text
      }
    },
    [activeChatId, activeChat?.pinned_context, queryClient],
  );

  const pinServer = useCallback(
    (server: PinnedServer) => {
      setPinnedServers((prev) => {
        if (prev.some((p) => p.id === server.id)) return prev;
        const next = [...prev, server];
        void persistPins(next, pinnedUsers);
        return next;
      });
    },
    [persistPins, pinnedUsers],
  );

  const unpinServer = useCallback(
    (id: number) => {
      setPinnedServers((prev) => {
        const next = prev.filter((p) => p.id !== id);
        void persistPins(next, pinnedUsers);
        return next;
      });
    },
    [persistPins, pinnedUsers],
  );

  const unpinUser = useCallback(
    (id: number) => {
      setPinnedUsers((prev) => {
        const next = prev.filter((p) => p.id !== id);
        void persistPins(pinnedServers, next);
        return next;
      });
    },
    [persistPins, pinnedServers],
  );

  return {
    pinnedServers,
    pinnedUsers,
    pinServer,
    unpinServer,
    unpinUser,
  };
}
