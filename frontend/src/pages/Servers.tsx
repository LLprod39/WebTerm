import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import {
  addServerGroupMember,
  bulkDeleteServerMemorySnapshots,
  clearMasterPassword,
  createServer,
  createServerGroup,
  createServerKnowledge,
  createServerShare,
  deleteServerMemorySnapshot,
  deleteServer,
  deleteServerGroup,
  deleteServerKnowledge,
  executeServerCommand,
  fetchAuthSession,
  fetchFrontendBootstrap,
  fetchMonitoringStatus,
  refreshMonitoringFleet,
  type MonitoringStatusItem,
  fetchServerDetails,
  getGlobalServerContext,
  getGroupServerContext,
  getMasterPasswordStatus,
  listServerKnowledge,
  listServerShares,
  listServerMemorySnapshots,
  purgeServerAiMemory,
  updateServerMemorySnapshot,
  type MemorySnapshotItem,
  revealServerPassword,
  removeServerGroupMember,
  revokeServerShare,
  saveGlobalServerContext,
  saveGroupServerContext,
  setMasterPassword,
  testServer,
  updateServer,
  updateServerGroup,
  updateServerKnowledge,
  type FrontendGroup,
  type FrontendServer,
  type ServerDetailsResponse,
  type ServerGroupRole,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  Terminal,
  Plus,
  Search,
  Server,
  Settings,
  Trash2,
  Sparkles,
  Layers,
  BookOpen,
  Loader2,
  Upload,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogBody,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { PageHero, PageShell, QueryStateBlock } from "@/components/ui/page-shell";
import { formatCommandOutput } from "./servers/formatters";
import {
  matchesKnowledgeQuery,
  memorySnapshotAudienceBadgeClass,
  memorySnapshotAudienceKind,
  memorySnapshotAudienceLabel,
  renderMemorySnapshotContent,
} from "./servers/memorySnapshots";
import { PlaybooksPanel, usePlaybooksPanel } from "./servers/PlaybooksPanel";
import {
  formatScopedRulesPreview,
  getServerEnvironmentVars,
  jsonText,
  mergeEnvironments,
  splitLines,
  toJson,
  toUnknownJson,
  uniqueLines,
} from "./servers/rules";
import { asPayload, initialForm, initialGroupForm } from "./servers/serverForm";
import { ServerGroupDialog } from "./servers/ServerGroupDialog";
import { ServersListTab } from "./servers/ServersListTab";
import type {
  AdvancedTab,
  KnowledgeCategoryOption,
  KnowledgeItem,
  MainTab,
  ServerForm,
  ServerGroupForm,
  ShareItem,
  UserKnowledgeFilter,
} from "./servers/types";

export default function Servers() {
  const { t, lang } = useI18n();
  const tr = useCallback((key: string, vars?: Record<string, string | number>) => {
    let text = t(key);
    if (!vars) return text;

    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }

    return text;
  }, [t]);
  const queryClient = useQueryClient();
  const [advancedTab, setAdvancedTab] = useState<AdvancedTab>("access");
  const [mainTab, setMainTab] = useState<MainTab>("servers");
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedServerId, setSelectedServerId] = useState<number | null>(null);
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<FrontendGroup | null>(null);
  const [groupDeleteTarget, setGroupDeleteTarget] = useState<FrontendGroup | null>(null);
  const [groupForm, setGroupForm] = useState<ServerGroupForm>(initialGroupForm());
  const [groupSaving, setGroupSaving] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingServer, setEditingServer] = useState<FrontendServer | null>(null);
  const [serverDeleteTarget, setServerDeleteTarget] = useState<FrontendServer | null>(null);
  const [form, setForm] = useState<ServerForm>(initialForm());
  const [saving, setSaving] = useState(false);

  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedServer, setAdvancedServer] = useState<FrontendServer | null>(null);
  const [advancedLoading, setAdvancedLoading] = useState(false);

  const [shares, setShares] = useState<ShareItem[]>([]);
  const [shareUser, setShareUser] = useState("");
  const [shareContext, setShareContext] = useState(true);
  const [shareExpiresAt, setShareExpiresAt] = useState("");

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

  const [aiKnowledgeDialogOpen, setAiKnowledgeDialogOpen] = useState(false);
  const [aiKnowledgeDialogSaving, setAiKnowledgeDialogSaving] = useState(false);
  const [aiKnowledgeEditingId, setAiKnowledgeEditingId] = useState<number | null>(null);
  const [aiKnowledgeTitle, setAiKnowledgeTitle] = useState("");
  const [aiKnowledgeContent, setAiKnowledgeContent] = useState("");
  const [aiKnowledgeDeletingId, setAiKnowledgeDeletingId] = useState<number | null>(null);
  const [aiKnowledgeBulkDeleting, setAiKnowledgeBulkDeleting] = useState(false);
  const [aiMemoryPurging, setAiMemoryPurging] = useState(false);

  const [globalRules, setGlobalRules] = useState("");
  const [globalForbidden, setGlobalForbidden] = useState("");
  const [globalRequired, setGlobalRequired] = useState("");
  const [globalEnvJson, setGlobalEnvJson] = useState("{}");
  const [rulesScopeTab, setRulesScopeTab] = useState<"global" | "group">("global");
  const [rulesGroupId, setRulesGroupId] = useState<number | null>(null);
  const [rulesLoading, setRulesLoading] = useState(false);

  const [groupRules, setGroupRules] = useState("");
  const [groupForbidden, setGroupForbidden] = useState("");
  const [groupEnvJson, setGroupEnvJson] = useState("{}");
  const [groupMemberUser, setGroupMemberUser] = useState("");
  const [groupMemberRole, setGroupMemberRole] = useState<ServerGroupRole>("member");
  const [groupRemoveUserId, setGroupRemoveUserId] = useState("");
  const [serverScopeRules, setServerScopeRules] = useState("");
  const [serverScopeNetworkJson, setServerScopeNetworkJson] = useState("{}");
  const [serverScopeDetails, setServerScopeDetails] = useState<ServerDetailsResponse | null>(null);
  const [serverScopeLoading, setServerScopeLoading] = useState(false);

  const [masterPassword, setMasterPasswordText] = useState("");
  const [hasMasterPassword, setHasMasterPassword] = useState(false);
  const [revealedPassword, setRevealedPassword] = useState("");

  const [execCommand, setExecCommand] = useState("hostname");
  const [execResult, setExecResult] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const { data: monitoringStatus } = useQuery({
    queryKey: ["monitoring", "status"],
    queryFn: fetchMonitoringStatus,
    staleTime: 60_000,
    refetchInterval: 90_000,
    refetchIntervalInBackground: true,
  });
  const fleetHealthByServerId = useMemo(() => {
    const map = new Map<number, MonitoringStatusItem>();
    for (const item of monitoringStatus?.servers ?? []) {
      map.set(item.server_id, item);
    }
    return map;
  }, [monitoringStatus]);
  const servers = useMemo(() => data?.servers ?? [], [data?.servers]);
  const playbooksPanel = usePlaybooksPanel({ servers, t, tr, lang });
  const groups = useMemo(() => data?.groups ?? [], [data?.groups]);
  const manageableGroups = useMemo(
    () =>
      groups.filter(
        (group): group is FrontendGroup & { id: number; role: ServerGroupRole } =>
          group.id !== null && Boolean(group.role),
      ),
    [groups],
  );
  const sharedCount = servers.filter((server) => server.is_shared).length;
  const groupCount = manageableGroups.length;
  const isAdmin = authData?.user?.is_staff ?? false;
  const manualKnowledge = useMemo(
    () => knowledge.filter((item) => item.source === "manual"),
    [knowledge],
  );
  const autoKnowledge = useMemo(
    () => aiKnowledge.filter((item) => item.kind !== "manual_note"),
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

  const filtered = useMemo(() => {
    if (!search) return servers;
    const q = search.toLowerCase();
    return servers.filter((s) => s.name.toLowerCase().includes(q) || s.host.includes(q));
  }, [servers, search]);

  const grouped = useMemo(() => {
    const map: Record<string, typeof filtered> = {};
    filtered.forEach((s) => {
      (map[s.group_name] ??= []).push(s);
    });
    return map;
  }, [filtered]);
  const onlineCount = useMemo(
    () => servers.filter((server) => server.status === "online").length,
    [servers],
  );

  const toggleGroup = (g: string) => setCollapsed((c) => ({ ...c, [g]: !c[g] }));

  useEffect(() => {
    if (!filtered.length) {
      setSelectedServerId(null);
      return;
    }
    if (!selectedServerId || !filtered.some((server) => server.id === selectedServerId)) {
      setSelectedServerId(filtered[0].id);
    }
  }, [filtered, selectedServerId]);

  const fleetRefreshRequested = useRef(false);
  useEffect(() => {
    if (!monitoringStatus?.meta?.has_stale || fleetRefreshRequested.current) return;
    fleetRefreshRequested.current = true;
    void refreshMonitoringFleet().then(() => {
      void queryClient.invalidateQueries({ queryKey: ["monitoring", "status"] });
    });
  }, [monitoringStatus?.meta?.has_stale, queryClient]);

  const selectedRulesGroup = useMemo(
    () => manageableGroups.find((group) => group.id === rulesGroupId) ?? null,
    [manageableGroups, rulesGroupId],
  );

  const parsedGlobalEnvironment = useMemo(() => {
    try {
      return { value: toJson(globalEnvJson), error: null as string | null };
    } catch {
      return { value: {} as Record<string, string>, error: t("srv.invalid_json") };
    }
  }, [globalEnvJson, t]);

  const parsedGroupEnvironment = useMemo(() => {
    try {
      return { value: toJson(groupEnvJson), error: null as string | null };
    } catch {
      return { value: {} as Record<string, string>, error: t("srv.invalid_json") };
    }
  }, [groupEnvJson, t]);

  const parsedServerNetworkConfig = useMemo(() => {
    try {
      return { value: toUnknownJson(serverScopeNetworkJson), error: null as string | null };
    } catch {
      return { value: {} as Record<string, unknown>, error: t("srv.invalid_json") };
    }
  }, [serverScopeNetworkJson, t]);

  const globalForbiddenLines = useMemo(() => splitLines(globalForbidden), [globalForbidden]);
  const groupForbiddenLines = useMemo(() => splitLines(groupForbidden), [groupForbidden]);
  const globalRequiredLines = useMemo(() => splitLines(globalRequired), [globalRequired]);
  const effectiveGroupForbidden = useMemo(
    () => uniqueLines([...globalForbiddenLines, ...groupForbiddenLines]),
    [globalForbiddenLines, groupForbiddenLines],
  );
  const effectiveGroupEnvironment = useMemo(
    () => mergeEnvironments(parsedGlobalEnvironment.value, parsedGroupEnvironment.value),
    [parsedGlobalEnvironment.value, parsedGroupEnvironment.value],
  );
  const effectiveServerEnvironment = useMemo(
    () => mergeEnvironments(
      parsedGlobalEnvironment.value,
      parsedGroupEnvironment.value,
      getServerEnvironmentVars(parsedServerNetworkConfig.value),
    ),
    [parsedGlobalEnvironment.value, parsedGroupEnvironment.value, parsedServerNetworkConfig.value],
  );
  const globalRulesPreview = useMemo(
    () => formatScopedRulesPreview([{ label: t("srv.rules_global_badge"), value: globalRules }]) || t("srv.no_rules_configured"),
    [globalRules, t],
  );
  const groupRulesPreview = useMemo(
    () =>
      formatScopedRulesPreview([
        { label: t("srv.rules_global_badge"), value: globalRules },
        { label: selectedRulesGroup ? tr("srv.group_label_name", { name: selectedRulesGroup.name }) : t("srv.rules_group_badge"), value: groupRules },
      ]) || t("srv.no_rules_configured"),
    [globalRules, groupRules, selectedRulesGroup, t, tr],
  );
  const serverRulesPreview = useMemo(
    () =>
      formatScopedRulesPreview([
        { label: t("srv.rules_global_badge"), value: globalRules },
        {
          label: advancedServer?.group_id ? tr("srv.group_label_name", { name: advancedServer.group_name }) : t("srv.rules_group_badge"),
          value: advancedServer?.group_id ? groupRules : "",
        },
        {
          label: advancedServer ? tr("srv.server_label_name", { name: advancedServer.name }) : t("srv.rules_server_badge"),
          value: serverScopeRules,
        },
      ]) || t("srv.no_rules_configured"),
    [advancedServer, globalRules, groupRules, serverScopeRules, t, tr],
  );

  const clearGlobalContextState = useCallback(() => {
    setGlobalRules("");
    setGlobalForbidden("");
    setGlobalRequired("");
    setGlobalEnvJson("{}");
  }, []);

  const applyGlobalContextState = useCallback((context: {
    rules?: string;
    forbidden_commands?: string[];
    required_checks?: string[];
    environment_vars?: Record<string, string>;
  }) => {
    setGlobalRules(context.rules || "");
    setGlobalForbidden((context.forbidden_commands || []).join("\n"));
    setGlobalRequired((context.required_checks || []).join("\n"));
    setGlobalEnvJson(jsonText(context.environment_vars));
  }, []);

  const clearGroupContextState = useCallback(() => {
    setGroupRules("");
    setGroupForbidden("");
    setGroupEnvJson("{}");
  }, []);

  const applyGroupContextState = useCallback((context: {
    rules?: string;
    forbidden_commands?: string[];
    environment_vars?: Record<string, string>;
  }) => {
    setGroupRules(context.rules || "");
    setGroupForbidden((context.forbidden_commands || []).join("\n"));
    setGroupEnvJson(jsonText(context.environment_vars));
  }, []);

  const clearServerScopeState = useCallback(() => {
    setServerScopeDetails(null);
    setServerScopeRules("");
    setServerScopeNetworkJson("{}");
  }, []);

  const applyServerScopeState = useCallback((details: ServerDetailsResponse) => {
    setServerScopeDetails(details);
    setServerScopeRules(details.corporate_context || "");
    setServerScopeNetworkJson(jsonText(details.network_config));
  }, []);

  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ["frontend", "bootstrap"] });
    await queryClient.invalidateQueries({ queryKey: ["settings", "activity"] });
  };

  useEffect(() => {
    if (!manageableGroups.length) {
      setRulesGroupId(null);
      clearGroupContextState();
      return;
    }
    if (!rulesGroupId || !manageableGroups.some((group) => group.id === rulesGroupId)) {
      setRulesGroupId(manageableGroups[0].id);
    }
  }, [clearGroupContextState, manageableGroups, rulesGroupId]);

  useEffect(() => {
    if (mainTab !== "rules") return;

    let cancelled = false;

    const loadRules = async () => {
      setRulesLoading(true);
      try {
        const globalPromise = getGlobalServerContext().catch(() => null);
        const groupPromise =
          rulesScopeTab === "group" && rulesGroupId ? getGroupServerContext(rulesGroupId).catch(() => null) : Promise.resolve(null);
        const [globalCtx, groupCtx] = await Promise.all([globalPromise, groupPromise]);
        if (cancelled) return;

        if (globalCtx) applyGlobalContextState(globalCtx);
        else clearGlobalContextState();

        if (rulesScopeTab === "group") {
          if (groupCtx) applyGroupContextState(groupCtx);
          else clearGroupContextState();
        }
      } finally {
        if (!cancelled) setRulesLoading(false);
      }
    };

    void loadRules();

    return () => {
      cancelled = true;
    };
  }, [
    applyGlobalContextState,
    applyGroupContextState,
    clearGlobalContextState,
    clearGroupContextState,
    mainTab,
    rulesGroupId,
    rulesScopeTab,
  ]);

  const openCreate = () => {
    setEditingServer(null);
    setForm(initialForm());
    setDialogOpen(true);
  };

  const openCreateGroup = () => {
    setEditingGroup(null);
    setGroupForm(initialGroupForm());
    setGroupDialogOpen(true);
  };

  const openGroupSettings = (group: FrontendGroup) => {
    setEditingGroup(group);
    setGroupForm({
      name: group.name,
      description: group.description || "",
      color: group.color || "#3b82f6",
    });
    setGroupDialogOpen(true);
  };

  const requestDeleteGroup = (group: FrontendGroup) => {
    setGroupDeleteTarget(group);
  };

  const openEdit = async (server: FrontendServer) => {
    setEditingServer(server);
    const details = await fetchServerDetails(server.id);
    setForm({
      name: details.name,
      server_type: details.server_type,
      host: details.host,
      port: details.port,
      username: details.username,
      auth_method: details.auth_method,
      key_path: details.key_path || "",
      ssh_private_key: "",
      password: "",
      sudo_auth_mode: details.sudo_auth_mode || "none",
      sudo_password: "",
      tags: details.tags || "",
      notes: details.notes || "",
      group_id: details.group_id,
      is_active: details.is_active,
      ai_read_only: details.ai_read_only ?? false,
    });
    setDialogOpen(true);
  };

  const requestDeleteServer = (server: FrontendServer) => {
    setServerDeleteTarget(server);
  };

  const onSave = async () => {
    setSaving(true);
    try {
      if (editingServer) await updateServer(editingServer.id, asPayload(form));
      else await createServer(asPayload(form));
      setDialogOpen(false);
      await reload();
    } finally {
      setSaving(false);
    }
  };

  const sudoPasswordRequired =
    form.sudo_auth_mode === "stored_password" &&
    !form.sudo_password.trim() &&
    !(editingServer?.has_saved_sudo_password ?? false);

  const handlePrivateKeyFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setForm((s) => ({ ...s, ssh_private_key: text }));
    } catch (error) {
      console.error(error);
      alert(t("srv.private_key_read_error"));
    } finally {
      event.currentTarget.value = "";
    }
  };

  const onDelete = async () => {
    if (!serverDeleteTarget?.id) return;
    const targetId = serverDeleteTarget.id;
    await deleteServer(targetId);
    if (advancedServer?.id === targetId) {
      setAdvancedOpen(false);
      setAdvancedServer(null);
    }
    if (editingServer?.id === targetId) {
      setDialogOpen(false);
      setEditingServer(null);
    }
    setServerDeleteTarget(null);
    await reload();
  };

  const onTest = async (server: FrontendServer) => {
    const result = await testServer(server.id, {});
    if (result.success) {
      alert(tr("srv.connection_success", { name: server.name }));
    } else {
      alert(tr("srv.connection_failed", { error: result.error || t("srv.unknown_error") }));
    }
    await reload();
  };

  const closeGroupDialog = () => {
    setGroupDialogOpen(false);
    setEditingGroup(null);
    setGroupForm(initialGroupForm());
  };

  const onSaveGroup = async () => {
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
  };

  const openGroupRules = (groupId: number) => {
    closeGroupDialog();
    setRulesGroupId(groupId);
    setRulesScopeTab("group");
    setMainTab("rules");
  };

  const onDeleteGroup = async () => {
    if (!groupDeleteTarget?.id) return;
    const targetId = groupDeleteTarget.id;
    await deleteServerGroup(targetId);
    if (editingGroup?.id === targetId) {
      closeGroupDialog();
    }
    setGroupDeleteTarget(null);
    await reload();
  };

  const openAdvanced = async (server: FrontendServer) => {
    const hasGroupRulesAccess = Boolean(server.group_id && manageableGroups.some((group) => group.id === server.group_id));
    setAdvancedServer(server);
    setAdvancedOpen(true);
    setAdvancedLoading(true);
    setAdvancedTab("access");
    setExecResult("");
    setRevealedPassword("");
    setKnowledgeSearch("");
    setAiKnowledgeKindFilter("all");
    setKnowledgeEditingId(null);
    setKnowledgeDialogOpen(false);
    setAiKnowledgeEditingId(null);
    setAiKnowledgeDialogOpen(false);
    setGroupMemberUser("");
    setGroupRemoveUserId("");
    if (hasGroupRulesAccess && server.group_id) {
      setRulesGroupId(server.group_id);
    }
    try {
      const [sharesResp, knowledgeResp, memoryResp, globalCtx, groupCtx, masterStatus, details] = await Promise.all([
        listServerShares(server.id).catch(() => ({ success: false, shares: [] })),
        listServerKnowledge(server.id).catch(() => ({ success: false, items: [], categories: [] })),
        listServerMemorySnapshots(server.id).catch(() => ({ success: false, items: [] })),
        getGlobalServerContext().catch(() => null),
        hasGroupRulesAccess && server.group_id ? getGroupServerContext(server.group_id).catch(() => null) : Promise.resolve(null),
        getMasterPasswordStatus().catch(() => ({ has_master_password: false })),
        fetchServerDetails(server.id).catch(() => null),
      ]);
      setShares(sharesResp.success ? sharesResp.shares : []);
      setKnowledge((knowledgeResp.items || []) as KnowledgeItem[]);
      setAiKnowledge(memoryResp.success ? memoryResp.items : []);
      setKnowledgeCategories((knowledgeResp.categories || []) as KnowledgeCategoryOption[]);
      setHasMasterPassword(Boolean(masterStatus.has_master_password));

      if (globalCtx) applyGlobalContextState(globalCtx);
      else clearGlobalContextState();

      if (groupCtx) applyGroupContextState(groupCtx);
      else clearGroupContextState();

      if (details) applyServerScopeState(details);
      else clearServerScopeState();
    } finally {
      setAdvancedLoading(false);
    }
  };

  const refreshShares = async () => {
    if (!advancedServer) return;
    const resp = await listServerShares(advancedServer.id);
    setShares(resp.shares || []);
  };

  const refreshKnowledge = async () => {
    if (!advancedServer) return;
    const [knowledgeResp, memoryResp] = await Promise.all([
      listServerKnowledge(advancedServer.id),
      listServerMemorySnapshots(advancedServer.id)
    ]);
    setKnowledge((knowledgeResp.items || []) as KnowledgeItem[]);
    setAiKnowledge((memoryResp.success ? memoryResp.items : []) as MemorySnapshotItem[]);
    setKnowledgeCategories((knowledgeResp.categories || []) as KnowledgeCategoryOption[]);
  };

  const onShareCreate = async () => {
    if (!advancedServer || !shareUser.trim()) return;
    await createServerShare(advancedServer.id, {
      user: shareUser.trim(),
      share_context: shareContext,
      can_connect_terminal: true,
      expires_at: shareExpiresAt ? new Date(shareExpiresAt).toISOString() : null,
    });
    setShareUser("");
    setShareExpiresAt("");
    await refreshShares();
  };

  const onShareRevoke = async (shareId: number) => {
    if (!advancedServer) return;
    await revokeServerShare(advancedServer.id, shareId);
    await refreshShares();
  };

  const resetKnowledgeDialog = useCallback(() => {
    setKnowledgeEditingId(null);
    setKnowledgeTitle("");
    setKnowledgeContent("");
    setKnowledgeCategory("other");
    setKnowledgeActive(true);
  }, []);

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

  const onKnowledgeSave = async () => {
    if (!advancedServer || !knowledgeTitle.trim() || !knowledgeContent.trim()) return;
    setKnowledgeDialogSaving(true);
    try {
      if (knowledgeEditingId) {
        await updateServerKnowledge(advancedServer.id, knowledgeEditingId, {
          title: knowledgeTitle.trim(),
          content: knowledgeContent.trim(),
          category: knowledgeCategory,
          is_active: knowledgeActive,
        });
      } else {
        await createServerKnowledge(advancedServer.id, {
          title: knowledgeTitle.trim(),
          content: knowledgeContent.trim(),
          category: knowledgeCategory,
          is_active: knowledgeActive,
        });
      }
      setKnowledgeDialogOpen(false);
      resetKnowledgeDialog();
      await refreshKnowledge();
    } finally {
      setKnowledgeDialogSaving(false);
    }
  };

  const onKnowledgeDelete = async (id: number) => {
    if (!advancedServer) return;
    const target = manualKnowledge.find((item) => item.id === id);
    const label = target?.title?.trim() || t("srv.this_entry");
    if (!confirm(tr("srv.delete_knowledge_confirm", { name: label }))) return;
    setKnowledgeDeletingId(id);
    try {
      await deleteServerKnowledge(advancedServer.id, id);
      if (knowledgeEditingId === id) {
        setKnowledgeDialogOpen(false);
        resetKnowledgeDialog();
      }
      await refreshKnowledge();
    } finally {
      setKnowledgeDeletingId(null);
    }
  };

  const onKnowledgeToggle = async (item: KnowledgeItem) => {
    if (!advancedServer) return;
    await updateServerKnowledge(advancedServer.id, item.id, { is_active: !item.is_active });
    await refreshKnowledge();
  };

  const onDeleteFilteredManualKnowledge = async () => {
    if (!advancedServer || filteredManualKnowledge.length === 0) return;
    const isAllManual = filteredManualKnowledge.length === manualKnowledge.length;
    const confirmed = confirm(
      isAllManual
        ? tr("srv.delete_manual_all_confirm", { count: filteredManualKnowledge.length })
        : tr("srv.delete_manual_filtered_confirm", { count: filteredManualKnowledge.length }),
    );
    if (!confirmed) return;

    setKnowledgeBulkDeleting(true);
    try {
      for (const item of filteredManualKnowledge) {
        await deleteServerKnowledge(advancedServer.id, item.id);
      }
      if (
        knowledgeEditingId &&
        filteredManualKnowledge.some((item) => item.id === knowledgeEditingId)
      ) {
        setKnowledgeDialogOpen(false);
        resetKnowledgeDialog();
      }
      await refreshKnowledge();
    } finally {
      setKnowledgeBulkDeleting(false);
    }
  };

  const resetAiKnowledgeDialog = useCallback(() => {
    setAiKnowledgeEditingId(null);
    setAiKnowledgeTitle("");
    setAiKnowledgeContent("");
  }, []);

  const openAiKnowledgeEditDialog = (item: MemorySnapshotItem) => {
    setAiKnowledgeEditingId(item.id);
    setAiKnowledgeTitle(item.title);
    setAiKnowledgeContent(item.content);
    setAiKnowledgeDialogOpen(true);
  };

  const onAiKnowledgeSave = async () => {
    if (!advancedServer || !aiKnowledgeEditingId || (!aiKnowledgeTitle.trim() && !aiKnowledgeContent.trim())) return;
    setAiKnowledgeDialogSaving(true);
    try {
      await updateServerMemorySnapshot(advancedServer.id, aiKnowledgeEditingId, {
        title: aiKnowledgeTitle.trim(),
        content: aiKnowledgeContent.trim(),
      });
      setAiKnowledgeDialogOpen(false);
      resetAiKnowledgeDialog();
      await refreshKnowledge();
    } finally {
      setAiKnowledgeDialogSaving(false);
    }
  };

  const onAiKnowledgeDelete = async (item: MemorySnapshotItem) => {
    if (!advancedServer) return;
    const label = item.title?.trim() || item.memory_key;
    if (!confirm(tr("srv.delete_ai_note_confirm", { name: label }))) return;

    setAiKnowledgeDeletingId(item.id);
    try {
      await deleteServerMemorySnapshot(advancedServer.id, item.id);
      if (aiKnowledgeEditingId === item.id) {
        setAiKnowledgeDialogOpen(false);
        resetAiKnowledgeDialog();
      }
      await refreshKnowledge();
    } finally {
      setAiKnowledgeDeletingId(null);
    }
  };

  const onDeleteFilteredAiKnowledge = async () => {
    if (!advancedServer || filteredAiKnowledge.length === 0) return;
    const isAllAi = filteredAiKnowledge.length === autoKnowledge.length;
    const confirmed = confirm(
      isAllAi
        ? tr("srv.delete_ai_all_confirm", { count: filteredAiKnowledge.length })
        : tr("srv.delete_ai_filtered_confirm", { count: filteredAiKnowledge.length }),
    );
    if (!confirmed) return;

    const snapshotIds = filteredAiKnowledge.map((item) => item.id);
    setAiKnowledgeBulkDeleting(true);
    try {
      await bulkDeleteServerMemorySnapshots(advancedServer.id, { snapshot_ids: snapshotIds });
      if (aiKnowledgeEditingId && snapshotIds.includes(aiKnowledgeEditingId)) {
        setAiKnowledgeDialogOpen(false);
        resetAiKnowledgeDialog();
      }
      await refreshKnowledge();
    } finally {
      setAiKnowledgeBulkDeleting(false);
    }
  };

  const onPurgeAiMemory = async () => {
    if (!advancedServer) return;
    const confirmed = confirm(t("srv.purge_ai_memory_confirm"));
    if (!confirmed) return;

    setAiMemoryPurging(true);
    try {
      await purgeServerAiMemory(advancedServer.id);
      if (aiKnowledgeEditingId) {
        setAiKnowledgeDialogOpen(false);
        resetAiKnowledgeDialog();
      }
      await refreshKnowledge();
    } finally {
      setAiMemoryPurging(false);
    }
  };

  const onSaveGlobalContext = async () => {
    if (parsedGlobalEnvironment.error) {
      alert(t("srv.invalid_global_json"));
      return;
    }
    await saveGlobalServerContext({
      rules: globalRules,
      forbidden_commands: globalForbidden,
      required_checks: globalRequired,
      environment_vars: parsedGlobalEnvironment.value,
    });
    alert(t("srv.global_context_saved"));
  };

  const onSaveGroupContext = async () => {
    if (!rulesGroupId) return;
    if (parsedGroupEnvironment.error) {
      alert(t("srv.invalid_group_json"));
      return;
    }
    await saveGroupServerContext(rulesGroupId, {
      rules: groupRules,
      forbidden_commands: groupForbidden,
      environment_vars: parsedGroupEnvironment.value,
    });
    alert(t("srv.group_context_saved"));
  };

  const onSaveServerContext = async () => {
    if (!advancedServer) return;
    if (parsedServerNetworkConfig.error) {
      alert(t("srv.invalid_server_network_json"));
      return;
    }

    setServerScopeLoading(true);
    try {
      await updateServer(advancedServer.id, {
        corporate_context: serverScopeRules,
        network_config: parsedServerNetworkConfig.value,
      });
      setServerScopeDetails((current) =>
        current
          ? {
              ...current,
              corporate_context: serverScopeRules,
              network_config: parsedServerNetworkConfig.value,
            }
          : current,
      );
      alert(t("srv.server_override_saved"));
      await reload();
    } finally {
      setServerScopeLoading(false);
    }
  };

  const onAddGroupMember = async () => {
    if (!advancedServer?.group_id || !groupMemberUser.trim()) return;
    await addServerGroupMember(advancedServer.group_id, { user: groupMemberUser.trim(), role: groupMemberRole });
    setGroupMemberUser("");
    alert(t("srv.group_member_updated"));
  };

  const onRemoveGroupMember = async () => {
    if (!advancedServer?.group_id || !groupRemoveUserId.trim()) return;
    const userId = Number(groupRemoveUserId);
    if (!Number.isFinite(userId) || userId <= 0) {
      alert(t("srv.invalid_user_id"));
      return;
    }
    await removeServerGroupMember(advancedServer.group_id, userId);
    setGroupRemoveUserId("");
    alert(t("srv.group_member_removed"));
  };

  const onSetMasterPassword = async () => {
    if (!masterPassword.trim()) return;
    await setMasterPassword(masterPassword.trim());
    setHasMasterPassword(true);
    alert(t("srv.master_pw_saved"));
  };

  const onClearMasterPassword = async () => {
    await clearMasterPassword();
    setHasMasterPassword(false);
    alert(t("srv.master_pw_cleared"));
  };

  const onRevealPassword = async () => {
    if (!advancedServer) return;
    const resp = await revealServerPassword(advancedServer.id, masterPassword.trim());
    if (resp.success) setRevealedPassword(resp.password || "");
    else alert(resp.error || t("srv.reveal_failed"));
  };

  const onExecuteCommand = async () => {
    if (!advancedServer || !execCommand.trim()) return;
    const resp = await executeServerCommand(advancedServer.id, execCommand, "");
    if (resp.success) setExecResult(formatCommandOutput(resp.output));
    else setExecResult(tr("srv.execute_error", { error: resp.error || t("srv.unknown_error") }));
  };

  if (isLoading || error || !data) {
    return (
      <QueryStateBlock
        loading={isLoading}
        error={error || (!isLoading && !data ? new Error(t("srv.error")) : undefined)}
        errorText={t("srv.error")}
        className="p-6"
      >
        {null}
      </QueryStateBlock>
    );
  }

  return (
    <PageShell width="full" className="max-w-[1500px]">
      <PageHero
        kicker="Inventory"
        title={t("srv.title")}
        description={t("srv.groups_description")}
        actions={
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <div className="relative w-full sm:w-auto">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={t("srv.search")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-10 w-full border-border bg-background pl-9 text-sm sm:w-64"
              />
            </div>
            <Button size="sm" className="h-10 gap-1.5 text-sm" onClick={openCreate}>
              <Plus className="h-4 w-4" /> {t("srv.add")}
            </Button>
          </div>
        }
      />

      <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)} className="space-y-3">
        <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto p-1">
          <TabsTrigger value="servers" className="min-h-10 gap-2 px-3">
            <Server className="h-4 w-4" /> {t("srv.list")}
          </TabsTrigger>
          <TabsTrigger value="groups" className="min-h-10 gap-2 px-3">
            <Layers className="h-4 w-4" /> {t("srv.groups")}
          </TabsTrigger>
          <TabsTrigger value="rules" className="min-h-10 gap-2 px-3">
            <Settings className="h-4 w-4" /> {t("srv.rules_tab")}
          </TabsTrigger>
          <TabsTrigger value="playbook" className="min-h-10 gap-2 px-3">
            <BookOpen className="h-4 w-4" /> {t("pb.title")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="servers" className="space-y-3">
          <ServersListTab
            grouped={grouped}
            filteredCount={filtered.length}
            totalServers={servers.length}
            collapsed={collapsed}
            fleetHealthByServerId={fleetHealthByServerId}
            t={t}
            tr={tr}
            lang={lang}
            onToggleGroup={toggleGroup}
            onOpenCreate={openCreate}
            onOpenAdvanced={openAdvanced}
            onOpenEdit={openEdit}
            onRequestDeleteServer={requestDeleteServer}
            onClearSearch={() => setSearch("")}
          />
        </TabsContent>

        <TabsContent value="groups" className="space-y-3">
          <section className="overflow-hidden rounded-lg border border-border bg-card">
            <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-foreground">{t("srv.groups")}</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  {tr("srv.groups_count", { count: groupCount })}
                </p>
              </div>
              <Button size="sm" className="h-10 gap-1.5 self-start sm:self-auto" onClick={openCreateGroup}>
                <Plus className="h-3.5 w-3.5" /> {t("srv.create_group")}
              </Button>
            </div>

            {manageableGroups.length ? (
              <div>
                {manageableGroups.map((group, index) => (
                  <article
                    key={group.id!}
                    className={`flex items-center gap-4 px-4 py-3 hover:bg-secondary/30 transition-colors ${
                      index < manageableGroups.length - 1 ? "border-b border-border/50" : ""
                    }`}
                  >
                    <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border/70 bg-secondary/30">
                      <Layers className="h-4 w-4 text-primary/80" />
                      <span
                        className="absolute bottom-1 right-1 h-2 w-2 rounded-full border border-card"
                        style={{ backgroundColor: group.color }}
                        aria-hidden="true"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{group.name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {group.description || t("srv.group_description_empty")} · {tr("srv.servers_count_value", { count: group.server_count })}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="xs"
                        variant="outline"
                        className="h-9 gap-1.5 border-border hover:border-primary hover:text-primary"
                        onClick={() => openGroupRules(group.id!)}
                      >
                        <Layers className="h-3 w-3" /> {t("srv.rules_tab")}
                      </Button>
                      {group.can_edit && (
                        <Button
                          size="icon"
                          variant="outline"
                          className="h-9 w-9 border-border hover:border-primary hover:text-primary"
                          onClick={() => openGroupSettings(group)}
                          aria-label={`${t("nav.settings")} ${group.name}`}
                          title={t("nav.settings")}
                        >
                          <Settings className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      {group.role === "owner" && (
                        <Button
                          size="icon"
                          variant="destructive"
                          className="h-9 w-9"
                          onClick={() => requestDeleteGroup(group)}
                          aria-label={`${t("srv.delete")} ${group.name}`}
                          title={t("srv.delete")}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="px-4 py-10 text-center">
                <h3 className="text-sm font-medium text-foreground">{t("srv.groups_empty_title")}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{t("srv.groups_empty_text")}</p>
              </div>
            )}
          </section>
        </TabsContent>

        <TabsContent value="rules" className="space-y-3">
          <section className="bg-card border border-border rounded-lg p-5 space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-sm font-semibold text-foreground">{t("srv.rules_tab")}</h2>
                <p className="text-xs text-muted-foreground mt-1">
                  {t("srv.rules_intro")}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="inline-flex items-center rounded-full border border-border px-2 py-1 font-medium text-foreground">{t("srv.rules_global_badge")}</span>
                <span className="inline-flex items-center rounded-full border border-border px-2 py-1 font-medium text-foreground">{t("srv.rules_group_badge")}</span>
                <span className="inline-flex items-center rounded-full border border-border px-2 py-1 font-medium text-foreground">{t("srv.rules_server_badge")}</span>
              </div>
            </div>

            <Tabs value={rulesScopeTab} onValueChange={(value) => setRulesScopeTab(value as "global" | "group")} className="space-y-4">
              <TabsList className="w-full justify-start">
                <TabsTrigger value="global" className="gap-2">
                  <Settings className="h-4 w-4" /> {t("srv.rules_scope_global")}
                </TabsTrigger>
                <TabsTrigger value="group" className="gap-2">
                  <Layers className="h-4 w-4" /> {t("srv.rules_scope_group")}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="global" className="mt-0">
                {rulesLoading ? (
                  <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("loading")}</div>
                ) : (
                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
                    <div className="space-y-4 rounded-lg border border-border p-4">
                      <div>
                        <div className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">{t("srv.scope_global")}</div>
                        <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.rules_default_instructions")}</h3>
                        <p className="text-xs text-muted-foreground mt-1">
                          {t("srv.rules_global_help")}
                        </p>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_field_rules")}</Label>
                        <Textarea
                          className="min-h-28 bg-secondary/50 text-sm"
                          value={globalRules}
                          onChange={(e) => setGlobalRules(e.target.value)}
                          placeholder={t("srv.rules_placeholder_global")}
                        />
                      </div>
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                          <Textarea
                            className="min-h-24 bg-secondary/50 text-sm font-mono"
                            value={globalForbidden}
                            onChange={(e) => setGlobalForbidden(e.target.value)}
                            placeholder={t("srv.rules_placeholder_forbidden")}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.rules_field_checks")}</Label>
                          <Textarea
                            className="min-h-24 bg-secondary/50 text-sm font-mono"
                            value={globalRequired}
                            onChange={(e) => setGlobalRequired(e.target.value)}
                            placeholder={t("srv.rules_placeholder_checks")}
                          />
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_field_env")}</Label>
                        <Textarea
                          className="min-h-20 bg-secondary/50 text-sm font-mono"
                          value={globalEnvJson}
                          onChange={(e) => setGlobalEnvJson(e.target.value)}
                          placeholder={t("srv.rules_placeholder_env")}
                        />
                        {parsedGlobalEnvironment.error && (
                          <p className="text-xs text-destructive">{parsedGlobalEnvironment.error}</p>
                        )}
                      </div>
                      <div className="flex justify-end">
                        <Button size="sm" className="h-8 px-4" onClick={onSaveGlobalContext}>
                          {t("srv.save_global")}
                        </Button>
                      </div>
                    </div>

                    <div className="space-y-4 rounded-lg border border-border bg-secondary/10 p-4">
                      <div>
                        <div className="inline-flex items-center rounded-full bg-secondary px-2.5 py-1 text-[11px] font-medium text-foreground">{t("srv.rules_preview_global_badge")}</div>
                        <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.rules_preview_global_title")}</h3>
                        <p className="text-xs text-muted-foreground mt-1">
                          {t("srv.rules_preview_global_help")}
                        </p>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_field_stack")}</Label>
                        <Textarea className="min-h-44 bg-background text-sm" value={globalRulesPreview} readOnly />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                        <Textarea className="min-h-20 bg-background text-xs font-mono" value={globalForbiddenLines.join("\n") || t("srv.none")} readOnly />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_field_checks")}</Label>
                        <Textarea className="min-h-20 bg-background text-xs font-mono" value={globalRequiredLines.join("\n") || t("srv.none")} readOnly />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.environment")}</Label>
                        <Textarea className="min-h-24 bg-background text-xs font-mono" value={jsonText(parsedGlobalEnvironment.value)} readOnly />
                      </div>
                    </div>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="group" className="mt-0">
                {!manageableGroups.length ? (
                  <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
                    {t("srv.rules_group_empty")}
                  </div>
                ) : rulesLoading ? (
                  <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("loading")}</div>
                ) : (
                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
                    <div className="space-y-4 rounded-lg border border-border p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">{t("srv.scope_group")}</div>
                          <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.rules_group_title")}</h3>
                          <p className="text-xs text-muted-foreground mt-1">
                            {t("srv.rules_group_help")}
                          </p>
                        </div>
                        <div className="min-w-[220px] space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.rules_group_select")}</Label>
                          <select
                            value={rulesGroupId ?? ""}
                            onChange={(e) => setRulesGroupId(e.target.value ? Number(e.target.value) : null)}
                            className="flex h-9 w-full rounded-md border border-input bg-secondary/50 px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                          >
                            {manageableGroups.map((group) => (
                                <option key={group.id!} value={group.id!}>
                                  {group.name}
                                </option>
                              ))}
                          </select>
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_field_rules")}</Label>
                        <Textarea
                          className="min-h-28 bg-secondary/50 text-sm"
                          value={groupRules}
                          onChange={(e) => setGroupRules(e.target.value)}
                          placeholder={t("srv.rules_placeholder_group")}
                        />
                      </div>
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                          <Textarea
                            className="min-h-24 bg-secondary/50 text-sm font-mono"
                            value={groupForbidden}
                            onChange={(e) => setGroupForbidden(e.target.value)}
                            placeholder={t("srv.rules_placeholder_group_command")}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.rules_field_env")}</Label>
                          <Textarea
                            className="min-h-24 bg-secondary/50 text-sm font-mono"
                            value={groupEnvJson}
                            onChange={(e) => setGroupEnvJson(e.target.value)}
                            placeholder={t("srv.rules_placeholder_group_env")}
                          />
                          {parsedGroupEnvironment.error && (
                            <p className="text-xs text-destructive">{parsedGroupEnvironment.error}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex justify-end">
                        <Button size="sm" className="h-8 px-4" onClick={onSaveGroupContext} disabled={!rulesGroupId}>
                          {t("srv.save_group")}
                        </Button>
                      </div>
                    </div>

                    <div className="space-y-4 rounded-lg border border-border bg-secondary/10 p-4">
                      <div>
                        <div className="inline-flex items-center rounded-full bg-secondary px-2.5 py-1 text-[11px] font-medium text-foreground">
                          {t("srv.rules_preview_group_badge")}
                        </div>
                        <h3 className="mt-3 text-sm font-semibold text-foreground">
                          {tr("srv.rules_preview_group_title", { name: selectedRulesGroup?.name || t("srv.selected_group") })}
                        </h3>
                        <p className="text-xs text-muted-foreground mt-1">
                          {t("srv.rules_preview_group_help")}
                        </p>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_field_stack")}</Label>
                        <Textarea className="min-h-44 bg-background text-sm" value={groupRulesPreview} readOnly />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                        <Textarea className="min-h-20 bg-background text-xs font-mono" value={effectiveGroupForbidden.join("\n") || t("srv.none")} readOnly />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.rules_required_inherited")}</Label>
                        <Textarea className="min-h-20 bg-background text-xs font-mono" value={globalRequiredLines.join("\n") || t("srv.none")} readOnly />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.environment")}</Label>
                        <Textarea className="min-h-24 bg-background text-xs font-mono" value={jsonText(effectiveGroupEnvironment)} readOnly />
                      </div>
                    </div>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </section>
        </TabsContent>

        <TabsContent value="playbook" className="space-y-3">
          <PlaybooksPanel {...playbooksPanel} />
        </TabsContent>
      </Tabs>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-2xl flex-col sm:max-h-[90vh]">
          <DialogHeader>
            <DialogTitle>{editingServer ? t("srv.edit_server") : t("srv.create_server")}</DialogTitle>
            <DialogDescription>{t("srv.server_settings")}</DialogDescription>
          </DialogHeader>

          <DialogBody className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 pb-6 sm:px-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5 md:col-span-2">
                <Label className="text-xs text-muted-foreground">{t("srv.name")} *</Label>
                <Input placeholder="e.g. prod-web-01" value={form.name} onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.host")} *</Label>
                <Input placeholder="192.168.1.10" value={form.host} onChange={(e) => setForm((s) => ({ ...s, host: e.target.value }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.port")}</Label>
                <Input type="number" value={form.port} onChange={(e) => setForm((s) => ({ ...s, port: Number(e.target.value) || 22 }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.username")} *</Label>
                <Input placeholder="ubuntu" value={form.username} onChange={(e) => setForm((s) => ({ ...s, username: e.target.value }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.server_type")}</Label>
                <select
                  value={form.server_type}
                  onChange={() => setForm((s) => ({ ...s, server_type: "ssh" }))}
                  className="flex h-10 w-full rounded-md border border-input bg-secondary/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="ssh">SSH</option>
                </select>
              </div>
            </div>

            <div className="border-t border-border pt-4 space-y-4">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.auth_method")}</Label>
                <div className="flex gap-2">
                  {(["password", "key", "key_password"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setForm((s) => ({ ...s, auth_method: m }))}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${form.auth_method === m ? "bg-primary/15 border-primary text-primary" : "bg-secondary/50 border-border text-muted-foreground hover:text-foreground"}`}
                    >
                      {m === "password" ? t("srv.auth_password") : m === "key" ? t("srv.auth_key") : t("srv.auth_key_password")}
                    </button>
                  ))}
                </div>
              </div>

              {form.auth_method !== "password" && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <Label className="text-xs text-muted-foreground">{t("srv.private_key")}</Label>
                    <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-secondary/50 px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary">
                      <Upload className="h-3.5 w-3.5" />
                      {t("srv.private_key_upload")}
                      <input
                        type="file"
                        accept=".key,.pem,.ppk,.txt,text/plain,application/x-pem-file"
                        className="sr-only"
                        onChange={handlePrivateKeyFile}
                      />
                    </label>
                  </div>
                  <Textarea
                    value={form.ssh_private_key}
                    onChange={(e) => setForm((s) => ({ ...s, ssh_private_key: e.target.value }))}
                    placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                    className="min-h-28 bg-secondary/50 font-mono text-xs"
                    spellCheck={false}
                  />
                  <p className="text-xs text-muted-foreground">
                    {form.key_path && !form.ssh_private_key.trim()
                      ? t("srv.private_key_saved_hint")
                      : t("srv.private_key_hint")}
                  </p>
                </div>
              )}
              {form.auth_method !== "key" && (
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.password")}</Label>
                  <Input
                    type="password"
                    placeholder={editingServer ? t("srv.keep_password_placeholder") : ""}
                    value={form.password}
                    onChange={(e) => setForm((s) => ({ ...s, password: e.target.value }))}
                    className="bg-secondary/50"
                  />
                </div>
              )}
            </div>

            <div className="border-t border-border pt-4 space-y-4">
              <div className="flex items-start gap-2">
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                  <ShieldCheck className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <Label className="text-xs text-muted-foreground">{t("srv.sudo_auth")}</Label>
                  <p className="mt-1 text-xs text-muted-foreground">{t("srv.sudo_auth_hint")}</p>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {(["none", "nopasswd", "stored_password"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setForm((s) => ({ ...s, sudo_auth_mode: mode }))}
                    className={`min-h-10 rounded-md border px-3 py-2 text-left text-xs font-medium transition-colors ${form.sudo_auth_mode === mode ? "border-primary bg-primary/15 text-primary" : "border-border bg-secondary/50 text-muted-foreground hover:text-foreground"}`}
                  >
                    {mode === "none" ? t("srv.sudo_none") : mode === "nopasswd" ? t("srv.sudo_nopasswd") : t("srv.sudo_stored")}
                  </button>
                ))}
              </div>
              {form.sudo_auth_mode === "stored_password" && (
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.sudo_password")}</Label>
                  <Input
                    type="password"
                    placeholder={editingServer?.has_saved_sudo_password ? t("srv.keep_sudo_password_placeholder") : ""}
                    value={form.sudo_password}
                    onChange={(e) => setForm((s) => ({ ...s, sudo_password: e.target.value }))}
                    className="bg-secondary/50"
                  />
                  <p className="text-xs text-muted-foreground">{t("srv.sudo_password_hint")}</p>
                </div>
              )}
            </div>

            <div className="border-t border-border pt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.groups")}</Label>
                <select
                  value={form.group_id ?? ""}
                  onChange={(e) => setForm((s) => ({ ...s, group_id: e.target.value ? Number(e.target.value) : null }))}
                  className="flex h-10 w-full rounded-md border border-input bg-secondary/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="">{t("srv.no_group")}</option>
                  {manageableGroups.map((g) => (
                      <option key={g.id!} value={g.id!}>{g.name}</option>
                    ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.tags")}</Label>
                <Input placeholder="web, production" value={form.tags} onChange={(e) => setForm((s) => ({ ...s, tags: e.target.value }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5 md:col-span-2">
                <Label className="text-xs text-muted-foreground">{t("srv.notes")}</Label>
                <Input placeholder="..." value={form.notes} onChange={(e) => setForm((s) => ({ ...s, notes: e.target.value }))} className="bg-secondary/50" />
              </div>
            </div>
          </DialogBody>

          <DialogFooter className="shrink-0 px-4 sm:px-6">
            <Button variant="outline" size="sm" onClick={() => setDialogOpen(false)}>
              {t("srv.cancel")}
            </Button>
            <Button
              size="sm"
              onClick={onSave}
              disabled={
                saving ||
                !form.name ||
                !form.host ||
                !form.username ||
                (form.auth_method !== "password" && !form.key_path && !form.ssh_private_key.trim()) ||
                sudoPasswordRequired
              }
            >
              {saving ? t("srv.saving") : editingServer ? t("srv.update") : t("srv.create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ServerGroupDialog
        open={groupDialogOpen}
        editingGroup={editingGroup}
        groupForm={groupForm}
        groupSaving={groupSaving}
        t={t}
        setGroupDialogOpen={setGroupDialogOpen}
        setGroupForm={setGroupForm}
        closeGroupDialog={closeGroupDialog}
        onSaveGroup={onSaveGroup}
        openGroupRules={openGroupRules}
      />

      <Dialog open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <DialogContent className="flex h-[88vh] max-w-5xl flex-col p-0 sm:h-[85vh]">
          {/* Header */}
          <div className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-4 sm:px-6">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
              <Server className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <DialogTitle className="text-sm font-semibold">{advancedServer?.name || t("srv.server")}</DialogTitle>
              <DialogDescription className="mt-0 text-xs font-mono">
                {advancedServer?.host}:{advancedServer?.port} · {advancedServer?.group_name}
              </DialogDescription>
            </div>
          </div>

          {advancedLoading ? (
            <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              {t("loading")}
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col md:flex-row">
              {/* Sidebar tabs */}
              <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-border bg-secondary/20 p-2 md:block md:w-44 md:border-b-0 md:border-r md:py-2">
                {([
                  { key: "access", icon: <Sparkles className="h-3.5 w-3.5" />, label: t("srv.access") },
                  { key: "knowledge", icon: <Sparkles className="h-3.5 w-3.5" />, label: t("srv.knowledge") },
                  { key: "context", icon: <Layers className="h-3.5 w-3.5" />, label: t("srv.server_rules_tab") },
                  { key: "security", icon: <Settings className="h-3.5 w-3.5" />, label: t("srv.security") },
                  { key: "execute", icon: <Terminal className="h-3.5 w-3.5" />, label: t("srv.execute") },
                ] as const).map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setAdvancedTab(tab.key)}
                    className={`flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs font-medium transition-colors md:w-full md:rounded-none md:px-4 md:py-2.5 ${
                      advancedTab === tab.key
                        ? "bg-primary/10 text-primary md:border-r-2 md:border-primary"
                        : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                    }`}
                  >
                    {tab.icon}
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Content area */}
              <div className="flex-1 overflow-y-auto p-4 sm:p-6">
                {/* ACCESS TAB */}
                {advancedTab === "access" && (
                  <div className="space-y-5">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.server_sharing")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">{t("srv.share_help")}</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.username")}</Label>
                          <Input placeholder={t("srv.username_email_id")} value={shareUser} onChange={(e) => setShareUser(e.target.value)} className="bg-secondary/50 h-9" />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.expires")}</Label>
                          <Input type="datetime-local" value={shareExpiresAt} onChange={(e) => setShareExpiresAt(e.target.value)} className="bg-secondary/50 h-9" />
                        </div>
                      </div>
                      <div className="flex items-center justify-between mt-3">
                        <label className="text-xs flex items-center gap-2 text-muted-foreground">
                          <input type="checkbox" checked={shareContext} onChange={(e) => setShareContext(e.target.checked)} className="rounded" />
                          {t("srv.share_context")}
                        </label>
                        <Button size="sm" className="h-8 px-4" onClick={onShareCreate}>{t("srv.share")}</Button>
                      </div>
                    </div>

                    {shares.length > 0 && (
                      <div className="border-t border-border pt-4">
                        <h4 className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wider">{t("srv.active_shares")}</h4>
                        <div className="space-y-2">
                          {shares.map((s) => (
                            <div key={s.id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-border bg-secondary/10">
                              <div className="h-7 w-7 rounded-full bg-primary/15 flex items-center justify-center text-xs font-medium text-primary shrink-0">
                                {(s.username || "U").slice(0, 1).toUpperCase()}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-foreground truncate">{s.username}</p>
                                <p className="text-xs text-muted-foreground">{s.email || "—"} · {s.is_active ? t("srv.status_active") : t("srv.status_expired")}</p>
                              </div>
                              <Button size="sm" variant="outline" className="h-7 text-xs text-destructive border-destructive/30 hover:bg-destructive/10" onClick={() => onShareRevoke(s.id)}>
                                {t("srv.revoke")}
                              </Button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {advancedServer?.group_id && manageableGroups.some((group) => group.id === advancedServer.group_id) && (
                      <div className="border-t border-border pt-4">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{t("srv.group_access")}</h4>
                            <p className="mt-2 text-sm font-medium text-foreground">{advancedServer.group_name}</p>
                            <p className="text-xs text-muted-foreground mt-1">
                              {t("srv.group_access_help")}
                            </p>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-8"
                            onClick={() => openGroupRules(advancedServer.group_id!)}
                          >
                            {t("srv.open_group_rules")}
                          </Button>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">{t("srv.username_email")}</Label>
                            <Input placeholder="user@example.com" value={groupMemberUser} onChange={(e) => setGroupMemberUser(e.target.value)} className="bg-secondary/50 h-9" />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">{t("srv.role")}</Label>
                            <select
                              value={groupMemberRole}
                              onChange={(e) => setGroupMemberRole(e.target.value as ServerGroupRole)}
                              className="flex h-9 w-full rounded-md border border-input bg-secondary/50 px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                            >
                              <option value="owner">{t("srv.role_owner")}</option>
                              <option value="admin">{t("srv.role_admin")}</option>
                              <option value="member">{t("srv.role_member")}</option>
                              <option value="viewer">{t("srv.role_viewer")}</option>
                            </select>
                          </div>
                          <div className="flex items-end">
                            <Button size="sm" className="h-9 w-full" onClick={onAddGroupMember}>{t("srv.add_member")}</Button>
                          </div>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">{t("srv.remove_by_user_id")}</Label>
                            <Input placeholder={t("srv.user_id_placeholder")} value={groupRemoveUserId} onChange={(e) => setGroupRemoveUserId(e.target.value)} className="bg-secondary/50 h-9" />
                          </div>
                          <div className="flex items-end">
                            <Button size="sm" variant="outline" className="h-9 w-full text-destructive border-destructive/30 hover:bg-destructive/10" onClick={onRemoveGroupMember}>{t("srv.remove_member")}</Button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* KNOWLEDGE TAB */}
                {advancedTab === "knowledge" && (
                  <div className="space-y-5">
                    <div className="rounded-xl border border-border bg-secondary/10 px-4 py-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="space-y-1">
                          <h3 className="text-sm font-semibold text-foreground">{t("srv.knowledge_title")}</h3>
                          <p className="text-xs text-muted-foreground">
                            {t("srv.knowledge_intro")}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Button size="sm" className="h-8 px-4" onClick={openKnowledgeCreateDialog}>
                            {t("srv.add_entry")}
                          </Button>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-xl border border-border bg-card/40 px-4 py-4">
                      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px_auto]">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.knowledge_filter_label")}</Label>
                          <div className="relative">
                            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                            <Input
                              value={knowledgeSearch}
                              onChange={(event) => setKnowledgeSearch(event.target.value)}
                              placeholder={t("srv.knowledge_search_placeholder")}
                              className="h-9 bg-secondary/50 pl-9"
                            />
                          </div>
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.knowledge_kind_label")}</Label>
                          <select
                            value={aiKnowledgeKindFilter}
                            onChange={(event) =>
                              setAiKnowledgeKindFilter(
                                event.target.value as UserKnowledgeFilter,
                              )
                            }
                            className="flex h-9 w-full rounded-md border border-input bg-secondary/50 px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                          >
                            <option value="all">{t("srv.knowledge_filter_all")}</option>
                            <option value="summary">{t("srv.knowledge_filter_summary")}</option>
                            <option value="access">{t("srv.knowledge_filter_access")}</option>
                            <option value="risks">{t("srv.knowledge_filter_risks")}</option>
                            <option value="changes">{t("srv.knowledge_filter_changes")}</option>
                            <option value="instructions">{t("srv.knowledge_filter_instructions")}</option>
                          </select>
                        </div>
                        <div className="flex items-end">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-9 w-full"
                            onClick={() => {
                              setKnowledgeSearch("");
                              setAiKnowledgeKindFilter("all");
                            }}
                          >
                            {t("srv.reset_filters")}
                          </Button>
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                        <span className="rounded-full border border-border px-2.5 py-1">
                          {tr("srv.manual_count", { filtered: filteredManualKnowledge.length, total: manualKnowledge.length })}
                        </span>
                        <span className="rounded-full border border-border px-2.5 py-1">
                          {tr("srv.ai_count", { filtered: filteredAiKnowledge.length, total: autoKnowledge.length })}
                        </span>
                        {normalizedKnowledgeSearch ? (
                          <span className="rounded-full border border-border px-2.5 py-1">
                            {tr("srv.search_term", { query: knowledgeSearch.trim() })}
                          </span>
                        ) : null}
                      </div>
                    </div>

                    {manualKnowledge.length > 0 ? (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between gap-3">
                        <div>
                          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                            {tr("srv.manual_entries_count", { filtered: filteredManualKnowledge.length, total: manualKnowledge.length })}
                          </h4>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                              {t("srv.manual_entries_help")}
                          </p>
                        </div>
                          {filteredManualKnowledge.length > 0 ? (
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-3 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                              onClick={() => void onDeleteFilteredManualKnowledge()}
                              disabled={knowledgeBulkDeleting}
                            >
                              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                              {knowledgeBulkDeleting
                                ? t("srv.saving")
                                : filteredManualKnowledge.length === manualKnowledge.length
                                  ? t("srv.delete_all")
                                  : t("srv.delete_filtered")}
                            </Button>
                          ) : null}
                        </div>
                        {filteredManualKnowledge.length > 0 ? (
                          <div className="space-y-2">
                            {filteredManualKnowledge.map((item) => (
                              <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <p className="text-sm font-medium text-foreground">{item.title}</p>
                                      <span
                                        className={`rounded px-1.5 py-0.5 text-[10px] ${
                                          item.is_active
                                            ? "bg-primary/15 text-primary"
                                            : "bg-secondary text-muted-foreground"
                                        }`}
                                      >
                                        {item.category_label}
                                      </span>
                                      {item.updated_at ? (
                                        <span className="text-[10px] text-muted-foreground">
                                          {new Date(item.updated_at).toLocaleString()}
                                        </span>
                                      ) : null}
                                    </div>
                                    <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                                      {item.content}
                                    </p>
                                  </div>
                                  <div className="flex flex-wrap gap-2 lg:justify-end">
                                    <Button size="sm" variant="outline" className="h-7 px-3 text-xs" onClick={() => onKnowledgeToggle(item)}>
                                      {item.is_active ? t("srv.disable") : t("srv.enable")}
                                    </Button>
                                    <Button size="sm" variant="outline" className="h-7 px-3 text-xs" onClick={() => openKnowledgeEditDialog(item)}>
                                      {t("srv.edit")}
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="h-7 px-3 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                                      onClick={() => void onKnowledgeDelete(item.id)}
                                      disabled={knowledgeDeletingId === item.id || knowledgeBulkDeleting}
                                    >
                                      {knowledgeDeletingId === item.id ? t("srv.saving") : t("srv.delete")}
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center">
                            <p className="text-sm font-medium text-foreground">{t("srv.manual_empty_filtered_title")}</p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {t("srv.manual_empty_filtered_text")}
                            </p>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center">
                        <p className="text-sm font-medium text-foreground">{t("srv.manual_empty_title")}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {t("srv.manual_empty_text")}
                        </p>
                        <Button size="sm" className="mt-4 h-8 px-4" onClick={openKnowledgeCreateDialog}>
                          {t("srv.add_entry")}
                        </Button>
                      </div>
                    )}

                    {/* AI KNOWLEDGE SECTION */}
                    <div className="space-y-3 mt-6 border-t border-border pt-6">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                            {tr("srv.ai_entries_count", { filtered: filteredAiKnowledge.length, total: autoKnowledge.length })}
                          </h4>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            {t("srv.ai_entries_help")}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center justify-end gap-2">
                          {filteredAiKnowledge.length > 0 ? (
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-3 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                              onClick={() => void onDeleteFilteredAiKnowledge()}
                              disabled={aiKnowledgeBulkDeleting || aiMemoryPurging}
                            >
                              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                              {aiKnowledgeBulkDeleting
                                ? t("srv.saving")
                                : filteredAiKnowledge.length === autoKnowledge.length
                                  ? t("srv.delete_all")
                                  : t("srv.delete_filtered")}
                            </Button>
                          ) : null}
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-3 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                            onClick={() => void onPurgeAiMemory()}
                            disabled={aiKnowledgeBulkDeleting || aiMemoryPurging}
                          >
                            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                            {aiMemoryPurging ? t("srv.saving") : t("srv.purge_all")}
                          </Button>
                        </div>
                      </div>
                      {filteredAiKnowledge.length > 0 ? (
                        <div className="space-y-2">
                          {filteredAiKnowledge.map((item) => (
                            <div key={item.id} className="rounded-lg border border-border bg-card px-3 py-3 shadow-sm">
                              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                <div className="min-w-0 flex-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <p className="text-sm font-medium text-foreground">{item.title}</p>
                                    <span
                                      className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${memorySnapshotAudienceBadgeClass(item)}`}
                                    >
                                      {memorySnapshotAudienceLabel(item, t)}
                                    </span>
                                    {item.updated_at ? (
                                      <span className="text-[10px] text-muted-foreground">
                                        {new Date(item.updated_at).toLocaleString()}
                                      </span>
                                    ) : null}
                                  </div>
                                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap max-h-[180px] overflow-y-auto custom-scrollbar">
                                    {renderMemorySnapshotContent(item)}
                                  </p>
                                </div>
                                <div className="flex flex-wrap gap-2 lg:justify-end">
                                  <Button size="sm" variant="outline" className="h-7 px-3 text-xs flex-shrink-0" onClick={() => openAiKnowledgeEditDialog(item)}>
                                    {t("srv.edit")}
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 px-3 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                                    onClick={() => void onAiKnowledgeDelete(item)}
                                    disabled={aiKnowledgeDeletingId === item.id || aiKnowledgeBulkDeleting || aiMemoryPurging}
                                  >
                                    {aiKnowledgeDeletingId === item.id ? t("srv.saving") : t("srv.delete")}
                                  </Button>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center">
                          <p className="text-sm font-medium text-foreground">
                            {autoKnowledge.length > 0 ? t("srv.ai_empty_filtered_title") : t("srv.ai_empty_title")}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {autoKnowledge.length > 0
                              ? t("srv.ai_empty_filtered_text")
                              : t("srv.ai_empty_text")}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* CONTEXT TAB */}
                {advancedTab === "context" && (
                  <div className="space-y-6">
                    <div className="rounded-lg border border-border p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">{t("srv.scope_server")}</span>
                            <span className="inline-flex items-center rounded-full bg-secondary px-2.5 py-1 text-[11px] font-medium text-foreground">
                              {advancedServer?.group_id ? t("srv.inherits_global_group") : t("srv.inherits_global")}
                            </span>
                          </div>
                          <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.server_override_title")}</h3>
                          <p className="text-xs text-muted-foreground mt-1">
                            {t("srv.server_override_help")}
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8"
                          onClick={() => {
                            if (advancedServer?.group_id && manageableGroups.some((group) => group.id === advancedServer.group_id)) {
                              setRulesGroupId(advancedServer.group_id);
                              setRulesScopeTab("group");
                            } else {
                              setRulesScopeTab("global");
                            }
                            setMainTab("rules");
                            setAdvancedOpen(false);
                          }}
                        >
                          {t("srv.open_inherited_rules")}
                        </Button>
                      </div>
                    </div>

                    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(340px,0.95fr)]">
                      <div className="space-y-4 rounded-lg border border-border p-4">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.server_rules_label")}</Label>
                          <Textarea
                            className="min-h-28 bg-secondary/50 text-sm"
                            value={serverScopeRules}
                            onChange={(e) => setServerScopeRules(e.target.value)}
                            placeholder={t("srv.server_rules_placeholder")}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.server_network_label")}</Label>
                          <Textarea
                            className="min-h-28 bg-secondary/50 text-sm font-mono"
                            value={serverScopeNetworkJson}
                            onChange={(e) => setServerScopeNetworkJson(e.target.value)}
                            placeholder={t("srv.server_network_placeholder")}
                          />
                          {parsedServerNetworkConfig.error && (
                            <p className="text-xs text-destructive">{parsedServerNetworkConfig.error}</p>
                          )}
                        </div>
                        {serverScopeDetails?.shared_by_username && (
                          <p className="text-xs text-muted-foreground">
                            {t("srv.shared_by")}: <span className="text-foreground">{serverScopeDetails.shared_by_username}</span>
                          </p>
                        )}
                        <div className="flex justify-end">
                          <Button size="sm" className="h-8 px-4" onClick={onSaveServerContext} disabled={serverScopeLoading}>
                            {serverScopeLoading ? t("srv.saving") : t("srv.save_server_override")}
                          </Button>
                        </div>
                      </div>

                      <div className="space-y-4 rounded-lg border border-border bg-secondary/10 p-4">
                        <div>
                          <div className="inline-flex items-center rounded-full bg-secondary px-2.5 py-1 text-[11px] font-medium text-foreground">
                            {advancedServer?.group_id ? t("srv.preview_server_badge_group") : t("srv.preview_server_badge_global")}
                          </div>
                          <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.preview_server_title")}</h3>
                          <p className="text-xs text-muted-foreground mt-1">
                            {t("srv.preview_server_help")}
                          </p>
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.rules_field_stack")}</Label>
                          <Textarea className="min-h-44 bg-background text-sm" value={serverRulesPreview} readOnly />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
                          <Textarea className="min-h-20 bg-background text-xs font-mono" value={effectiveGroupForbidden.join("\n") || t("srv.none")} readOnly />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.rules_field_checks")}</Label>
                          <Textarea className="min-h-20 bg-background text-xs font-mono" value={globalRequiredLines.join("\n") || t("srv.none")} readOnly />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.effective_environment")}</Label>
                          <Textarea className="min-h-24 bg-background text-xs font-mono" value={jsonText(effectiveServerEnvironment)} readOnly />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* SECURITY TAB */}
                {advancedTab === "security" && (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.master_pw")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">{t("srv.security_help")}</p>
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                          <span className={`inline-block w-2 h-2 rounded-full ${hasMasterPassword ? "bg-primary" : "bg-muted-foreground"}`} />
                          {hasMasterPassword ? t("srv.master_pw_set_status") : t("srv.master_pw_not_set_status")}
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">{t("srv.master_pw_label")}</Label>
                            <Input type="password" value={masterPassword} onChange={(e) => setMasterPasswordText(e.target.value)} className="bg-secondary/50 h-9" placeholder={t("srv.master_pw_placeholder")} />
                          </div>
                          <Button size="sm" className="h-9" onClick={onSetMasterPassword}>{t("srv.set_mp")}</Button>
                          <Button size="sm" variant="outline" className="h-9" onClick={onClearMasterPassword}>{t("srv.clear_mp")}</Button>
                        </div>
                      </div>
                    </div>

                    <div className="border-t border-border pt-5">
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.reveal_pw")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">{t("srv.reveal_help")}</p>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                        <div className="sm:col-span-2 space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.decrypted_password")}</Label>
                          <Input value={revealedPassword} readOnly className="bg-secondary/50 h-9 font-mono" placeholder="•••••••••" />
                        </div>
                        <Button size="sm" className="h-9" onClick={onRevealPassword}>{t("srv.reveal_pw")}</Button>
                      </div>
                    </div>
                  </div>
                )}

                {/* EXECUTE TAB */}
                {advancedTab === "execute" && (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.exec_cmd")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">{t("srv.execute_help")}</p>
                      <div className="flex gap-2">
                        <Input value={execCommand} onChange={(e) => setExecCommand(e.target.value)} className="bg-secondary/50 h-9 font-mono flex-1" placeholder="hostname" />
                        <Button size="sm" className="h-9 px-6" onClick={onExecuteCommand}>{t("srv.run")}</Button>
                      </div>
                    </div>
                    {execResult && (
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("srv.output")}</Label>
                        <Textarea className="min-h-40 bg-background font-mono text-xs border-border" value={execResult} readOnly />
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={knowledgeDialogOpen}
        onOpenChange={(open) => {
          setKnowledgeDialogOpen(open);
          if (!open) {
            resetKnowledgeDialog();
          }
        }}
      >
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {knowledgeEditingId ? t("srv.edit") : t("srv.add_entry")}
            </DialogTitle>
            <DialogDescription>
              {t("srv.knowledge_manual_dialog_desc")}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_title")}</Label>
              <Input
                placeholder={t("srv.knowledge_title_placeholder")}
                value={knowledgeTitle}
                onChange={(event) => setKnowledgeTitle(event.target.value)}
                className="bg-secondary/50 h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_category")}</Label>
              <select
                value={knowledgeCategory}
                onChange={(event) => setKnowledgeCategory(event.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-secondary/50 px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {activeKnowledgeCategories.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_content")}</Label>
              <Textarea
                placeholder={t("srv.knowledge_content_placeholder")}
                value={knowledgeContent}
                onChange={(event) => setKnowledgeContent(event.target.value)}
                className="bg-secondary/50 min-h-32 text-sm"
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={knowledgeActive}
                onChange={(event) => setKnowledgeActive(event.target.checked)}
              />
              {t("srv.enable")}
            </label>
          </DialogBody>
          <DialogFooter>
            <Button
              size="sm"
              variant="outline"
              className="h-8 px-4"
              onClick={() => {
                setKnowledgeDialogOpen(false);
                resetKnowledgeDialog();
              }}
            >
              {t("srv.cancel")}
            </Button>
            <Button
              size="sm"
              className="h-8 px-4"
              onClick={() => void onKnowledgeSave()}
              disabled={knowledgeDialogSaving || !knowledgeTitle.trim() || !knowledgeContent.trim()}
            >
              {knowledgeDialogSaving ? t("srv.saving") : knowledgeEditingId ? t("srv.save") : t("srv.add_entry")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={aiKnowledgeDialogOpen}
        onOpenChange={(open) => {
          setAiKnowledgeDialogOpen(open);
          if (!open) {
            resetAiKnowledgeDialog();
          }
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              {t("srv.ai_knowledge_dialog_title")}
            </DialogTitle>
            <DialogDescription>
              {t("srv.ai_knowledge_dialog_desc")}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_title")}</Label>
              <Input
                placeholder={t("srv.knowledge_title_placeholder")}
                value={aiKnowledgeTitle}
                onChange={(event) => setAiKnowledgeTitle(event.target.value)}
                className="bg-secondary/50 h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_content")}</Label>
              <Textarea
                placeholder={t("srv.knowledge_content_placeholder")}
                value={aiKnowledgeContent}
                onChange={(event) => setAiKnowledgeContent(event.target.value)}
                className="bg-secondary/50 min-h-64 text-sm font-mono custom-scrollbar"
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button
              size="sm"
              variant="outline"
              className="h-8 px-4"
              onClick={() => {
                setAiKnowledgeDialogOpen(false);
                resetAiKnowledgeDialog();
              }}
            >
              {t("srv.cancel")}
            </Button>
            <Button
              size="sm"
              className="h-8 px-4"
              onClick={() => void onAiKnowledgeSave()}
              disabled={aiKnowledgeDialogSaving || (!aiKnowledgeTitle.trim() && !aiKnowledgeContent.trim())}
            >
              {aiKnowledgeDialogSaving ? t("srv.saving") : t("srv.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmActionDialog
        open={Boolean(serverDeleteTarget)}
        onOpenChange={(open) => {
          if (!open) setServerDeleteTarget(null);
        }}
        title={serverDeleteTarget ? tr("srv.delete_server_confirm", { name: serverDeleteTarget.name }) : t("srv.delete")}
        description={t("srv.delete_server_description")}
        confirmLabel={t("srv.delete")}
        cancelLabel={t("srv.cancel")}
        onConfirm={onDelete}
        contentClassName="max-w-sm"
      />

      <ConfirmActionDialog
        open={Boolean(groupDeleteTarget)}
        onOpenChange={(open) => {
          if (!open) setGroupDeleteTarget(null);
        }}
        title={groupDeleteTarget ? tr("srv.delete_group_confirm", { name: groupDeleteTarget.name }) : t("srv.delete")}
        description={t("srv.delete_group_description")}
        confirmLabel={t("srv.delete")}
        cancelLabel={t("srv.cancel")}
        onConfirm={onDeleteGroup}
        contentClassName="max-w-sm"
      />
    </PageShell>
  );
}
