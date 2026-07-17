import { ShieldCheck } from "lucide-react";

import type { InsightCertificate } from "@/api/monitoring-insights";
import { StatusBadge } from "@/components/ui/page-shell";
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

/** Bare certificate list for the insights rail. */
export function CertificatesList({ certificates }: { certificates: InsightCertificate[] }) {
  const { lang } = useI18n();
  const now = Date.now();

  if (certificates.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
        <ShieldCheck className="h-5 w-5 text-muted-foreground/50" />
        <p className="text-xs text-muted-foreground">
          {localize(
            lang,
            "Сертификаты не найдены. Сканер проверяет TLS-порты каждые 6 часов.",
            "No certificates found. The scanner probes TLS ports every 6 hours.",
          )}
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-1.5">
      {certificates.map((cert) => {
        const changedRecently =
          cert.changed_at !== null &&
          now - new Date(cert.changed_at).getTime() <= RECENT_CHANGE_DAYS * 86400_000;
        return (
          <li key={cert.id} className="flex items-center gap-2.5 rounded-sm border border-border bg-surface-1/60 px-2.5 py-2">
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium text-foreground">{certCommonName(cert)}</div>
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
  );
}
