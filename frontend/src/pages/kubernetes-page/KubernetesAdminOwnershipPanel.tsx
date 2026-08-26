import type { KubernetesAdminOwnershipContext, KubernetesAdminOwnershipSummary } from "@/api";
import { StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";

type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

export function OwnershipSummaryPanel({ lang, summary }: { lang: string; summary: KubernetesAdminOwnershipSummary }) {
  return (
    <div className="mb-4 rounded-lg border border-border/70 bg-background/45 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={localize(lang, "Сводка владельцев", "Ownership summary")} tone="info" />
        <span className="text-xs text-muted-foreground">
          {localize(lang, "Всего:", "Total:")} {summary.total}
        </span>
        <span className="text-xs text-muted-foreground">
          {localize(lang, "Защищено:", "Guarded:")} {summary.guarded_items}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {Object.entries(summary.owners).map(([owner, count]) => (
          <StatusBadge key={owner} label={`${ownerLabel(owner, lang)} ${count}`} tone={ownerTone(owner)} />
        ))}
      </div>
    </div>
  );
}

export function OwnershipPanel({ lang, ownership }: { lang: string; ownership: KubernetesAdminOwnershipContext }) {
  return (
    <div className="mb-4 rounded-lg border border-border/70 bg-background/45 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={ownerLabel(ownership.owner, lang)} tone={ownerTone(ownership.owner)} />
        <StatusBadge label={ownership.change_path} tone="neutral" />
        <StatusBadge label={ownership.direct_apply_policy} tone={ownership.direct_apply_policy === "blocked_by_default" ? "warning" : "neutral"} />
        <StatusBadge label={ownership.confidence} tone="info" />
      </div>
      <div className="mt-3 grid gap-3 text-xs text-muted-foreground md:grid-cols-3">
        <div>
          <div className="font-medium text-foreground">{localize(lang, "Правильный путь", "Change path")}</div>
          <div className="mt-1">{changePathText(lang, ownership.change_path)}</div>
        </div>
        <div>
          <div className="font-medium text-foreground">{localize(lang, "Режим сейчас", "Current mode")}</div>
          <div className="mt-1">{ownership.current_mode}</div>
        </div>
        <div>
          <div className="font-medium text-foreground">{localize(lang, "Подтверждение", "Evidence")}</div>
          <div className="mt-1">{ownership.evidence.length ? ownership.evidence.join(", ") : "-"}</div>
        </div>
      </div>
      {ownership.warnings.length ? (
        <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          {ownership.warnings.join(" ")}
        </div>
      ) : null}
    </div>
  );
}

export function ownerLabel(owner: string, lang = "en") {
  if (owner === "devtron") return "Devtron";
  if (owner === "fleet") return "Fleet";
  if (owner === "rancher") return "Rancher";
  if (owner === "external") return localize(lang, "Внешний", "External");
  return localize(lang, "Неизвестен", "Unknown");
}

export function ownerTone(owner: string): StatusTone {
  if (owner === "devtron" || owner === "fleet") return "warning";
  if (owner === "rancher") return "success";
  if (owner === "external") return "info";
  return "neutral";
}

function changePathText(lang: string, changePath: string) {
  if (changePath === "devtron_app_flow") return localize(lang, "Менять через Devtron AppOps в WebTerm.", "Use the Devtron AppOps flow in WebTerm.");
  if (changePath === "fleet_gitops_or_mr") return localize(lang, "Менять через развёртывание GitOps/Fleet в WebTerm.", "Use the GitOps/Fleet rollout flow in WebTerm.");
  if (changePath === "external_owner_flow") return localize(lang, "Сначала подтвердить внешнего владельца.", "Confirm the external owner first.");
  return localize(lang, "Разрешён только просмотр; изменения отключены.", "Read-only access; changes are disabled.");
}
