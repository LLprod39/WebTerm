import { CheckCircle2, Server, XCircle } from "lucide-react";

export interface LdapStatus {
  enabled: boolean;
  status: "disabled" | "enabled" | "misconfigured";
  severity: "ready" | "warning" | "error";
  backend_loaded: boolean;
  server_configured: boolean;
  search_base_configured: boolean;
  bind_dn_configured: boolean;
  bind_password_configured: boolean;
  start_tls: boolean;
  ignore_cert: boolean;
  ca_cert_configured: boolean;
  missing: string[];
}

function LdapStatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${
        ok
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
          : "border-border/60 bg-secondary/30 text-muted-foreground"
      }`}
    >
      {ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {label}
    </span>
  );
}

export function LdapStatusPanel({ ldapStatus }: { ldapStatus?: LdapStatus }) {
  const status = ldapStatus ?? {
    enabled: false,
    status: "disabled",
    severity: "ready",
    backend_loaded: false,
    server_configured: false,
    search_base_configured: false,
    bind_dn_configured: false,
    bind_password_configured: false,
    start_tls: false,
    ignore_cert: false,
    ca_cert_configured: false,
    missing: [],
  };
  const enabled = status.enabled;
  const broken = status.severity === "error";
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-primary" />
            <h2 className="text-base font-semibold text-foreground">Вход через LDAP</h2>
            <span
              className={`inline-flex rounded-md border px-2 py-0.5 text-xs font-semibold ${
                broken
                  ? "border-destructive/30 bg-destructive/10 text-destructive"
                  : enabled
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                    : "border-border/60 bg-secondary/30 text-muted-foreground"
              }`}
            >
              {broken ? "Ошибка настройки" : enabled ? "Включён" : "Выключен"}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            LDAP настраивается в окружении запуска. После изменения перезапустите сервер WebTerm.
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <LdapStatusPill ok={status.backend_loaded} label="Модуль загружен" />
        <LdapStatusPill ok={status.server_configured} label="Сервер LDAP" />
        <LdapStatusPill ok={status.search_base_configured} label="Область поиска" />
        <LdapStatusPill ok={!status.bind_dn_configured || status.bind_password_configured} label="Учётные данные" />
        <LdapStatusPill ok={status.start_tls || status.ca_cert_configured || status.ignore_cert || !enabled} label="TLS и сертификаты" />
      </div>

      {status.missing.length ? (
        <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
          Не заданы параметры: {status.missing.join(", ")}
        </div>
      ) : null}
    </div>
  );
}
