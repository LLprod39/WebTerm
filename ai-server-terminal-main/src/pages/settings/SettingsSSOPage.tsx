import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe, ShieldCheck, Server, UserPlus, ArrowDownAZ, KeyRound, Info, CheckCircle2, XCircle } from "lucide-react";

import { fetchSettings, saveSettings, type SettingsConfig } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n";
import { getAccessProfileLabel } from "@/lib/accessUiText";

const SELECT_CLASS =
  "h-9 w-full rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 text-sm text-foreground outline-none ring-0 transition-all focus:border-primary/40 focus:ring-1 focus:ring-primary/30";

function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
      {children}
    </label>
  );
}

function FieldHint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground/50">{children}</p>;
}

function StatusIndicator({ active }: { active: boolean }) {
  return (
    <div className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ${active ? "bg-emerald-500/10 text-emerald-400" : "bg-white/[0.04] text-muted-foreground/60"}`}>
      {active ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {active ? "Активен" : "Выключен"}
    </div>
  );
}

export default function SettingsSSOPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });

  const config = data?.config;

  const [form, setForm] = useState<{
    domain_auth_enabled: boolean;
    domain_auth_header: string;
    domain_auth_auto_create: boolean;
    domain_auth_lowercase_usernames: boolean;
    domain_auth_default_profile: string;
  } | null>(null);

  // Initialize form from config on first load
  const currentForm = form ?? {
    domain_auth_enabled: config?.domain_auth_enabled ?? false,
    domain_auth_header: config?.domain_auth_header ?? "REMOTE_USER",
    domain_auth_auto_create: config?.domain_auth_auto_create ?? true,
    domain_auth_lowercase_usernames: config?.domain_auth_lowercase_usernames ?? true,
    domain_auth_default_profile: config?.domain_auth_default_profile ?? "server_only",
  };

  const update = <K extends keyof typeof currentForm>(key: K, value: (typeof currentForm)[K]) => {
    setForm({ ...currentForm, [key]: value });
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveSettings(currentForm);
      setDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setForm(null);
    setDirty(false);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (error || !config) {
    return <div className="p-6 text-sm text-destructive">Не удалось загрузить настройки</div>;
  }

  return (
    <div className="space-y-6 pb-10">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            {lang === "ru" ? "Доменная авторизация" : "Domain Authentication"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground/70">
            {lang === "ru"
              ? "Настройка SSO через HTTP-заголовок от реверс-прокси (Nginx, Apache, Keycloak, ADFS)"
              : "Configure SSO via HTTP header from reverse proxy (Nginx, Apache, Keycloak, ADFS)"}
          </p>
        </div>
        <StatusIndicator active={currentForm.domain_auth_enabled} />
      </div>

      {/* ── How it works ── */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-500/12 text-blue-400 mt-0.5">
            <Info className="h-4 w-4" />
          </div>
          <div className="text-sm leading-relaxed text-muted-foreground/70">
            <p>
              {lang === "ru"
                ? "Доменная авторизация позволяет автоматически входить пользователям, которые уже прошли аутентификацию через корпоративный SSO-провайдер. Реверс-прокси передает имя пользователя в HTTP-заголовке, и система автоматически находит или создает аккаунт."
                : "Domain authentication allows automatic login for users already authenticated via a corporate SSO provider. The reverse proxy passes the username in an HTTP header, and the system automatically finds or creates the account."}
            </p>
            <p className="mt-2 text-xs text-muted-foreground/50">
              Поддерживаемые сценарии: Nginx + Kerberos, Apache + mod_auth_kerb, Keycloak proxy, ADFS + WAP, Traefik + ForwardAuth
            </p>
          </div>
        </div>
      </div>

      {/* ── Main settings ── */}
      <div className="space-y-1">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-3">
          {lang === "ru" ? "Основные параметры" : "Core settings"}
        </h2>

        <div className="space-y-4 rounded-xl border border-white/[0.06] bg-white/[0.015] p-5">
          {/* Enable toggle */}
          <div className="flex items-center justify-between gap-4 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3.5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/12 text-emerald-400">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div>
                <div className="text-sm font-medium text-foreground/90">
                  {lang === "ru" ? "Включить доменную авторизацию" : "Enable domain authentication"}
                </div>
                <div className="text-[11px] text-muted-foreground/50">
                  {lang === "ru"
                    ? "Автовход через HTTP-заголовок от реверс-прокси"
                    : "Auto-login via HTTP header from reverse proxy"}
                </div>
              </div>
            </div>
            <Switch
              checked={currentForm.domain_auth_enabled}
              onCheckedChange={(v) => update("domain_auth_enabled", v)}
            />
          </div>

          {/* Header name */}
          <div>
            <FieldLabel htmlFor="sso-header">
              <div className="flex items-center gap-2">
                <Server className="h-3 w-3" />
                {lang === "ru" ? "HTTP-заголовок" : "HTTP Header"}
              </div>
            </FieldLabel>
            <Input
              id="sso-header"
              value={currentForm.domain_auth_header}
              onChange={(e) => update("domain_auth_header", e.target.value)}
              placeholder="REMOTE_USER"
              className="h-9 bg-white/[0.03] border-white/[0.06] font-mono text-sm"
            />
            <FieldHint>
              {lang === "ru"
                ? "Имя HTTP-заголовка, который будет содержать логин пользователя. Типовые: REMOTE_USER, X-Forwarded-User, X-Remote-User, HTTP_X_REMOTE_USER"
                : "HTTP header name containing the username. Common values: REMOTE_USER, X-Forwarded-User, X-Remote-User"}
            </FieldHint>
          </div>

          {/* Default profile */}
          <div>
            <FieldLabel htmlFor="sso-profile">
              <div className="flex items-center gap-2">
                <KeyRound className="h-3 w-3" />
                {lang === "ru" ? "Профиль для новых пользователей" : "Default profile for new users"}
              </div>
            </FieldLabel>
            <select
              id="sso-profile"
              value={currentForm.domain_auth_default_profile}
              onChange={(e) => update("domain_auth_default_profile", e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="server_only">{getAccessProfileLabel(lang, "server_only")}</option>
              <option value="admin_full">{getAccessProfileLabel(lang, "admin_full")}</option>
              <option value="custom">{getAccessProfileLabel(lang, "custom")}</option>
            </select>
            <FieldHint>
              {lang === "ru"
                ? "Какой профиль доступа назначить автоматически созданным через SSO пользователям"
                : "Which access profile to assign to users auto-created via SSO"}
            </FieldHint>
          </div>
        </div>
      </div>

      {/* ── Behavior settings ── */}
      <div className="space-y-1">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-3">
          {lang === "ru" ? "Поведение" : "Behavior"}
        </h2>

        <div className="space-y-3 rounded-xl border border-white/[0.06] bg-white/[0.015] p-5">
          {/* Auto-create */}
          <div className="flex items-center justify-between gap-4 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3.5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/12 text-violet-400">
                <UserPlus className="h-4 w-4" />
              </div>
              <div>
                <div className="text-sm font-medium text-foreground/90">
                  {lang === "ru" ? "Автоматическое создание пользователя" : "Auto-create users"}
                </div>
                <div className="text-[11px] text-muted-foreground/50">
                  {lang === "ru"
                    ? "Если пользователь не найден в базе, создать аккаунт автоматически"
                    : "If user is not found in DB, create account automatically"}
                </div>
              </div>
            </div>
            <Switch
              checked={currentForm.domain_auth_auto_create}
              onCheckedChange={(v) => update("domain_auth_auto_create", v)}
            />
          </div>

          {/* Lowercase */}
          <div className="flex items-center justify-between gap-4 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3.5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/12 text-amber-400">
                <ArrowDownAZ className="h-4 w-4" />
              </div>
              <div>
                <div className="text-sm font-medium text-foreground/90">
                  {lang === "ru" ? "Приводить логин к нижнему регистру" : "Lowercase usernames"}
                </div>
                <div className="text-[11px] text-muted-foreground/50">
                  {lang === "ru"
                    ? "Нормализация имён (DOMAIN\\User → domain\\user)"
                    : "Normalize usernames (DOMAIN\\User → domain\\user)"}
                </div>
              </div>
            </div>
            <Switch
              checked={currentForm.domain_auth_lowercase_usernames}
              onCheckedChange={(v) => update("domain_auth_lowercase_usernames", v)}
            />
          </div>
        </div>
      </div>

      {/* ── Typical configs reference ── */}
      <div className="space-y-1">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-3">
          {lang === "ru" ? "Примеры конфигурации прокси" : "Proxy config examples"}
        </h2>

        <div className="grid gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-500/12 text-emerald-400">
                <Globe className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold text-foreground/90">Nginx + Kerberos</span>
            </div>
            <pre className="rounded-lg bg-black/30 px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground/70 font-mono overflow-x-auto">
{`location / {
  auth_gss on;
  auth_gss_realm CORP.EXAMPLE.COM;
  proxy_set_header REMOTE_USER $remote_user;
  proxy_pass http://webterm:9000;
}`}
            </pre>
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-500/12 text-blue-400">
                <Globe className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold text-foreground/90">Keycloak Proxy</span>
            </div>
            <pre className="rounded-lg bg-black/30 px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground/70 font-mono overflow-x-auto">
{`location / {
  auth_request /oauth2/auth;
  auth_request_set $user $upstream_http_x_auth_request_user;
  proxy_set_header X-Forwarded-User $user;
  proxy_pass http://webterm:9000;
}`}
            </pre>
            <p className="mt-2 text-[10px] text-muted-foreground/40">Заголовок: X-Forwarded-User</p>
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-500/12 text-amber-400">
                <Globe className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold text-foreground/90">Apache + mod_auth_kerb</span>
            </div>
            <pre className="rounded-lg bg-black/30 px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground/70 font-mono overflow-x-auto">
{`<Location />
  AuthType Kerberos
  KrbAuthRealms CORP.EXAMPLE.COM
  Require valid-user
  RequestHeader set REMOTE_USER %{REMOTE_USER}e
</Location>`}
            </pre>
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-violet-500/12 text-violet-400">
                <Globe className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold text-foreground/90">Traefik ForwardAuth</span>
            </div>
            <pre className="rounded-lg bg-black/30 px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground/70 font-mono overflow-x-auto">
{`labels:
  traefik.http.middlewares.auth.forwardauth.address: https://auth.corp/verify
  traefik.http.middlewares.auth.forwardauth.authResponseHeaders: X-Forwarded-User`}
            </pre>
            <p className="mt-2 text-[10px] text-muted-foreground/40">Заголовок: X-Forwarded-User</p>
          </div>
        </div>
      </div>

      {/* ── Sticky save bar ── */}
      {dirty && (
        <div className="sticky bottom-4 flex items-center justify-between gap-4 rounded-xl border border-primary/20 bg-background/95 backdrop-blur-lg px-5 py-3 shadow-lg">
          <p className="text-sm text-muted-foreground/70">
            {lang === "ru" ? "Есть несохранённые изменения" : "You have unsaved changes"}
          </p>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={handleReset} disabled={saving}>
              {lang === "ru" ? "Сбросить" : "Reset"}
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving
                ? (lang === "ru" ? "Сохранение..." : "Saving...")
                : (lang === "ru" ? "Сохранить" : "Save")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
