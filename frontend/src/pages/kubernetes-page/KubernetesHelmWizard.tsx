import { useMutation, useQuery } from "@tanstack/react-query";
import { Package, Rocket, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { createKubernetesActionRequest, type KubernetesCluster } from "@/api";
import { fetchKubernetesHelmReleases } from "@/api/kubernetes-ops-extra";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";

/**
 * Guided Helm install / ownership wizard.
 * Install itself is approval-gated (no silent cluster mutate).
 */
export function KubernetesHelmWizard({
  open,
  onClose,
  clusters,
}: {
  open: boolean;
  onClose: () => void;
  clusters: KubernetesCluster[];
}) {
  const { lang } = useI18n();
  const [clusterId, setClusterId] = useState(clusters[0]?.id || "");
  const [namespace, setNamespace] = useState("default");
  const [releaseName, setReleaseName] = useState("");
  const [chartRef, setChartRef] = useState("bitnami/nginx");
  const [valuesNote, setValuesNote] = useState("");
  const [step, setStep] = useState<1 | 2 | 3>(1);

  const releasesQuery = useQuery({
    queryKey: ["kubernetes", "helm", "releases", clusterId],
    queryFn: () => fetchKubernetesHelmReleases({ cluster_id: clusterId, limit: 80 }),
    enabled: open && Boolean(clusterId),
    staleTime: 30_000,
    retry: false,
  });

  const items = useMemo(() => releasesQuery.data?.items || [], [releasesQuery.data?.items]);
  const conflicts = useMemo(() => items.filter((i) => i.conflict), [items]);

  const requestMutation = useMutation({
    mutationFn: () =>
      createKubernetesActionRequest({
        action: "k8s.rollout.restart",
        // Backend may map unknown helm actions; we encode intent in reason for operators.
        reason: [
          "HELM_INSTALL_REQUEST",
          `release=${releaseName || "unnamed"}`,
          `chart=${chartRef}`,
          `namespace=${namespace}`,
          `cluster=${clusterId}`,
          valuesNote ? `values_note=${valuesNote.slice(0, 400)}` : "",
        ]
          .filter(Boolean)
          .join(" | "),
        target: clusterId ? { cluster_id: clusterId, namespace } : { namespace },
      }),
  });

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/45 p-3 sm:items-center" role="dialog">
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-sm border border-border bg-card shadow-elev-3">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <Package className="h-4 w-4 text-primary" />
            <div>
              <div className="font-display text-sm font-semibold">
                {localize(lang, "Helm · мастер", "Helm · wizard")}
              </div>
              <div className="text-2xs text-muted-foreground">
                {localize(lang, "Проверка владельца → запрос установки", "Ownership check → request install")}
              </div>
            </div>
          </div>
          <Button type="button" size="icon" variant="ghost" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </header>

        <div className="flex gap-2 border-b border-border px-4 py-2 text-2xs uppercase tracking-wide">
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setStep(n as 1 | 2 | 3)}
              className={
                step === n ? "font-semibold text-primary" : "text-muted-foreground hover:text-foreground"
              }
            >
              {n}.{" "}
              {n === 1
                ? localize(lang, "Релизы", "Releases")
                : n === 2
                  ? localize(lang, "Параметры", "Params")
                  : localize(lang, "Запрос", "Request")}
            </button>
          ))}
        </div>

        <div className="space-y-4 p-4">
          {step === 1 ? (
            <>
              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">{localize(lang, "Кластер", "Cluster")}</span>
                <select
                  value={clusterId}
                  onChange={(e) => setClusterId(e.target.value)}
                  className="h-9 w-full rounded-sm border border-border bg-surface-0 px-2 font-mono text-xs"
                >
                  {clusters.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="rounded-sm border border-border bg-surface-0 p-3">
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="font-semibold">{localize(lang, "Известные релизы", "Known releases")}</span>
                  <StatusBadge
                    label={
                      conflicts.length
                        ? localize(lang, `${conflicts.length} конфликтов`, `${conflicts.length} conflict`)
                        : localize(lang, "готово", "ok")
                    }
                    tone={conflicts.length ? "warning" : "success"}
                  />
                </div>
                {releasesQuery.isLoading ? (
                  <div className="text-2xs text-muted-foreground">{localize(lang, "Загрузка…", "Loading…")}</div>
                ) : items.length ? (
                  <ul className="max-h-48 space-y-1 overflow-y-auto font-mono text-2xs">
                    {items.slice(0, 40).map((item) => (
                      <li key={`${item.cluster_name}-${item.namespace}-${item.release_name}`} className="flex justify-between gap-2 border-b border-border/40 py-1">
                        <span className="truncate text-foreground">
                          {item.namespace}/{item.release_name}
                        </span>
                        <span className="shrink-0 text-muted-foreground">{item.primary_owner || "—"}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-2xs text-muted-foreground">
                    {localize(lang, "Метки Helm не найдены, но запрос на установку всё равно можно отправить.", "No Helm labels were found, but you can still request an installation.")}
                  </div>
                )}
              </div>
              <Button type="button" className="w-full" onClick={() => setStep(2)}>
                {localize(lang, "Далее · параметры", "Next · params")}
              </Button>
            </>
          ) : null}

          {step === 2 ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1 text-xs">
                  <span className="text-muted-foreground">{localize(lang, "Релиз", "Release")}</span>
                  <input
                    value={releaseName}
                    onChange={(e) => setReleaseName(e.target.value)}
                    placeholder="my-nginx"
                    className="h-9 w-full rounded-sm border border-border bg-surface-0 px-2 font-mono text-xs"
                  />
                </label>
                <label className="space-y-1 text-xs">
                  <span className="text-muted-foreground">{localize(lang, "Пространство имён", "Namespace")}</span>
                  <input
                    value={namespace}
                    onChange={(e) => setNamespace(e.target.value)}
                    className="h-9 w-full rounded-sm border border-border bg-surface-0 px-2 font-mono text-xs"
                  />
                </label>
              </div>
              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">{localize(lang, "Ссылка на chart", "Chart ref")}</span>
                <input
                  value={chartRef}
                  onChange={(e) => setChartRef(e.target.value)}
                  className="h-9 w-full rounded-sm border border-border bg-surface-0 px-2 font-mono text-xs"
                />
              </label>
              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">{localize(lang, "Параметры / заметка", "Values / note")}</span>
                <textarea
                  value={valuesNote}
                  onChange={(e) => setValuesNote(e.target.value)}
                  rows={3}
                  className="w-full rounded-sm border border-border bg-surface-0 px-2 py-2 font-mono text-xs"
                  placeholder="replicaCount: 2"
                />
              </label>
              <div className="flex gap-2">
                <Button type="button" variant="outline" className="flex-1" onClick={() => setStep(1)}>
                  {localize(lang, "Назад", "Back")}
                </Button>
                <Button type="button" className="flex-1" onClick={() => setStep(3)} disabled={!releaseName.trim()}>
                  {localize(lang, "Далее", "Next")}
                </Button>
              </div>
            </>
          ) : null}

          {step === 3 ? (
            <>
              <div className="space-y-2 rounded-sm border border-border bg-surface-0 p-3 font-mono text-2xs leading-relaxed text-muted-foreground">
                <div>
                  <span className="text-foreground">{localize(lang, "релиз", "release")}</span> {releaseName}
                </div>
                <div>
                  <span className="text-foreground">{localize(lang, "пакет Helm", "chart")}</span> {chartRef}
                </div>
                <div>
                  <span className="text-foreground">{localize(lang, "пространство", "namespace")}</span> {namespace}
                </div>
                <div>
                  <span className="text-foreground">{localize(lang, "кластер", "cluster")}</span> {clusterId}
                </div>
                <p className="pt-2 text-amber-200/90">
                  {localize(
                    lang,
                    "Прямая установка Helm из интерфейса запрещена политикой. Будет создан запрос оператору на подтверждение.",
                    "Direct helm install from UI is policy-blocked. Creates an operator approval request.",
                  )}
                </p>
              </div>
              {requestMutation.isSuccess ? (
                <div className="rounded-sm border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
                  {localize(lang, "Запрос создан.", "Request created.")}{" "}
                  <Link className="underline" to="/kubernetes">
                    OK
                  </Link>
                </div>
              ) : null}
              {requestMutation.error ? (
                <div className="rounded-sm border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {requestMutation.error instanceof Error
                    ? requestMutation.error.message
                    : localize(lang, "Ошибка запроса", "Request failed")}
                </div>
              ) : null}
              <div className="flex gap-2">
                <Button type="button" variant="outline" className="flex-1" onClick={() => setStep(2)}>
                  {localize(lang, "Назад", "Back")}
                </Button>
                <Button
                  type="button"
                  className="flex-1 gap-2"
                  disabled={requestMutation.isPending}
                  onClick={() => requestMutation.mutate()}
                >
                  <Rocket className="h-3.5 w-3.5" />
                  {localize(lang, "Запросить установку", "Request install")}
                </Button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
