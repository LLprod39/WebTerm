import { useCallback, useState } from "react";

import {
  createServerShare,
  listServerShares,
  revokeServerShare,
  type FrontendServer,
} from "@/lib/api";

import type { ShareItem } from "./types";

export function useServerSharesController(activeServer: FrontendServer | null) {
  const [shares, setShares] = useState<ShareItem[]>([]);
  const [shareUser, setShareUser] = useState("");
  const [shareContext, setShareContext] = useState(true);
  const [shareExpiresAt, setShareExpiresAt] = useState("");

  const loadForServer = useCallback(async (serverId: number) => {
    const response = await listServerShares(serverId).catch(() => null);
    const nextShares = (response?.shares ?? []) as ShareItem[];
    setShares(nextShares);
    return nextShares;
  }, []);

  const refresh = useCallback(async () => {
    if (!activeServer) return [];
    return loadForServer(activeServer.id);
  }, [activeServer, loadForServer]);

  const createShare = useCallback(async () => {
    if (!activeServer || !shareUser.trim()) return;
    await createServerShare(activeServer.id, {
      user: shareUser.trim(),
      share_context: shareContext,
      can_connect_terminal: true,
      expires_at: shareExpiresAt ? new Date(shareExpiresAt).toISOString() : null,
    });
    setShareUser("");
    setShareExpiresAt("");
    await loadForServer(activeServer.id);
  }, [activeServer, loadForServer, shareContext, shareExpiresAt, shareUser]);

  const revokeShare = useCallback(async (shareId: number) => {
    if (!activeServer) return;
    await revokeServerShare(activeServer.id, shareId);
    await loadForServer(activeServer.id);
  }, [activeServer, loadForServer]);

  return {
    createShare,
    loadForServer,
    refresh,
    revokeShare,
    shareContext,
    shareExpiresAt,
    shares,
    shareUser,
    setShareContext,
    setShareExpiresAt,
    setShareUser,
  };
}

export type ServerSharesController = ReturnType<typeof useServerSharesController>;
