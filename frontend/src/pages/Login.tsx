import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  Eye,
  EyeOff,
  LockKeyhole,
  Server,
  ShieldCheck,
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authLogin, fetchAuthSession, type AuthLoginResponse } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type AuthMode = "local" | "sso";

export default function Login() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t, lang, setLang } = useI18n();
  const [searchParams] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("local");
  const [errorDetail, setErrorDetail] = useState("");
  const [loading, setLoading] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const nextFromUrl = searchParams.get("next") || "";
  const isLocal = authMode === "local";

  const { data: session } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
    refetchOnMount: "always",
    enabled: !isLocal,
  });

  useEffect(() => {
    if (!isLocal && session?.authenticated) {
      navigate(nextFromUrl || "/dashboard", { replace: true });
    }
  }, [isLocal, session?.authenticated, navigate, nextFromUrl]);

  const completeLogin = async (result: AuthLoginResponse) => {
    queryClient.setQueryData(["auth", "session"], {
      authenticated: true,
      user: result.user,
    });
    await queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    const nextUrl = nextFromUrl || result.next_url || "/dashboard";
    navigate(nextUrl, { replace: true });
  };

  const handleLocalSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorDetail("");
    setLoading(true);
    try {
      await completeLogin(await authLogin(username, password, "local"));
    } catch (error) {
      setErrorDetail(error instanceof Error ? error.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSsoContinue = async () => {
    setErrorDetail("");
    setLoading(true);
    try {
      await completeLogin(await authLogin("", "", "auto"));
    } catch (error) {
      setErrorDetail(error instanceof Error ? error.message : "SSO login failed");
    } finally {
      setLoading(false);
    }
  };

  const selectMode = (mode: AuthMode) => {
    setAuthMode(mode);
    setErrorDetail("");
  };

  return (
    <div className="app-shell-bg min-h-dvh text-foreground">
      <div className="grid min-h-dvh lg:grid-cols-[42fr_58fr]">
        {/* Left brand panel — SoftHeader wash, not heavy chrome */}
        <section className="relative hidden overflow-hidden border-r border-border/50 lg:flex lg:flex-col lg:justify-between">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "linear-gradient(120deg, hsl(var(--primary) / 0.10), transparent 42%), linear-gradient(250deg, hsl(var(--ai) / 0.09), transparent 46%), hsl(var(--surface-1) / 0.55)",
            }}
          />
          <div aria-hidden className="accent-gradient absolute inset-y-0 left-0 w-0.5 opacity-70" />

          <div className="relative px-10 py-10">
            <div className="flex items-center gap-3">
              <div className="accent-gradient flex h-10 w-10 items-center justify-center rounded-lg text-sm font-bold text-white shadow-elev-1">
                W
              </div>
              <div>
                <div className="text-[15px] font-semibold leading-5 text-foreground">WebTermAI</div>
                <div className="text-xs leading-4 text-muted-foreground/80">{t("login.brand_subtitle")}</div>
              </div>
            </div>

            <div className="mt-20 max-w-xl">
              <p className="text-xs font-semibold uppercase tracking-wide text-primary/90">{t("login.kicker")}</p>
              <h2 className="mt-3 text-[1.75rem] font-semibold leading-[2.125rem] tracking-tight text-foreground">
                {t("login.hero_title")}
              </h2>
              <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">{t("login.hero_desc")}</p>
            </div>
          </div>

          <div className="relative grid gap-3 px-10 pb-10 text-sm text-muted-foreground">
            <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-surface-1/40 px-3.5 py-2.5 shadow-elev-1">
              <Server className="h-4 w-4 shrink-0 text-primary" />
              <span className="leading-5">{t("login.bullet_ssh")}</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-surface-1/40 px-3.5 py-2.5 shadow-elev-1">
              <ShieldCheck className="h-4 w-4 shrink-0 text-primary" />
              <span className="leading-5">{t("login.bullet_sso")}</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-surface-1/40 px-3.5 py-2.5 shadow-elev-1">
              <LockKeyhole className="h-4 w-4 shrink-0 text-primary" />
              <span className="leading-5">{t("login.bullet_session")}</span>
            </div>
          </div>
        </section>

        {/* Right form column */}
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
                <div className="accent-gradient mb-5 flex h-10 w-10 items-center justify-center rounded-lg text-sm font-bold text-white shadow-elev-1 lg:hidden">
                  W
                </div>
                <p className="text-xs font-semibold uppercase tracking-wide text-primary/90">{t("login.eyebrow")}</p>
                <h1 className="type-h1 mt-2 text-foreground">{t("login.title")}</h1>
                <p className="mt-1.5 text-sm leading-5 text-muted-foreground">{t("login.subtitle")}</p>
              </div>

              {/* Quiet lang pills — agents filter grammar */}
              <div className="flex shrink-0 items-center gap-0.5 text-sm">
                {(["en", "ru"] as const).map((code) => (
                  <button
                    key={code}
                    type="button"
                    onClick={() => setLang(code)}
                    aria-pressed={lang === code}
                    className={cn(
                      "rounded-md px-2.5 py-1 uppercase transition-colors",
                      lang === code
                        ? "bg-surface-2 font-medium text-foreground shadow-elev-1"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {code}
                  </button>
                ))}
              </div>
            </div>

            {/* Form surface — agent list card grammar */}
            <div className="overflow-hidden rounded-2xl border border-border/50 bg-surface-1/60 shadow-elev-2">
              <div className="flex items-center gap-1 border-b border-border/50 px-3 py-2.5 text-sm">
                {(
                  [
                    { id: "local" as const, label: t("login.local_tab") },
                    { id: "sso" as const, label: t("login.sso_tab") },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => selectMode(tab.id)}
                    aria-pressed={authMode === tab.id}
                    className={cn(
                      "min-h-9 rounded-md px-3 py-1.5 transition-colors",
                      authMode === tab.id
                        ? "bg-surface-2 font-medium text-foreground shadow-elev-1"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="px-5 py-5 sm:px-6">
                {isLocal ? (
                  <form onSubmit={handleLocalSubmit} className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="username" className="text-[13px] font-medium text-muted-foreground">
                        {t("login.username")}
                      </Label>
                      <Input
                        id="username"
                        value={username}
                        onChange={(event) => setUsername(event.target.value)}
                        placeholder="admin"
                        className="h-11 border-border/70 bg-card/70 shadow-elev-1"
                        autoComplete="username"
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
                          className="h-11 border-border/70 bg-card/70 pr-12 shadow-elev-1"
                          autoComplete="current-password"
                        />
                        <button
                          type="button"
                          className="absolute right-0.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                      className="h-11 w-full shadow-elev-1"
                      disabled={loading || !username.trim() || !password.trim()}
                      loading={loading}
                    >
                      {t("login.submit")}
                    </Button>
                  </form>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-start gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary shadow-elev-1">
                        <ShieldCheck className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <h2 className="text-[15px] font-semibold leading-5 text-foreground">{t("login.sso_title")}</h2>
                        <p className="mt-1 text-[13px] leading-5 text-muted-foreground">{t("login.sso_desc")}</p>
                      </div>
                    </div>

                    <div className="rounded-lg border border-border/50 bg-surface-2/40 px-3.5 py-2.5 text-sm shadow-elev-1">
                      <span className="text-muted-foreground">{t("login.sso_provider_label")}</span>
                      <span className="ml-2 font-medium text-foreground">{t("login.sso_provider_value")}</span>
                    </div>

                    <LoginError detail={errorDetail} />

                    <Button
                      type="button"
                      className="h-11 w-full shadow-elev-1"
                      onClick={handleSsoContinue}
                      loading={loading}
                    >
                      {t("login.sso_submit")}
                    </Button>
                  </div>
                )}
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
