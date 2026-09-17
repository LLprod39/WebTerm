import { useDeferredValue, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";

import { searchServerShareCandidates } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { FrontendGroup, FrontendServer, ServerGroupRole } from "@/lib/api";

import type { ShareItem } from "./types";

interface ServerAccessTabProps {
  advancedServer: FrontendServer | null;
  groupMemberRole: ServerGroupRole;
  groupMemberUser: string;
  groupRemoveUserId: string;
  manageableGroups: FrontendGroup[];
  onAddGroupMember: () => void;
  onRemoveGroupMember: () => void;
  onShareCreate: () => void;
  onShareRevoke: (shareId: number) => void;
  openGroupRules: (groupId: number) => void;
  setGroupMemberRole: (role: ServerGroupRole) => void;
  setGroupMemberUser: (value: string) => void;
  setGroupRemoveUserId: (value: string) => void;
  setShareContext: (value: boolean) => void;
  setShareExpiresAt: (value: string) => void;
  setShareUser: (value: string) => void;
  shareContext: boolean;
  shareExpiresAt: string;
  shares: ShareItem[];
  shareUser: string;
  t: (key: string) => string;
}

export function ServerAccessTab({
  advancedServer,
  groupMemberRole,
  groupMemberUser,
  groupRemoveUserId,
  manageableGroups,
  onAddGroupMember,
  onRemoveGroupMember,
  onShareCreate,
  onShareRevoke,
  openGroupRules,
  setGroupMemberRole,
  setGroupMemberUser,
  setGroupRemoveUserId,
  setShareContext,
  setShareExpiresAt,
  setShareUser,
  shareContext,
  shareExpiresAt,
  shares,
  shareUser,
  t,
}: ServerAccessTabProps) {
  const canManageGroupAccess = Boolean(
    advancedServer?.group_id &&
      manageableGroups.some((group) => group.id === advancedServer.group_id),
  );
  const [shareUserSelected, setShareUserSelected] = useState(false);
  const [sharePickerOpen, setSharePickerOpen] = useState(false);
  const deferredShareUser = useDeferredValue(shareUser.trim());
  const candidatesQuery = useQuery({
    queryKey: ["server-share-candidates", advancedServer?.id, deferredShareUser],
    queryFn: () => searchServerShareCandidates(advancedServer!.id, deferredShareUser),
    enabled: Boolean(advancedServer?.id) && deferredShareUser.length > 0 && !shareUserSelected && sharePickerOpen,
    staleTime: 30_000,
    retry: false,
  });
  const candidates = candidatesQuery.data?.candidates ?? [];

  useEffect(() => {
    if (!shareUser.trim()) {
      setShareUserSelected(false);
    }
  }, [shareUser]);

  return (
    <div className="space-y-5">
      <div>
        <h3 className="mb-1 text-sm font-semibold text-foreground">{t("srv.server_sharing")}</h3>
        <p className="mb-4 text-xs text-muted-foreground">{t("srv.share_help")}</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="relative space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.username")}</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={t("srv.user_search_placeholder")}
                value={shareUser}
                onChange={(event) => {
                  setShareUser(event.target.value);
                  setShareUserSelected(false);
                  setSharePickerOpen(true);
                }}
                onFocus={() => setSharePickerOpen(true)}
                onBlur={() => {
                  window.setTimeout(() => setSharePickerOpen(false), 120);
                }}
                className="h-9 bg-secondary/50 pl-9"
                autoComplete="off"
                aria-autocomplete="list"
                aria-expanded={sharePickerOpen && !shareUserSelected && shareUser.trim().length > 0}
                aria-controls="server-share-user-results"
              />
            </div>
            {sharePickerOpen && !shareUserSelected && shareUser.trim().length > 0 ? (
              <div
                id="server-share-user-results"
                role="listbox"
                aria-label={t("srv.user_search_results")}
                className="absolute z-30 mt-1 max-h-44 w-full overflow-auto rounded-sm border border-border bg-popover p-1 shadow-elev-2"
              >
                {candidatesQuery.isPending ? (
                  <p className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {t("srv.user_searching")}
                  </p>
                ) : candidates.length ? (
                  candidates.map((candidate) => (
                    <button
                      key={candidate.id}
                      type="button"
                      role="option"
                      className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-2 text-left text-xs hover:bg-secondary"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => {
                        setShareUser(candidate.username);
                        setShareUserSelected(true);
                        setSharePickerOpen(false);
                      }}
                    >
                      <span className="min-w-0 truncate font-medium text-foreground">
                        {candidate.label || candidate.username}
                      </span>
                      {candidate.email ? (
                        <span className="shrink-0 text-muted-foreground">{candidate.email}</span>
                      ) : null}
                    </button>
                  ))
                ) : (
                  <p className="px-2 py-2 text-xs text-muted-foreground">{t("srv.user_search_empty")}</p>
                )}
              </div>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.expires")}</Label>
            <Input
              type="datetime-local"
              value={shareExpiresAt}
              onChange={(event) => setShareExpiresAt(event.target.value)}
              className="h-9 bg-secondary/50"
            />
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={shareContext}
              onChange={(event) => setShareContext(event.target.checked)}
              className="rounded"
            />
            {t("srv.share_context")}
          </label>
          <Button size="sm" className="h-8 px-4" onClick={onShareCreate}>
            {t("srv.share")}
          </Button>
        </div>
      </div>

      {shares.length > 0 ? (
        <div className="border-t border-border pt-4">
          <h4 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">{t("srv.active_shares")}</h4>
          <div className="space-y-2">
            {shares.map((share) => (
              <div key={share.id} className="flex items-center gap-3 rounded-sm border border-border bg-secondary/10 px-3 py-2.5">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-primary/15 text-xs font-medium text-primary">
                  {(share.username || "U").slice(0, 1).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{share.username}</p>
                  <p className="text-xs text-muted-foreground">
                    {share.email || "—"} · {share.is_active ? t("srv.status_active") : t("srv.status_expired")}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 border-destructive/30 text-xs text-destructive hover:bg-destructive/10"
                  onClick={() => onShareRevoke(share.id)}
                >
                  {t("srv.revoke")}
                </Button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {canManageGroupAccess ? (
        <div className="border-t border-border pt-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t("srv.group_access")}</h4>
              <p className="mt-2 text-sm font-medium text-foreground">{advancedServer?.group_name}</p>
              <p className="mt-1 text-xs text-muted-foreground">{t("srv.group_access_help")}</p>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              onClick={() => openGroupRules(advancedServer!.group_id!)}
            >
              {t("srv.open_group_rules")}
            </Button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.username_email")}</Label>
              <Input
                placeholder="user@example.com"
                value={groupMemberUser}
                onChange={(event) => setGroupMemberUser(event.target.value)}
                className="h-9 bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.role")}</Label>
              <Select
                value={groupMemberRole}
                onValueChange={(value) => setGroupMemberRole(value as ServerGroupRole)}
              >
                <SelectTrigger className="h-9 bg-secondary/50" aria-label={t("srv.role")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="owner">{t("srv.role_owner")}</SelectItem>
                  <SelectItem value="admin">{t("srv.role_admin")}</SelectItem>
                  <SelectItem value="member">{t("srv.role_member")}</SelectItem>
                  <SelectItem value="viewer">{t("srv.role_viewer")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button size="sm" className="h-9 w-full" onClick={onAddGroupMember}>
                {t("srv.add_member")}
              </Button>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.remove_by_user_id")}</Label>
              <Input
                placeholder={t("srv.user_id_placeholder")}
                value={groupRemoveUserId}
                onChange={(event) => setGroupRemoveUserId(event.target.value)}
                className="h-9 bg-secondary/50"
              />
            </div>
            <div className="flex items-end">
              <Button
                size="sm"
                variant="outline"
                className="h-9 w-full border-destructive/30 text-destructive hover:bg-destructive/10"
                onClick={onRemoveGroupMember}
              >
                {t("srv.remove_member")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
