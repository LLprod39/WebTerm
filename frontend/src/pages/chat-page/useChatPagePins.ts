import { useCallback, useEffect, useState } from "react";
import type { QueryClient } from "@tanstack/react-query";

import { updateAssistantChat, type AssistantChatSession } from "@/api";

import type { PinnedServer, PinnedUser } from "./ComposeCommandPalette";

export type PinnedPlaybook = { id: number; name: string; kind?: string };

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
  const [pinnedPlaybook, setPinnedPlaybookState] = useState<PinnedPlaybook | null>(null);

  // Hydrate pins from session.pinned_context
  useEffect(() => {
    const pinned = activeChat?.pinned_context || {};
    const serversRaw = (pinned.servers || pinned.pinned_servers || []) as Array<{
      id?: number;
      name?: string;
      host?: string;
    }>;
    const usersRaw = (pinned.users || []) as Array<{ id?: number; username?: string }>;
    const playbookRaw = (pinned.playbook || pinned.pinned_playbook) as Partial<PinnedPlaybook> | undefined;
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
    setPinnedPlaybookState(
      playbookRaw?.id && playbookRaw?.name
        ? { id: Number(playbookRaw.id), name: String(playbookRaw.name), kind: playbookRaw.kind ? String(playbookRaw.kind) : undefined }
        : null,
    );
  }, [activeChatId, activeChat?.pinned_context]);

  const persistPins = useCallback(
    async (servers: PinnedServer[], users: PinnedUser[], playbook: PinnedPlaybook | null) => {
      if (!activeChatId) return;
      const pinned_context = {
        ...(activeChat?.pinned_context || {}),
        servers: servers.map((s) => ({ id: s.id, name: s.name, host: s.host || "" })),
        users: users.map((u) => ({ id: u.id, username: u.username })),
        playbook: playbook ? { id: playbook.id, name: playbook.name, kind: playbook.kind || "" } : null,
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
        void persistPins(next, pinnedUsers, pinnedPlaybook);
        return next;
      });
    },
    [persistPins, pinnedPlaybook, pinnedUsers],
  );

  const unpinServer = useCallback(
    (id: number) => {
      setPinnedServers((prev) => {
        const next = prev.filter((p) => p.id !== id);
        void persistPins(next, pinnedUsers, pinnedPlaybook);
        return next;
      });
    },
    [persistPins, pinnedPlaybook, pinnedUsers],
  );

  const unpinUser = useCallback(
    (id: number) => {
      setPinnedUsers((prev) => {
        const next = prev.filter((p) => p.id !== id);
        void persistPins(pinnedServers, next, pinnedPlaybook);
        return next;
      });
    },
    [persistPins, pinnedPlaybook, pinnedServers],
  );

  const setPinnedPlaybook = useCallback(
    (playbook: PinnedPlaybook | null) => {
      setPinnedPlaybookState(playbook);
      void persistPins(pinnedServers, pinnedUsers, playbook);
    },
    [persistPins, pinnedServers, pinnedUsers],
  );

  return {
    pinnedServers,
    pinnedUsers,
    pinServer,
    unpinServer,
    unpinUser,
    pinnedPlaybook,
    setPinnedPlaybook,
  };
}
