import { useCallback, useMemo, useState } from "react";

import {
  bulkDeleteServerMemorySnapshots,
  createServerKnowledge,
  deleteServerMemorySnapshot,
  deleteServerKnowledge,
  listServerKnowledge,
  listServerMemorySnapshots,
  purgeServerAiMemory,
  updateServerKnowledge,
  updateServerMemorySnapshot,
  type FrontendServer,
  type MemorySnapshotItem,
} from "@/lib/api";

import {
  matchesKnowledgeQuery,
  memorySnapshotAudienceKind,
  memorySnapshotAudienceLabel,
} from "./memorySnapshots";
import type { KnowledgeCategoryOption, KnowledgeItem, UserKnowledgeFilter } from "./types";

type Translate = (key: string) => string;
type TranslateWithVars = (key: string, vars?: Record<string, string | number>) => string;
type KnowledgeConfirmDialog = {
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => Promise<void>;
};

export function useServerKnowledgeController(
  activeServer: FrontendServer | null,
  t: Translate,
  tr: TranslateWithVars,
) {
  const [knowledge, setKnowledge] = useState<KnowledgeItem[]>([]);
  const [aiKnowledge, setAiKnowledge] = useState<MemorySnapshotItem[]>([]);
  const [knowledgeCategories, setKnowledgeCategories] = useState<KnowledgeCategoryOption[]>([]);
  const [knowledgeDialogOpen, setKnowledgeDialogOpen] = useState(false);
  const [knowledgeDialogSaving, setKnowledgeDialogSaving] = useState(false);
  const [knowledgeEditingId, setKnowledgeEditingId] = useState<number | null>(null);
  const [knowledgeTitle, setKnowledgeTitle] = useState("");
  const [knowledgeContent, setKnowledgeContent] = useState("");
  const [knowledgeCategory, setKnowledgeCategory] = useState("other");
  const [knowledgeActive, setKnowledgeActive] = useState(true);
  const [knowledgeSearch, setKnowledgeSearch] = useState("");
  const [aiKnowledgeKindFilter, setAiKnowledgeKindFilter] = useState<UserKnowledgeFilter>("all");
  const [knowledgeDeletingId, setKnowledgeDeletingId] = useState<number | null>(null);
  const [knowledgeBulkDeleting, setKnowledgeBulkDeleting] = useState(false);
  const [knowledgeConfirmDialog, setKnowledgeConfirmDialog] = useState<KnowledgeConfirmDialog | null>(null);

  const [aiKnowledgeDialogOpen, setAiKnowledgeDialogOpen] = useState(false);
  const [aiKnowledgeDialogSaving, setAiKnowledgeDialogSaving] = useState(false);
  const [aiKnowledgeEditingId, setAiKnowledgeEditingId] = useState<number | null>(null);
  const [aiKnowledgeTitle, setAiKnowledgeTitle] = useState("");
  const [aiKnowledgeContent, setAiKnowledgeContent] = useState("");
  const [aiKnowledgeDeletingId, setAiKnowledgeDeletingId] = useState<number | null>(null);
  const [aiKnowledgeBulkDeleting, setAiKnowledgeBulkDeleting] = useState(false);
  const [aiMemoryPurging, setAiMemoryPurging] = useState(false);

  const manualKnowledge = useMemo(
    () => (knowledge ?? []).filter((item) => item.source === "manual"),
    [knowledge],
  );
  const autoKnowledge = useMemo(
    () => (aiKnowledge ?? []).filter((item) => item.kind !== "manual_note"),
    [aiKnowledge],
  );
  const normalizedKnowledgeSearch = useMemo(
    () => knowledgeSearch.trim().toLowerCase(),
    [knowledgeSearch],
  );
  const filteredManualKnowledge = useMemo(
    () =>
      manualKnowledge.filter((item) =>
        matchesKnowledgeQuery(
          [item.title, item.content, item.category_label, item.source_label],
          normalizedKnowledgeSearch,
        ),
      ),
    [manualKnowledge, normalizedKnowledgeSearch],
  );
  const filteredAiKnowledge = useMemo(
    () =>
      autoKnowledge.filter((item) => {
        if (aiKnowledgeKindFilter !== "all" && memorySnapshotAudienceKind(item) !== aiKnowledgeKindFilter) {
          return false;
        }
        return matchesKnowledgeQuery(
          [item.title, item.content, memorySnapshotAudienceLabel(item, t)],
          normalizedKnowledgeSearch,
        );
      }),
    [aiKnowledgeKindFilter, autoKnowledge, normalizedKnowledgeSearch, t],
  );
  const activeKnowledgeCategories = useMemo(() => {
    if (knowledgeCategories.length > 0) return knowledgeCategories;
    return [
      { value: "system", label: t("srv.cat_system") },
      { value: "services", label: t("srv.cat_services") },
      { value: "network", label: t("srv.cat_network") },
      { value: "security", label: t("srv.cat_security") },
      { value: "performance", label: t("srv.cat_performance") },
      { value: "storage", label: t("srv.cat_storage") },
      { value: "packages", label: t("srv.cat_packages") },
      { value: "config", label: t("srv.cat_config") },
      { value: "issues", label: t("srv.cat_issues") },
      { value: "solutions", label: t("srv.cat_solutions") },
      { value: "other", label: t("srv.cat_other") },
    ];
  }, [knowledgeCategories, t]);

  const resetKnowledgeDialog = useCallback(() => {
    setKnowledgeEditingId(null);
    setKnowledgeTitle("");
    setKnowledgeContent("");
    setKnowledgeCategory("other");
    setKnowledgeActive(true);
  }, []);

  const resetAiKnowledgeDialog = useCallback(() => {
    setAiKnowledgeEditingId(null);
    setAiKnowledgeTitle("");
    setAiKnowledgeContent("");
  }, []);

  const clearKnowledgeConfirmDialog = useCallback(() => {
    setKnowledgeConfirmDialog(null);
  }, []);

  const resetForAdvancedOpen = useCallback(() => {
    setKnowledgeSearch("");
    setAiKnowledgeKindFilter("all");
    setKnowledgeDialogOpen(false);
    setAiKnowledgeDialogOpen(false);
    clearKnowledgeConfirmDialog();
    resetKnowledgeDialog();
    resetAiKnowledgeDialog();
  }, [clearKnowledgeConfirmDialog, resetAiKnowledgeDialog, resetKnowledgeDialog]);

  const loadForServer = useCallback(async (serverId: number) => {
    const [knowledgeResp, memoryResp] = await Promise.all([
      listServerKnowledge(serverId),
      listServerMemorySnapshots(serverId),
    ]);
    setKnowledge((knowledgeResp?.items ?? []) as KnowledgeItem[]);
    setAiKnowledge((memoryResp?.items ?? []) as MemorySnapshotItem[]);
    setKnowledgeCategories((knowledgeResp?.categories ?? []) as KnowledgeCategoryOption[]);
  }, []);

  const refreshKnowledge = useCallback(async () => {
    if (!activeServer) return;
    await loadForServer(activeServer.id);
  }, [activeServer, loadForServer]);

  const openKnowledgeCreateDialog = useCallback(() => {
    resetKnowledgeDialog();
    setKnowledgeDialogOpen(true);
  }, [resetKnowledgeDialog]);

  const openKnowledgeEditDialog = useCallback((item: KnowledgeItem) => {
    setKnowledgeEditingId(item.id);
    setKnowledgeTitle(item.title);
    setKnowledgeContent(item.content);
    setKnowledgeCategory(item.category || "other");
    setKnowledgeActive(item.is_active);
    setKnowledgeDialogOpen(true);
  }, []);

  const onKnowledgeSave = useCallback(async () => {
    if (!activeServer || !knowledgeTitle.trim() || !knowledgeContent.trim()) return;
    setKnowledgeDialogSaving(true);
    try {
      if (knowledgeEditingId) {
        await updateServerKnowledge(activeServer.id, knowledgeEditingId, {
          title: knowledgeTitle.trim(),
          content: knowledgeContent.trim(),
          category: knowledgeCategory,
          is_active: knowledgeActive,
        });
      } else {
        await createServerKnowledge(activeServer.id, {
          title: knowledgeTitle.trim(),
          content: knowledgeContent.trim(),
          category: knowledgeCategory,
          is_active: knowledgeActive,
        });
      }
      setKnowledgeDialogOpen(false);
      resetKnowledgeDialog();
      await loadForServer(activeServer.id);
    } finally {
      setKnowledgeDialogSaving(false);
    }
  }, [
    activeServer,
    knowledgeActive,
    knowledgeCategory,
    knowledgeContent,
    knowledgeEditingId,
    knowledgeTitle,
    loadForServer,
    resetKnowledgeDialog,
  ]);

  const onKnowledgeDelete = useCallback(async (id: number) => {
    if (!activeServer) return;
    const target = manualKnowledge.find((item) => item.id === id);
    const label = target?.title?.trim() || t("srv.this_entry");

    setKnowledgeConfirmDialog({
      title: tr("srv.delete_knowledge_confirm", { name: label }),
      description: t("srv.delete_knowledge_description"),
      confirmLabel: t("srv.delete"),
      onConfirm: async () => {
        setKnowledgeDeletingId(id);
        try {
          await deleteServerKnowledge(activeServer.id, id);
          if (knowledgeEditingId === id) {
            setKnowledgeDialogOpen(false);
            resetKnowledgeDialog();
          }
          await loadForServer(activeServer.id);
        } finally {
          setKnowledgeDeletingId(null);
        }
      },
    });
  }, [activeServer, knowledgeEditingId, loadForServer, manualKnowledge, resetKnowledgeDialog, t, tr]);

  const onKnowledgeToggle = useCallback(async (item: KnowledgeItem) => {
    if (!activeServer) return;
    await updateServerKnowledge(activeServer.id, item.id, { is_active: !item.is_active });
    await loadForServer(activeServer.id);
  }, [activeServer, loadForServer]);

  const onDeleteFilteredManualKnowledge = useCallback(async () => {
    if (!activeServer || filteredManualKnowledge.length === 0) return;
    const isAllManual = filteredManualKnowledge.length === manualKnowledge.length;

    setKnowledgeConfirmDialog({
      title: isAllManual
        ? tr("srv.delete_manual_all_confirm", { count: filteredManualKnowledge.length })
        : tr("srv.delete_manual_filtered_confirm", { count: filteredManualKnowledge.length }),
      description: t("srv.delete_knowledge_bulk_description"),
      confirmLabel: isAllManual ? t("srv.delete_all") : t("srv.delete_filtered"),
      onConfirm: async () => {
        setKnowledgeBulkDeleting(true);
        try {
          for (const item of filteredManualKnowledge) {
            await deleteServerKnowledge(activeServer.id, item.id);
          }
          if (
            knowledgeEditingId &&
            filteredManualKnowledge.some((item) => item.id === knowledgeEditingId)
          ) {
            setKnowledgeDialogOpen(false);
            resetKnowledgeDialog();
          }
          await loadForServer(activeServer.id);
        } finally {
          setKnowledgeBulkDeleting(false);
        }
      },
    });
  }, [
    activeServer,
    filteredManualKnowledge,
    knowledgeEditingId,
    loadForServer,
    manualKnowledge.length,
    resetKnowledgeDialog,
    t,
    tr,
  ]);

  const openAiKnowledgeEditDialog = useCallback((item: MemorySnapshotItem) => {
    setAiKnowledgeEditingId(item.id);
    setAiKnowledgeTitle(item.title);
    setAiKnowledgeContent(item.content);
    setAiKnowledgeDialogOpen(true);
  }, []);

  const onAiKnowledgeSave = useCallback(async () => {
    if (!activeServer || !aiKnowledgeEditingId || (!aiKnowledgeTitle.trim() && !aiKnowledgeContent.trim())) return;
    setAiKnowledgeDialogSaving(true);
    try {
      await updateServerMemorySnapshot(activeServer.id, aiKnowledgeEditingId, {
        title: aiKnowledgeTitle.trim(),
        content: aiKnowledgeContent.trim(),
      });
      setAiKnowledgeDialogOpen(false);
      resetAiKnowledgeDialog();
      await loadForServer(activeServer.id);
    } finally {
      setAiKnowledgeDialogSaving(false);
    }
  }, [
    activeServer,
    aiKnowledgeContent,
    aiKnowledgeEditingId,
    aiKnowledgeTitle,
    loadForServer,
    resetAiKnowledgeDialog,
  ]);

  const onAiKnowledgeDelete = useCallback(async (item: MemorySnapshotItem) => {
    if (!activeServer) return;
    const label = item.title?.trim() || item.memory_key;

    setKnowledgeConfirmDialog({
      title: tr("srv.delete_ai_note_confirm", { name: label }),
      description: t("srv.delete_ai_note_description"),
      confirmLabel: t("srv.delete"),
      onConfirm: async () => {
        setAiKnowledgeDeletingId(item.id);
        try {
          await deleteServerMemorySnapshot(activeServer.id, item.id);
          if (aiKnowledgeEditingId === item.id) {
            setAiKnowledgeDialogOpen(false);
            resetAiKnowledgeDialog();
          }
          await loadForServer(activeServer.id);
        } finally {
          setAiKnowledgeDeletingId(null);
        }
      },
    });
  }, [activeServer, aiKnowledgeEditingId, loadForServer, resetAiKnowledgeDialog, t, tr]);

  const onDeleteFilteredAiKnowledge = useCallback(async () => {
    if (!activeServer || filteredAiKnowledge.length === 0) return;
    const isAllAi = filteredAiKnowledge.length === autoKnowledge.length;

    const snapshotIds = filteredAiKnowledge.map((item) => item.id);

    setKnowledgeConfirmDialog({
      title: isAllAi
        ? tr("srv.delete_ai_all_confirm", { count: filteredAiKnowledge.length })
        : tr("srv.delete_ai_filtered_confirm", { count: filteredAiKnowledge.length }),
      description: t("srv.delete_ai_bulk_description"),
      confirmLabel: isAllAi ? t("srv.delete_all") : t("srv.delete_filtered"),
      onConfirm: async () => {
        setAiKnowledgeBulkDeleting(true);
        try {
          await bulkDeleteServerMemorySnapshots(activeServer.id, { snapshot_ids: snapshotIds });
          if (aiKnowledgeEditingId && snapshotIds.includes(aiKnowledgeEditingId)) {
            setAiKnowledgeDialogOpen(false);
            resetAiKnowledgeDialog();
          }
          await loadForServer(activeServer.id);
        } finally {
          setAiKnowledgeBulkDeleting(false);
        }
      },
    });
  }, [
    activeServer,
    aiKnowledgeEditingId,
    autoKnowledge.length,
    filteredAiKnowledge,
    loadForServer,
    resetAiKnowledgeDialog,
    t,
    tr,
  ]);

  const onPurgeAiMemory = useCallback(async () => {
    if (!activeServer) return;

    setKnowledgeConfirmDialog({
      title: t("srv.purge_ai_memory_confirm"),
      description: t("srv.purge_ai_memory_description"),
      confirmLabel: t("srv.purge_all"),
      onConfirm: async () => {
        setAiMemoryPurging(true);
        try {
          await purgeServerAiMemory(activeServer.id);
          if (aiKnowledgeEditingId) {
            setAiKnowledgeDialogOpen(false);
            resetAiKnowledgeDialog();
          }
          await loadForServer(activeServer.id);
        } finally {
          setAiMemoryPurging(false);
        }
      },
    });
  }, [activeServer, aiKnowledgeEditingId, loadForServer, resetAiKnowledgeDialog, t]);

  return {
    activeKnowledgeCategories,
    aiKnowledgeBulkDeleting,
    aiKnowledgeContent,
    aiKnowledgeDeletingId,
    aiKnowledgeDialogOpen,
    aiKnowledgeDialogSaving,
    aiKnowledgeEditingId,
    aiKnowledgeKindFilter,
    aiKnowledgeTitle,
    aiMemoryPurging,
    autoKnowledge,
    clearKnowledgeConfirmDialog,
    filteredAiKnowledge,
    filteredManualKnowledge,
    knowledgeActive,
    knowledgeBulkDeleting,
    knowledgeCategory,
    knowledgeConfirmDialog,
    knowledgeContent,
    knowledgeDeletingId,
    knowledgeDialogOpen,
    knowledgeDialogSaving,
    knowledgeEditingId,
    knowledgeSearch,
    knowledgeTitle,
    loadForServer,
    manualKnowledge,
    normalizedKnowledgeSearch,
    onAiKnowledgeDelete,
    onAiKnowledgeSave,
    onDeleteFilteredAiKnowledge,
    onDeleteFilteredManualKnowledge,
    onKnowledgeDelete,
    onKnowledgeSave,
    onKnowledgeToggle,
    onPurgeAiMemory,
    openAiKnowledgeEditDialog,
    openKnowledgeCreateDialog,
    openKnowledgeEditDialog,
    resetAiKnowledgeDialog,
    resetForAdvancedOpen,
    resetKnowledgeDialog,
    setAiKnowledgeContent,
    setAiKnowledgeDialogOpen,
    setAiKnowledgeKindFilter,
    setAiKnowledgeTitle,
    setKnowledgeActive,
    setKnowledgeCategory,
    setKnowledgeContent,
    setKnowledgeDialogOpen,
    setKnowledgeSearch,
    setKnowledgeTitle,
  };
}

export type ServerKnowledgeController = ReturnType<typeof useServerKnowledgeController>;
