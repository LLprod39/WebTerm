import { useCallback, useEffect, useMemo, useState } from "react";

import {
  addServerGroupMember,
  fetchServerDetails,
  getGlobalServerContext,
  getGroupServerContext,
  removeServerGroupMember,
  saveGlobalServerContext,
  saveGroupServerContext,
  updateServer,
  type FrontendGroup,
  type FrontendServer,
  type ServerDetailsResponse,
  type ServerGroupRole,
} from "@/lib/api";

import {
  formatScopedRulesPreview,
  getServerEnvironmentVars,
  jsonText,
  mergeEnvironments,
  splitLines,
  toJson,
  toUnknownJson,
  uniqueLines,
} from "./rules";
import type { MainTab } from "./types";

type Translate = (key: string) => string;
type TranslateWithVars = (key: string, vars?: Record<string, string | number>) => string;
type ManageableGroup = FrontendGroup & { id: number; role: ServerGroupRole };

interface UseServerRulesControllerParams {
  activeServer: FrontendServer | null;
  manageableGroups: ManageableGroup[];
  mainTab: MainTab;
  reload: () => Promise<void>;
  t: Translate;
  tr: TranslateWithVars;
}

export function useServerRulesController({
  activeServer,
  manageableGroups,
  mainTab,
  reload,
  t,
  tr,
}: UseServerRulesControllerParams) {
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
    () =>
      mergeEnvironments(
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
          label: activeServer?.group_id ? tr("srv.group_label_name", { name: activeServer.group_name }) : t("srv.rules_group_badge"),
          value: activeServer?.group_id ? groupRules : "",
        },
        {
          label: activeServer ? tr("srv.server_label_name", { name: activeServer.name }) : t("srv.rules_server_badge"),
          value: serverScopeRules,
        },
      ]) || t("srv.no_rules_configured"),
    [activeServer, globalRules, groupRules, serverScopeRules, t, tr],
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

  const resetGroupMemberFields = useCallback(() => {
    setGroupMemberUser("");
    setGroupRemoveUserId("");
  }, []);

  const selectGlobalRules = useCallback(() => {
    setRulesScopeTab("global");
  }, []);

  const selectGroupRules = useCallback((groupId: number) => {
    setRulesGroupId(groupId);
    setRulesScopeTab("group");
  }, []);

  const loadForAdvancedServer = useCallback(async (server: FrontendServer) => {
    const hasGroupRulesAccess = Boolean(
      server.group_id && manageableGroups.some((group) => group.id === server.group_id),
    );
    resetGroupMemberFields();
    if (hasGroupRulesAccess && server.group_id) {
      setRulesGroupId(server.group_id);
    }

    const [globalCtx, groupCtx, details] = await Promise.all([
      getGlobalServerContext().catch(() => null),
      hasGroupRulesAccess && server.group_id
        ? getGroupServerContext(server.group_id).catch(() => null)
        : Promise.resolve(null),
      fetchServerDetails(server.id).catch(() => null),
    ]);

    if (globalCtx) applyGlobalContextState(globalCtx);
    else clearGlobalContextState();

    if (groupCtx) applyGroupContextState(groupCtx);
    else clearGroupContextState();

    if (details) applyServerScopeState(details);
    else clearServerScopeState();
  }, [
    applyGlobalContextState,
    applyGroupContextState,
    applyServerScopeState,
    clearGlobalContextState,
    clearGroupContextState,
    clearServerScopeState,
    manageableGroups,
    resetGroupMemberFields,
  ]);

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
          rulesScopeTab === "group" && rulesGroupId
            ? getGroupServerContext(rulesGroupId).catch(() => null)
            : Promise.resolve(null);
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
    if (!activeServer) return;
    if (parsedServerNetworkConfig.error) {
      alert(t("srv.invalid_server_network_json"));
      return;
    }

    setServerScopeLoading(true);
    try {
      await updateServer(activeServer.id, {
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
    if (!activeServer?.group_id || !groupMemberUser.trim()) return;
    await addServerGroupMember(activeServer.group_id, { user: groupMemberUser.trim(), role: groupMemberRole });
    setGroupMemberUser("");
    alert(t("srv.group_member_updated"));
  };

  const onRemoveGroupMember = async () => {
    if (!activeServer?.group_id || !groupRemoveUserId.trim()) return;
    const userId = Number(groupRemoveUserId);
    if (!Number.isFinite(userId) || userId <= 0) {
      alert(t("srv.invalid_user_id"));
      return;
    }
    await removeServerGroupMember(activeServer.group_id, userId);
    setGroupRemoveUserId("");
    alert(t("srv.group_member_removed"));
  };

  return {
    effectiveGroupEnvironment,
    effectiveGroupForbidden,
    effectiveServerEnvironment,
    globalEnvJson,
    globalForbidden,
    globalForbiddenLines,
    globalRequired,
    globalRequiredLines,
    globalRules,
    globalRulesPreview,
    groupEnvJson,
    groupForbidden,
    groupMemberRole,
    groupMemberUser,
    groupRemoveUserId,
    groupRules,
    groupRulesPreview,
    loadForAdvancedServer,
    onAddGroupMember,
    onRemoveGroupMember,
    onSaveGlobalContext,
    onSaveGroupContext,
    onSaveServerContext,
    parsedGlobalEnvironment,
    parsedGroupEnvironment,
    parsedServerNetworkConfig,
    rulesGroupId,
    rulesLoading,
    rulesScopeTab,
    selectGlobalRules,
    selectGroupRules,
    selectedRulesGroup,
    serverRulesPreview,
    serverScopeDetails,
    serverScopeLoading,
    serverScopeNetworkJson,
    serverScopeRules,
    setGlobalEnvJson,
    setGlobalForbidden,
    setGlobalRequired,
    setGlobalRules,
    setGroupEnvJson,
    setGroupForbidden,
    setGroupMemberRole,
    setGroupMemberUser,
    setGroupRemoveUserId,
    setGroupRules,
    setRulesGroupId,
    setRulesScopeTab,
    setServerScopeNetworkJson,
    setServerScopeRules,
  };
}

export type ServerRulesController = ReturnType<typeof useServerRulesController>;
