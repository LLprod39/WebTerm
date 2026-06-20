import { useCallback, useState } from "react";

import {
  createServerGroup,
  deleteServerGroup,
  updateServerGroup,
  type FrontendGroup,
} from "@/lib/api";

import { initialGroupForm } from "./serverForm";
import type { ServerGroupForm } from "./types";

interface UseServerGroupControllerParams {
  reload: () => Promise<void>;
}

export function useServerGroupController({ reload }: UseServerGroupControllerParams) {
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<FrontendGroup | null>(null);
  const [groupDeleteTarget, setGroupDeleteTarget] = useState<FrontendGroup | null>(null);
  const [groupForm, setGroupForm] = useState<ServerGroupForm>(initialGroupForm());
  const [groupSaving, setGroupSaving] = useState(false);

  const closeGroupDialog = useCallback(() => {
    setGroupDialogOpen(false);
    setEditingGroup(null);
    setGroupForm(initialGroupForm());
  }, []);

  const openCreateGroup = useCallback(() => {
    setEditingGroup(null);
    setGroupForm(initialGroupForm());
    setGroupDialogOpen(true);
  }, []);

  const openGroupSettings = useCallback((group: FrontendGroup) => {
    setEditingGroup(group);
    setGroupForm({
      name: group.name,
      description: group.description || "",
      color: group.color || "#3b82f6",
    });
    setGroupDialogOpen(true);
  }, []);

  const requestDeleteGroup = useCallback((group: FrontendGroup) => {
    setGroupDeleteTarget(group);
  }, []);

  const clearGroupDeleteTarget = useCallback(() => {
    setGroupDeleteTarget(null);
  }, []);

  const saveGroup = useCallback(async () => {
    if (!groupForm.name.trim()) return;
    setGroupSaving(true);
    try {
      const payload = {
        name: groupForm.name.trim(),
        description: groupForm.description.trim(),
        color: groupForm.color,
      };
      if (editingGroup?.id) {
        await updateServerGroup(editingGroup.id, payload);
      } else {
        await createServerGroup(payload);
      }
      closeGroupDialog();
      await reload();
    } finally {
      setGroupSaving(false);
    }
  }, [closeGroupDialog, editingGroup?.id, groupForm, reload]);

  const confirmDeleteGroup = useCallback(async () => {
    if (!groupDeleteTarget?.id) return;
    const targetId = groupDeleteTarget.id;
    await deleteServerGroup(targetId);
    if (editingGroup?.id === targetId) {
      closeGroupDialog();
    }
    setGroupDeleteTarget(null);
    await reload();
  }, [closeGroupDialog, editingGroup?.id, groupDeleteTarget, reload]);

  return {
    clearGroupDeleteTarget,
    closeGroupDialog,
    confirmDeleteGroup,
    editingGroup,
    groupDeleteTarget,
    groupDialogOpen,
    groupForm,
    groupSaving,
    openCreateGroup,
    openGroupSettings,
    requestDeleteGroup,
    saveGroup,
    setGroupDialogOpen,
    setGroupForm,
  };
}
