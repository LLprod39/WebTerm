import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowDownAZ, CheckCircle2, Globe, Info, KeyRound, Server, ShieldCheck, UserPlus, XCircle } from "lucide-react";

import { fetchSettings, saveSettings } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n";
import { getAccessProfileLabel } from "@/lib/accessUiText";

function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-foreground">
      {children}
    </label>
  );
}

function FieldHint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1.5 max-w-full break-words text-xs leading-5 text-muted-foreground">{children}</p>;
}

function StatusIndicator({ active }: { active: boolean }) {
  const { t } = useI18n();
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-semibold ${
      active
        ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
        : "border-border/50 bg-secondary/40 text-muted-foreground"
    }`}>
      {active ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {active ? t("sso.active") : t("sso.inactive")}
    </span>
  );
}

function SsoReadinessBanner({
  enabled,
  headerReady,
}: {
  enabled: boolean;
  headerReady: boolean;
}) {
  const { t } = useI18n();
  const tone = !headerReady ? "danger" : enabled ? "success" : "info";
  const Icon = !headerReady ? AlertCircle : enabled ? CheckCircle2 : Info;
  const title = !headerReady
    ? t("sso.status_error_title")
    : enabled
      ? t("sso.status_ready_title")
      : t("sso.status_off_title");
  const description = !headerReady
    ? t("sso.status_error_desc")
    : enabled
      ? t("sso.status_ready_desc")
      : t("sso.status_off_desc");
  const toneClass = {
    danger: "border-destructive/30 bg-destructive/10 text-destructive",
    success: "border-success/30 bg-success/10 text-success",
    info: "border-info/30 bg-info/10 text-info",
  }[tone];

  return (
    <div className={`rounded-xl border px-4 py-3 ${toneClass}`}>
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0">
          <div className="text-sm font-semibold">{title}</div>
          <p className="mt-1 text-sm leading-6 text-foreground/80">{description}</p>
        </div>
      </div>
    </div>
  );
}

export default function SettingsSSOPage() {
  const { t, lang } = useI18n();
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [testHeaderValue, setTestHeaderValue] = useState("");
  const [testHeaderResult, setTestHeaderResult] = useState<{ ok: boolean; message: string } | null>(null);

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
    setTestHeaderResult(null);
  };

  const headerReady = Boolean(currentForm.domain_auth_header.trim());
  const canEnableSso = headerReady && Boolean(currentForm.domain_auth_default_profile);

  const handleTestHeader = () => {
    const header = currentForm.domain_auth_header.trim();
    const rawUsername = testHeaderValue.trim();
    if (!header) {
      setTestHeaderResult({ ok: false, message: t("sso.test_missing_header") });
      return;
    }
    if (!rawUsername) {
      setTestHeaderResult({ ok: false, message: t("sso.test_missing_value") });
      return;
    }
    const normalized = currentForm.domain_auth_lowercase_usernames ? rawUsername.toLowerCase() : rawUsername;
    setTestHeaderResult({ ok: true, message: `${header}: ${normalized}` });
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
    return <div className="p-6 text-sm text-destructive">{t("sso.load_error")}</div>;
  }

  return (
    <div className="space-y-6 pb-10">
      {/* ── Header ── */}
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
            <Globe className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">{t("sso.title")}</h1>
            <p className="break-words text-sm leading-6 text-muted-foreground">{t("sso.description")}</p>
          </div>
        </div>
        <StatusIndicator active={currentForm.domain_auth_enabled} />
      </div>

      <SsoReadinessBanner enabled={currentForm.domain_auth_enabled} headerReady={headerReady} />

      {/* ── How it works ── */}
      <div className="rounded-xl border border-primary/10 bg-primary/4 px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-500/12 text-blue-400 mt-0.5">
            <Info className="h-4 w-4" />
          </div>
          <div className="min-w-0 text-sm leading-relaxed text-muted-foreground/70">
            <p>
              {t("sso.how_it_works")}
            </p>
            <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">
              {t("sso.supported_scenarios")}
            </p>
          </div>
        </div>
      </div>

      {/* ── Main settings ── */}
      <div className="space-y-1">
        <h2 className="mb-3 text-base font-semibold text-foreground">
          {t("sso.core_settings")}
        </h2>

        <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
          {/* Enable toggle */}
          <div className="flex items-center justify-between gap-4 rounded-lg border border-border/50 bg-secondary/20 px-4 py-3.5">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/12 text-emerald-400">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground/90">
                  {t("sso.enable")}
                </div>
                <div className="break-words text-xs leading-4 text-muted-foreground/50">
                  {t("sso.enable_desc")}
                </div>
              </div>
            </div>
            <Switch
              checked={currentForm.domain_auth_enabled}
              disabled={!canEnableSso && !currentForm.domain_auth_enabled}
              onCheckedChange={(v) => {
                if (v && !canEnableSso) return;
                update("domain_auth_enabled", v);
              }}
            />
          </div>

          {/* Header name */}
          <div>
            <FieldLabel htmlFor="sso-header">
              <div className="flex items-center gap-2">
                <Server className="h-3 w-3" />
                {t("sso.http_header")}
              </div>
            </FieldLabel>
            <Input
              id="sso-header"
              value={currentForm.domain_auth_header}
              onChange={(e) => update("domain_auth_header", e.target.value)}
              placeholder="REMOTE_USER"
              className="h-9 bg-secondary/30 border-border font-mono text-sm"
            />
            <FieldHint>
              {t("sso.http_header_hint")}
            </FieldHint>
          </div>

          <div className="rounded-lg border border-border/60 bg-secondary/10 px-4 py-3">
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
              <div>
                <FieldLabel htmlFor="sso-test-value">{t("sso.test_header")}</FieldLabel>
                <Input
                  id="sso-test-value"
                  value={testHeaderValue}
                  onChange={(event) => {
                    setTestHeaderValue(event.target.value);
                    setTestHeaderResult(null);
                  }}
                  placeholder="DOMAIN\\Operator"
                  className="h-10 border-border bg-background/70 font-mono text-sm"
                />
                <FieldHint>{t("sso.test_header_hint")}</FieldHint>
              </div>
              <Button type="button" variant="outline" onClick={handleTestHeader} className="h-10">
                {t("sso.test_header_action")}
              </Button>
            </div>
            {testHeaderResult ? (
              <div className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
                testHeaderResult.ok
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-destructive/30 bg-destructive/10 text-destructive"
              }`}
              >
                {testHeaderResult.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
                <span className="break-words">{testHeaderResult.message}</span>
              </div>
            ) : null}
          </div>

          {/* Default profile */}
          <div>
            <FieldLabel htmlFor="sso-profile">
              <div className="flex items-center gap-2">
                <KeyRound className="h-3 w-3" />
                {t("sso.default_profile")}
              </div>
            </FieldLabel>
            <Select
              value={currentForm.domain_auth_default_profile}
              onValueChange={(value) => update("domain_auth_default_profile", value)}
            >
              <SelectTrigger id="sso-profile" className="h-10 border-border bg-secondary/30">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="server_only">{getAccessProfileLabel(lang, "server_only")}</SelectItem>
                <SelectItem value="admin_full">{getAccessProfileLabel(lang, "admin_full")}</SelectItem>
                <SelectItem value="custom">{getAccessProfileLabel(lang, "custom")}</SelectItem>
              </SelectContent>
            </Select>
            <FieldHint>
              {t("sso.default_profile_hint")}
            </FieldHint>
          </div>
        </div>
      </div>

      {/* ── Behavior settings ── */}
      <div className="space-y-1">
        <h2 className="mb-3 text-base font-semibold text-foreground">
          {t("sso.behavior")}
        </h2>

        <div className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
          {/* Auto-create */}
          <div className="flex items-center justify-between gap-4 rounded-lg border border-border/50 bg-secondary/20 px-4 py-3.5">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/12 text-violet-400">
                <UserPlus className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground/90">
                  {t("sso.auto_create")}
                </div>
                <div className="break-words text-xs leading-4 text-muted-foreground/50">
                  {t("sso.auto_create_desc")}
                </div>
              </div>
            </div>
            <Switch
              checked={currentForm.domain_auth_auto_create}
              onCheckedChange={(v) => update("domain_auth_auto_create", v)}
            />
          </div>

          {/* Lowercase */}
          <div className="flex items-center justify-between gap-4 rounded-lg border border-border/50 bg-secondary/20 px-4 py-3.5">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/12 text-amber-400">
                <ArrowDownAZ className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground/90">
                  {t("sso.lowercase")}
                </div>
                <div className="break-words text-xs leading-4 text-muted-foreground/50">
                  {t("sso.lowercase_desc")}
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
      <details className="group rounded-xl border border-border bg-card p-5 shadow-sm">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-base font-semibold text-foreground">
          <span>{t("sso.proxy_examples")}</span>
          <span className="text-sm font-normal text-muted-foreground group-open:hidden">{t("sso.proxy_examples_show")}</span>
          <span className="hidden text-sm font-normal text-muted-foreground group-open:inline">{t("sso.proxy_examples_hide")}</span>
        </summary>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-border/60 bg-secondary/10 p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-500/12 text-emerald-400">
                <Globe className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold text-foreground/90">Nginx + Kerberos</span>
            </div>
            <pre className="rounded-lg bg-black/30 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground/70 font-mono overflow-x-auto">
{`location / {
  auth_gss on;
  auth_gss_realm CORP.EXAMPLE.COM;
  proxy_set_header REMOTE_USER $remote_user;
  proxy_pass http://webterm:9000;
}`}
            </pre>
          </div>

          <div className="rounded-xl border border-border/60 bg-secondary/10 p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-500/12 text-blue-400">
                <Globe className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold text-foreground/90">Keycloak Proxy</span>
            </div>
            <pre className="rounded-lg bg-black/30 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground/70 font-mono overflow-x-auto">
{`location / {
  auth_request /oauth2/auth;
  auth_request_set $user $upstream_http_x_auth_request_user;
  proxy_set_header X-Forwarded-User $user;
  proxy_pass http://webterm:9000;
}`}
            </pre>
            <p className="mt-2 text-xs text-muted-foreground">{t("sso.example_header")}: X-Forwarded-User</p>
          </div>

          <div className="rounded-xl border border-border/60 bg-secondary/10 p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-500/12 text-amber-400">
                <Globe className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold text-foreground/90">Apache + mod_auth_kerb</span>
            </div>
            <pre className="rounded-lg bg-black/30 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground/70 font-mono overflow-x-auto">
{`<Location />
  AuthType Kerberos
  KrbAuthRealms CORP.EXAMPLE.COM
  Require valid-user
  RequestHeader set REMOTE_USER %{REMOTE_USER}e
</Location>`}
            </pre>
          </div>

          <div className="rounded-xl border border-border/60 bg-secondary/10 p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-violet-500/12 text-violet-400">
                <Globe className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold text-foreground/90">Traefik ForwardAuth</span>
            </div>
            <pre className="rounded-lg bg-black/30 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground/70 font-mono overflow-x-auto">
{`labels:
  traefik.http.middlewares.auth.forwardauth.address: https://auth.corp/verify
  traefik.http.middlewares.auth.forwardauth.authResponseHeaders: X-Forwarded-User`}
            </pre>
            <p className="mt-2 text-xs text-muted-foreground">{t("sso.example_header")}: X-Forwarded-User</p>
          </div>
        </div>
      </details>

      {/* ── Sticky save bar ── */}
      {dirty && (
        <div className="sticky bottom-4 flex items-center justify-between gap-4 rounded-xl border border-primary/20 bg-background/95 backdrop-blur-lg px-5 py-3 shadow-lg">
          <p className="text-sm text-muted-foreground/70">
            {t("sso.unsaved")}
          </p>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={handleReset} disabled={saving}>
              {t("sso.reset")}
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? t("sso.saving") : t("sso.save")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
