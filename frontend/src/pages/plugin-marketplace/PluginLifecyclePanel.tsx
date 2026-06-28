import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, RotateCcw, ShieldAlert, Trash2 } from "lucide-react";

import { fetchPluginLifecycleImpact, rollbackPlugin, softUninstallPlugin } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";

function tone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "enabled" || status === "verified" || status === "signed" || status === "builtin") return "success";
  if (status === "blocked" || status === "quarantined" || status === "invalid" || status === "rejected") return "danger";
  if (status === "pending" || status === "unsigned") return "warning";
  return "neutral";
}

function CountGrid({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).filter(([, count]) => count > 0);
  if (!entries.length) {
    return <p className="text-xs text-muted-foreground">No runtime surfaces are declared.</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([kind, count]) => (
        <Badge key={kind} variant="outline">{kind}: {count}</Badge>
      ))}
    </div>
  );
}

export function PluginLifecyclePanel({ installationId }: { installationId: number | null }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const impactQuery = useQuery({
    queryKey: ["plugins", "impact", installationId],
    queryFn: () => fetchPluginLifecycleImpact(installationId as number),
    enabled: Boolean(installationId),
  });
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plugins", "catalog"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "installed"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "impact"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "surfaces"] }),
    ]);
  };
  const softUninstall = useMutation({
    mutationFn: () => softUninstallPlugin(installationId as number),
    onSuccess: () => {
      invalidate();
      toast({ description: "Plugin soft-uninstalled." });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const rollback = useMutation({
    mutationFn: () => rollbackPlugin(installationId as number),
    onSuccess: () => {
      invalidate();
      toast({ description: "Plugin rolled back to the previous package." });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const impact = impactQuery.data?.impact;
  const sandboxPolicy = impact?.package.sandbox_policy as { required?: boolean; allowed?: boolean; blockers?: string[]; requirements?: Array<Record<string, unknown>> } | undefined;

  return (
    <SectionCard title="Lifecycle impact" description="Enable blockers, disappearing surfaces, missing permissions, and reversible operations." icon={<History className="h-4 w-4" />}>
      <QueryStateBlock loading={impactQuery.isLoading} error={impactQuery.error}>
        {!installationId || !impact ? (
          <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
            Select an installation to inspect lifecycle impact.
          </p>
        ) : (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-3">
              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-foreground">{impact.plugin_id}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">Package {impact.package.version}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge label={impact.status} tone={tone(impact.status)} />
                    <StatusBadge label={impact.package.ready_to_enable ? "ready" : "blocked"} tone={impact.package.ready_to_enable ? "success" : "warning"} />
                  </div>
                </div>
                {impact.package.enable_blockers.length ? (
                  <div className="mt-3 space-y-2">
                    {impact.package.enable_blockers.map((blocker) => (
                      <div key={blocker} className="flex items-start gap-2 rounded-lg border border-border/60 bg-secondary/15 px-3 py-2 text-xs text-muted-foreground">
                        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                        {blocker}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">Surfaces removed on disable/uninstall</div>
                <CountGrid counts={impact.surfaces.counts} />
              </div>
            </div>

            <div className="space-y-3">
              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">Permission review</div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">declared: {impact.permissions.declared.length}</Badge>
                  <Badge variant="outline">granted: {impact.permissions.granted.length}</Badge>
                  <Badge variant="outline">missing: {impact.permissions.missing.length}</Badge>
                </div>
              </div>
              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">Secrets</div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">declared: {impact.secrets.declared.length}</Badge>
                  <Badge variant="outline">bound: {impact.secrets.bound.length}</Badge>
                  <Badge variant={impact.secrets.missing_required.length ? "destructive" : "outline"}>
                    missing required: {impact.secrets.missing_required.length}
                  </Badge>
                </div>
              </div>
              <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">Sandbox</div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge
                    label={sandboxPolicy?.required ? (sandboxPolicy.allowed ? "sandbox ready" : "sandbox blocked") : "no sandbox"}
                    tone={sandboxPolicy?.required ? (sandboxPolicy.allowed ? "success" : "danger") : "neutral"}
                  />
                  <Badge variant="outline">requirements: {sandboxPolicy?.requirements?.length ?? 0}</Badge>
                  <Badge variant={sandboxPolicy?.blockers?.length ? "destructive" : "outline"}>blockers: {sandboxPolicy?.blockers?.length ?? 0}</Badge>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => softUninstall.mutate()} disabled={softUninstall.isPending}>
                  <Trash2 className="h-4 w-4" />
                  Soft uninstall
                </Button>
                <Button size="sm" variant="outline" onClick={() => rollback.mutate()} disabled={rollback.isPending || !impact.uninstall.reversible}>
                  <RotateCcw className="h-4 w-4" />
                  Rollback
                </Button>
              </div>
            </div>
          </div>
        )}
      </QueryStateBlock>
    </SectionCard>
  );
}
