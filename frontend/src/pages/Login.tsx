import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  Eye,
  EyeOff,
  LockKeyhole,
  Server,
  ShieldCheck,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authLogin, type AuthLoginResponse } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { normalizeInternalRedirectPath } from "@/lib/safeRedirect";
import { cn } from "@/lib/utils";

export default function Login() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t, lang, setLang } = useI18n();
  const [searchParams] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorDetail, setErrorDetail] = useState("");
  const [loading, setLoading] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const requestedNext = searchParams.get("next") || "";
  const nextFromUrl = normalizeInternalRedirectPath(requestedNext);

  const completeLogin = async (result: AuthLoginResponse) => {
    queryClient.setQueryData(["auth", "session"], {
      authenticated: true,
      user: result.user,
    });
    await queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    const nextUrl = requestedNext
      ? nextFromUrl ?? "/dashboard"
      : normalizeInternalRedirectPath(result.next_url) ?? "/dashboard";
    navigate(nextUrl, { replace: true });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorDetail("");
    setLoading(true);
    try {
      // Backend enforces LDAP for all users except local admin.
      await completeLogin(await authLogin(username, password, "auto"));
    } catch (error) {
      setErrorDetail(error instanceof Error ? error.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell-bg min-h-dvh text-foreground">
      <div className="grid min-h-dvh lg:grid-cols-[42fr_58fr]">
        <section className="relative hidden overflow-hidden border-r border-border lg:flex lg:flex-col lg:justify-between">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse 80% 50% at 0% 0%, hsl(var(--primary) / 0.08), transparent 55%), hsl(var(--surface-0))",
            }}
          />
          <div aria-hidden className="absolute inset-y-0 left-0 w-1 bg-primary" />

          <div className="relative px-10 py-10">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-sm border border-primary bg-primary font-display text-sm font-bold text-primary-foreground shadow-elev-1">
                W
              </div>
              <div>
                <div className="font-display text-[15px] font-bold leading-5 tracking-tight text-foreground">WebTerm</div>
                <div className="text-2xs uppercase tracking-[0.12em] text-muted-foreground">{t("login.brand_subtitle")}</div>
              </div>
            </div>

            <div className="mt-20 max-w-xl">
              <p className="text-2xs font-medium uppercase tracking-[0.14em] text-primary">{t("login.kicker")}</p>
              <h2 className="mt-3 font-display text-[1.9rem] font-bold leading-[1.15] tracking-tight text-foreground">
                {t("login.hero_title")}
              </h2>
              <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">{t("login.hero_desc")}</p>
            </div>
          </div>

          <div className="relative grid gap-2 px-10 pb-10 text-sm text-muted-foreground">
            <div className="flex items-center gap-3 rounded-sm border border-border bg-card px-3.5 py-2.5 shadow-elev-1">
              <Server className="h-4 w-4 shrink-0 text-primary" />
              <span className="leading-5">{t("login.bullet_ssh")}</span>
            </div>
            <div className="flex items-center gap-3 rounded-sm border border-border bg-card px-3.5 py-2.5 shadow-elev-1">
              <ShieldCheck className="h-4 w-4 shrink-0 text-primary" />
              <span className="leading-5">Доменный вход через LDAP / Active Directory</span>
            </div>
            <div className="flex items-center gap-3 rounded-sm border border-border bg-card px-3.5 py-2.5 shadow-elev-1">
              <LockKeyhole className="h-4 w-4 shrink-0 text-primary" />
              <span className="leading-5">{t("login.bullet_session")}</span>
            </div>
          </div>
        </section>

        <main className="relative flex min-h-dvh items-center justify-center px-5 py-8">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-70 lg:opacity-50"
            style={{
              background:
                "radial-gradient(ellipse 60% 40% at 70% 20%, hsl(var(--primary) / 0.06), transparent 55%), radial-gradient(ellipse 40% 35% at 20% 90%, hsl(var(--ai) / 0.05), transparent 50%)",
            }}
          />

          <div className="relative w-full max-w-[440px]">
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-sm border border-primary bg-primary font-display text-sm font-bold text-primary-foreground shadow-elev-1 lg:hidden">
                  W
                </div>
                <p className="text-2xs font-medium uppercase tracking-[0.14em] text-primary">{t("login.eyebrow")}</p>
                <h1 className="type-h1 mt-2 text-foreground">{t("login.title")}</h1>
                <p className="mt-1.5 text-sm leading-5 text-muted-foreground">
                  Войдите доменной учётной записью AD
                </p>
              </div>

              <div className="flex shrink-0 items-center gap-0.5 border border-border p-0.5 text-2xs uppercase tracking-wider">
                {(["en", "ru"] as const).map((code) => (
                  <button
                    key={code}
                    type="button"
                    onClick={() => setLang(code)}
                    aria-pressed={lang === code}
                    className={cn(
                      "rounded-sm px-2.5 py-1.5 transition-colors",
                      lang === code
                        ? "bg-primary font-medium text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {code}
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-hidden rounded-sm border border-border-strong bg-card shadow-elev-2">
              <div className="border-b border-border bg-surface-0 px-5 py-3 text-xs text-muted-foreground">
                LDAP / Active Directory
              </div>

              <div className="px-5 py-5 sm:px-6">
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="username" className="text-[13px] font-medium text-muted-foreground">
                      {t("login.username")}
                    </Label>
                    <Input
                      id="username"
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      placeholder="name.surname"
                      className="h-11"
                      autoComplete="username"
                      autoFocus
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="password" className="text-[13px] font-medium text-muted-foreground">
                      {t("login.password")}
                    </Label>
                    <div className="relative">
                      <Input
                        id="password"
                        type={passwordVisible ? "text" : "password"}
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        onKeyDown={(event) => setCapsLock(event.getModifierState("CapsLock"))}
                        onKeyUp={(event) => setCapsLock(event.getModifierState("CapsLock"))}
                        onBlur={() => setCapsLock(false)}
                        className="h-11 pr-12"
                        autoComplete="current-password"
                      />
                      <button
                        type="button"
                        className="absolute right-0.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => setPasswordVisible((visible) => !visible)}
                        aria-label={passwordVisible ? t("login.hide_password") : t("login.show_password")}
                        title={passwordVisible ? t("login.hide_password") : t("login.show_password")}
                      >
                        {passwordVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    {capsLock ? (
                      <p className="flex items-center gap-2 text-xs leading-5 text-warning">
                        <AlertCircle className="h-3.5 w-3.5" />
                        {t("login.caps_lock")}
                      </p>
                    ) : null}
                  </div>

                  <LoginError detail={errorDetail} />

                  <Button
                    type="submit"
                    className="h-11 w-full"
                    disabled={loading || !username.trim() || !password.trim()}
                    loading={loading}
                  >
                    {t("login.submit")}
                  </Button>
                </form>
              </div>
            </div>

            <p className="mt-5 text-sm leading-5 text-muted-foreground/80">{t("login.help")}</p>
          </div>
        </main>
      </div>
    </div>
  );
}

function LoginError({ detail }: { detail: string }) {
  const { t } = useI18n();
  if (!detail) return null;

  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive shadow-elev-1">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0">
          <div className="font-medium leading-5">{t("login.error_title")}</div>
          <div className="mt-0.5 text-[13px] leading-5 text-destructive/90">{t("login.error_desc")}</div>
          <details className="mt-2 text-xs text-destructive/80">
            <summary className="cursor-pointer select-none">{t("login.error_details")}</summary>
            <p className="mt-1 break-words">{detail}</p>
          </details>
        </div>
      </div>
    </div>
  );
}
