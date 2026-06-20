import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  archiveServerMemorySnapshot,
  fetchAuthSession,
  fetchFrontendBootstrap,
  fetchServerMemoryOverview,
  promoteServerMemorySnapshotToNote,
  promoteServerMemorySnapshotToSkill,
  runServerMemoryDreams,
  updateServerMemoryPolicy,
  type ServerMemoryOverviewResponse,
} from "@/api";
import { QueryStateBlock } from "@/components/ui/page-shell";
import { SettingsMemoryPanel } from "../settings-memory/SettingsMemoryPanel";

export default function SettingsMemoryPage() {
  const queryClient = useQueryClient();
  const [selectedMemoryServerId, setSelectedMemoryServerId] = useState<number | null>(null);
  const [memoryDreamRunning, setMemoryDreamRunning] = useState(false);
  const [memoryPolicySaving, setMemoryPolicySaving] = useState(false);
  const [memoryActionKey, setMemoryActionKey] = useState<string | null>(null);
  const [memoryPolicyDraft, setMemoryPolicyDraft] = useState<ServerMemoryOverviewResponse["policy"] | null>(null);

  const { data: authData, isLoading: authLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;

  const { data: frontendBootstrap } = useQuery({
    queryKey: ["settings", "memory", "servers"],
    queryFn: fetchFrontendBootstrap,
    enabled: isAdmin,
    staleTime: 60_000,
  });
  const memoryServers = useMemo(() => frontendBootstrap?.servers || [], [frontendBootstrap?.servers]);

  useEffect(() => {
    if (!isAdmin || selectedMemoryServerId) return;
    const firstServer = memoryServers[0];
    if (firstServer) {
      setSelectedMemoryServerId(firstServer.id);
    }
  }, [isAdmin, memoryServers, selectedMemoryServerId]);

  const {
    data: memoryOverview,
    isLoading: memoryLoading,
    refetch: refetchMemoryOverview,
  } = useQuery({
    queryKey: ["settings", "memory", "overview", selectedMemoryServerId],
    queryFn: () => fetchServerMemoryOverview(selectedMemoryServerId as number),
    enabled: isAdmin && Boolean(selectedMemoryServerId),
    staleTime: 20_000,
  });

  useEffect(() => {
    if (!memoryOverview) return;
    setMemoryPolicyDraft(memoryOverview.policy);
  }, [memoryOverview]);

  const selectedMemoryServer = useMemo(
    () => memoryServers.find((server) => server.id === selectedMemoryServerId) || null,
    [memoryServers, selectedMemoryServerId],
  );

  const refreshMemoryOverview = useCallback(async () => {
    if (!selectedMemoryServerId) return;
    await queryClient.invalidateQueries({ queryKey: ["settings", "memory", "overview", selectedMemoryServerId] });
    await refetchMemoryOverview();
  }, [queryClient, refetchMemoryOverview, selectedMemoryServerId]);

  const onRunMemoryDreams = useCallback(async () => {
    if (!selectedMemoryServerId) return;
    setMemoryDreamRunning(true);
    try {
      await runServerMemoryDreams(selectedMemoryServerId, { job_kind: "hybrid" });
      await refreshMemoryOverview();
    } finally {
      setMemoryDreamRunning(false);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onSaveMemoryPolicy = useCallback(async () => {
    if (!selectedMemoryServerId || !memoryPolicyDraft) return;
    setMemoryPolicySaving(true);
    try {
      await updateServerMemoryPolicy(selectedMemoryServerId, memoryPolicyDraft);
      await refreshMemoryOverview();
    } finally {
      setMemoryPolicySaving(false);
    }
  }, [memoryPolicyDraft, refreshMemoryOverview, selectedMemoryServerId]);

  const onArchiveMemorySnapshot = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`archive:${snapshotId}`);
    try {
      await archiveServerMemorySnapshot(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onPromoteMemorySnapshotToNote = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`note:${snapshotId}`);
    try {
      await promoteServerMemorySnapshotToNote(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onPromoteMemorySnapshotToSkill = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`skill:${snapshotId}`);
    try {
      await promoteServerMemorySnapshotToSkill(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  if (authLoading) {
    return <QueryStateBlock loading>{null}</QueryStateBlock>;
  }

  if (!isAdmin) {
    return <Navigate to="/settings/ai" replace />;
  }

  return (
    <SettingsMemoryPanel
      memoryServers={memoryServers}
      selectedMemoryServerId={selectedMemoryServerId}
      selectedMemoryServer={selectedMemoryServer}
      memoryOverview={memoryOverview}
      memoryLoading={memoryLoading}
      memoryDreamRunning={memoryDreamRunning}
      memoryPolicySaving={memoryPolicySaving}
      memoryActionKey={memoryActionKey}
      memoryPolicyDraft={memoryPolicyDraft}
      onSelectedMemoryServerIdChange={setSelectedMemoryServerId}
      onMemoryPolicyDraftChange={setMemoryPolicyDraft}
      onRefreshMemoryOverview={refreshMemoryOverview}
      onRunMemoryDreams={onRunMemoryDreams}
      onSaveMemoryPolicy={onSaveMemoryPolicy}
      onArchiveMemorySnapshot={onArchiveMemorySnapshot}
      onPromoteMemorySnapshotToNote={onPromoteMemorySnapshotToNote}
      onPromoteMemorySnapshotToSkill={onPromoteMemorySnapshotToSkill}
    />
  );
}
