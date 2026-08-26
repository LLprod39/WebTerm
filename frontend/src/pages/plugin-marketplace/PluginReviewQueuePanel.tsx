import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, BadgeCheck, FileCheck2, FileDown, History, ScrollText, ShieldAlert, ShieldCheck, ShieldX, Trash2 } from "lucide-react";

import {
  attestPluginPackage,
  cleanupPluginPackageRetention,
  fetchPluginPackageRetention,
  fetchPluginReviewPackages,
  pluginPackageSbomUrl,
  replayPluginPackageProvenance,
  reviewPluginPackage,
  securityScanPluginPackage,
  signPluginPackage,
  verifyPluginPackageSignature,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";

function tone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "verified" || status === "signed" || status === "builtin") return "success";
  if (status === "rejected" || status === "invalid" || status === "suspended") return "danger";
  if (status === "pending" || status === "unsigned") return "warning";
  return "neutral";
}

export function PluginReviewQueuePanel() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();
  const reviewQuery = useQuery({ queryKey: ["plugins", "review", "packages"], queryFn: fetchPluginReviewPackages });
  const retentionQuery = useQuery({ queryKey: ["plugins", "packages", "retention"], queryFn: fetchPluginPackageRetention });
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plugins", "review"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "installed"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "catalog"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "impact"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "packages", "retention"] }),
    ]);
  };
  const reviewMutation = useMutation({
    mutationFn: ({ packageId, status }: { packageId: number; status: string }) => reviewPluginPackage(packageId, { status }),
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Решение по пакету сохранено.", "Package review updated.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const signMutation = useMutation({
    mutationFn: signPluginPackage,
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Пакет подписан.", "Package signed.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const verifyMutation = useMutation({
    mutationFn: verifyPluginPackageSignature,
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Подпись пакета проверена.", "Package signature verified.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const attestMutation = useMutation({
    mutationFn: attestPluginPackage,
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Аттестация пакета записана.", "Package attestation recorded.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const securityScanMutation = useMutation({
    mutationFn: securityScanPluginPackage,
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Проверка безопасности записана.", "Security scan recorded.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const replayMutation = useMutation({
    mutationFn: replayPluginPackageProvenance,
    onSuccess: () => {
      invalidate();
      toast({ description: localize(lang, "Проверка происхождения завершена.", "Remote provenance replay finished.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const retentionCleanupMutation = useMutation({
    mutationFn: cleanupPluginPackageRetention,
    onSuccess: (result) => {
      invalidate();
      const summary = result.result.summary as { delete_count?: number; delete_bytes?: number } | undefined;
      toast({ description: localize(lang, `Очистка: ${Number(summary?.delete_count || 0)} файлов, ${Number(summary?.delete_bytes || 0)} байт.`, `Retention cleanup: ${Number(summary?.delete_count || 0)} file(s), ${Number(summary?.delete_bytes || 0)} bytes.`) });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const packages = reviewQuery.data?.packages ?? [];
  const retentionSummary = retentionQuery.data?.retention?.summary as { file_count?: number; referenced_count?: number; unreferenced_count?: number; total_bytes?: number } | undefined;

  return (
    <SectionCard
      title={localize(lang, "Проверка и подпись", "Review and signing")}
      description={localize(lang, "Пакет нельзя включить, пока он не прошёл проверку.", "Local package review gate before enabled runtime surfaces.")}
      icon={<FileCheck2 className="h-4 w-4" />}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => retentionCleanupMutation.mutate({ dry_run: true })} disabled={retentionCleanupMutation.isPending}>
            <Archive className="h-4 w-4" />
            {localize(lang, "Показать, что удалится", "Dry run")}
          </Button>
          <Button size="sm" variant="outline" onClick={() => retentionCleanupMutation.mutate({ dry_run: false })} disabled={retentionCleanupMutation.isPending}>
            <Trash2 className="h-4 w-4" />
            {localize(lang, "Очистить", "Cleanup")}
          </Button>
        </div>
      }
    >
      <QueryStateBlock loading={reviewQuery.isLoading} error={reviewQuery.error}>
        {retentionSummary ? (
          <div className="mb-3 flex flex-wrap gap-2 rounded-lg border border-border/70 bg-secondary/15 px-4 py-3 text-xs text-muted-foreground">
            <span>{localize(lang, "хранится", "retained")}: {Number(retentionSummary.file_count || 0)}</span>
            <span>{localize(lang, "используется", "referenced")}: {Number(retentionSummary.referenced_count || 0)}</span>
            <span>{localize(lang, "не используется", "unreferenced")}: {Number(retentionSummary.unreferenced_count || 0)}</span>
            <span>{localize(lang, "байт", "bytes")}: {Number(retentionSummary.total_bytes || 0)}</span>
          </div>
        ) : null}
        <div className="grid gap-3 lg:grid-cols-2">
          {packages.length ? packages.map((item) => (
            <div key={item.id} className="rounded-lg border border-border/70 bg-card px-4 py-4">
              {(() => {
                const lastAttestation = Array.isArray(item.attestations) ? item.attestations[item.attestations.length - 1] : null;
                const hasRemoteProvenance = Boolean(item.provenance && typeof item.provenance.source_url === "string");
                const sbomSummary = item.sbom?.summary as { file_count?: number; component_count?: number } | undefined;
                const dependencySummary = item.dependency_scan?.summary as { dependency_manifest_count?: number } | undefined;
                return (
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">{item.name}</span>
                    <Badge variant="outline">{item.plugin_id}</Badge>
                    <Badge variant="secondary">{item.version}</Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <StatusBadge label={item.review_status} tone={tone(item.review_status)} />
                    <StatusBadge label={item.signature_status} tone={tone(item.signature_status)} />
                    <Badge variant="outline">{item.source}</Badge>
                    {lastAttestation ? (
                      <StatusBadge
                        label={`${localize(lang, "аттестация", "attested")}: ${String(lastAttestation.status || localize(lang, "неизвестно", "unknown"))}`}
                        tone={tone(String(lastAttestation.status || ""))}
                      />
                    ) : null}
                    {sbomSummary ? <Badge variant="outline">{localize(lang, "файлы", "files")}: {Number(sbomSummary.file_count || 0)}</Badge> : null}
                    {dependencySummary ? <Badge variant="outline">{localize(lang, "зависимости", "deps")}: {Number(sbomSummary?.component_count || 0)}</Badge> : null}
                    {dependencySummary?.dependency_manifest_count ? <StatusBadge label={localize(lang, "есть файл зависимостей", "dependency manifest")} tone="warning" /> : null}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label={localize(lang, "Одобрить пакет", "Approve package")}
                    title={localize(lang, "Одобрить пакет", "Approve package")}
                    onClick={() => reviewMutation.mutate({ packageId: item.id, status: "verified" })}
                    disabled={reviewMutation.isPending}
                  >
                    <BadgeCheck className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label={localize(lang, "Отклонить пакет", "Reject package")}
                    title={localize(lang, "Отклонить пакет", "Reject package")}
                    onClick={() => reviewMutation.mutate({ packageId: item.id, status: "rejected" })}
                    disabled={reviewMutation.isPending}
                  >
                    <ShieldX className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label={localize(lang, "Подписать пакет", "Sign package")}
                    title={localize(lang, "Подписать пакет", "Sign package")}
                    onClick={() => signMutation.mutate(item.id)}
                    disabled={signMutation.isPending || item.review_status !== "verified"}
                  >
                    <ShieldCheck className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label={localize(lang, "Проверить подпись", "Verify signature")}
                    title={localize(lang, "Проверить подпись", "Verify signature")}
                    onClick={() => verifyMutation.mutate(item.id)}
                    disabled={verifyMutation.isPending}
                  >
                    <FileCheck2 className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label={localize(lang, "Скачать SBOM", "Export SBOM")}
                    title={localize(lang, "Скачать SBOM", "Export SBOM")}
                    onClick={() => window.open(pluginPackageSbomUrl(item.id), "_blank", "noopener,noreferrer")}
                  >
                    <FileDown className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label={localize(lang, "Записать аттестацию", "Record package attestation")}
                    title={localize(lang, "Записать аттестацию", "Record package attestation")}
                    onClick={() => attestMutation.mutate(item.id)}
                    disabled={attestMutation.isPending}
                  >
                    <ScrollText className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label={localize(lang, "Проверить безопасность", "Run security scan")}
                    title={localize(lang, "Проверить безопасность", "Run security scan")}
                    onClick={() => securityScanMutation.mutate(item.id)}
                    disabled={securityScanMutation.isPending}
                  >
                    <ShieldAlert className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    aria-label={localize(lang, "Проверить происхождение", "Replay remote provenance")}
                    title={localize(lang, "Проверить происхождение", "Replay remote provenance")}
                    onClick={() => replayMutation.mutate(item.id)}
                    disabled={replayMutation.isPending || !hasRemoteProvenance}
                  >
                    <History className="h-4 w-4" />
                  </Button>
                </div>
              </div>
                );
              })()}
            </div>
          )) : (
            <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
              {localize(lang, "Пакетов на проверке нет.", "No plugin packages are waiting for review.")}
            </p>
          )}
        </div>
      </QueryStateBlock>
    </SectionCard>
  );
}
