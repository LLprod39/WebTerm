import { ShieldCheck } from "lucide-react";

import type { InsightCertificate } from "@/api/monitoring-insights";
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useI18n, localize } from "@/lib/i18n";

function daysBadge(lang: string, cert: InsightCertificate) {
  if (cert.days_left === null) {
    return <StatusBadge label={localize(lang, "нет даты", "no date")} tone="neutral" dot={false} />;
  }
  const days = Math.floor(cert.days_left);
  if (days < 0) {
    return <StatusBadge label={localize(lang, "истёк", "expired")} tone="danger" />;
  }
  if (days <= 7) {
    return <StatusBadge label={localize(lang, `${days} дн`, `${days} d`)} tone="danger" dot={false} />;
  }
  if (days <= 30) {
    return <StatusBadge label={localize(lang, `${days} дн`, `${days} d`)} tone="warning" dot={false} />;
  }
  return <StatusBadge label={localize(lang, `${days} дн`, `${days} d`)} tone="success" dot={false} />;
}

function certCommonName(cert: InsightCertificate): string {
  const match = /CN\s*=\s*([^,/]+)/i.exec(cert.subject || "");
  return (match?.[1] || cert.subject || "—").trim();
}

const RECENT_CHANGE_DAYS = 7;

export function CertificatesPanel({ certificates }: { certificates: InsightCertificate[] }) {
  const { lang } = useI18n();
  const now = Date.now();

  return (
    <SectionCard
      title={localize(lang, "Сертификаты", "Certificates")}
      description={localize(
        lang,
        "TLS на слушающих портах, сортировка по сроку",
        "TLS on listening ports, sorted by expiry",
      )}
      icon={<ShieldCheck className="h-4 w-4" />}
      bodyClassName="p-0"
    >
      {certificates.length === 0 ? (
        <div className="px-4 py-4">
          <EmptyState
            icon={<ShieldCheck className="h-5 w-5" />}
            title={localize(lang, "Сертификаты не найдены", "No certificates found")}
            description={localize(
              lang,
              "Сканер проверяет слушающие TLS-порты каждые 6 часов.",
              "The scanner probes listening TLS ports every 6 hours.",
            )}
          />
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {certificates.map((cert) => {
            const changedRecently =
              cert.changed_at !== null &&
              now - new Date(cert.changed_at).getTime() <= RECENT_CHANGE_DAYS * 86400_000;
            return (
              <li key={cert.id} className="flex items-center gap-3 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-foreground">{certCommonName(cert)}</div>
                  <div className="mt-0.5 truncate font-mono text-2xs text-muted-foreground">
                    {cert.server_name} · :{cert.port}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {changedRecently ? (
                    <StatusBadge label={localize(lang, "сменился", "changed")} tone="info" dot={false} />
                  ) : null}
                  {daysBadge(lang, cert)}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}
