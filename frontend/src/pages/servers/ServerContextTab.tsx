import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { FrontendServer, ServerDetailsResponse } from "@/lib/api";

import { jsonText } from "./rules";

interface ServerContextTabProps {
  advancedServer: FrontendServer | null;
  effectiveGroupForbidden: string[];
  effectiveServerEnvironment: Record<string, string>;
  globalRequiredLines: string[];
  onOpenInheritedRules: () => void;
  onSaveServerContext: () => void;
  parsedServerNetworkConfig: { error: string | null };
  serverRulesPreview: string;
  serverScopeDetails: ServerDetailsResponse | null;
  serverScopeLoading: boolean;
  serverScopeNetworkJson: string;
  serverScopeRules: string;
  setServerScopeNetworkJson: (value: string) => void;
  setServerScopeRules: (value: string) => void;
  t: (key: string) => string;
}

export function ServerContextTab({
  advancedServer,
  effectiveGroupForbidden,
  effectiveServerEnvironment,
  globalRequiredLines,
  onOpenInheritedRules,
  onSaveServerContext,
  parsedServerNetworkConfig,
  serverRulesPreview,
  serverScopeDetails,
  serverScopeLoading,
  serverScopeNetworkJson,
  serverScopeRules,
  setServerScopeNetworkJson,
  setServerScopeRules,
  t,
}: ServerContextTabProps) {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
                {t("srv.scope_server")}
              </span>
              <span className="inline-flex items-center rounded-full bg-secondary px-2.5 py-1 text-[11px] font-medium text-foreground">
                {advancedServer?.group_id ? t("srv.inherits_global_group") : t("srv.inherits_global")}
              </span>
            </div>
            <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.server_override_title")}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{t("srv.server_override_help")}</p>
          </div>
          <Button size="sm" variant="outline" className="h-8" onClick={onOpenInheritedRules}>
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
              onChange={(event) => setServerScopeRules(event.target.value)}
              placeholder={t("srv.server_rules_placeholder")}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.server_network_label")}</Label>
            <Textarea
              className="min-h-28 bg-secondary/50 font-mono text-sm"
              value={serverScopeNetworkJson}
              onChange={(event) => setServerScopeNetworkJson(event.target.value)}
              placeholder={t("srv.server_network_placeholder")}
            />
            {parsedServerNetworkConfig.error ? (
              <p className="text-xs text-destructive">{parsedServerNetworkConfig.error}</p>
            ) : null}
          </div>
          {serverScopeDetails?.shared_by_username ? (
            <p className="text-xs text-muted-foreground">
              {t("srv.shared_by")}: <span className="text-foreground">{serverScopeDetails.shared_by_username}</span>
            </p>
          ) : null}
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
            <p className="mt-1 text-xs text-muted-foreground">{t("srv.preview_server_help")}</p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.rules_field_stack")}</Label>
            <Textarea className="min-h-44 bg-background text-sm" value={serverRulesPreview} readOnly />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.rules_field_forbidden")}</Label>
            <Textarea className="min-h-20 bg-background font-mono text-xs" value={effectiveGroupForbidden.join("\n") || t("srv.none")} readOnly />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.rules_field_checks")}</Label>
            <Textarea className="min-h-20 bg-background font-mono text-xs" value={globalRequiredLines.join("\n") || t("srv.none")} readOnly />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.effective_environment")}</Label>
            <Textarea className="min-h-24 bg-background font-mono text-xs" value={jsonText(effectiveServerEnvironment)} readOnly />
          </div>
        </div>
      </div>
    </div>
  );
}
