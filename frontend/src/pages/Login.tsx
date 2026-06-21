import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  Eye,
  EyeOff,
  Loader2,
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
    <div className="min-h-dvh bg-background text-foreground">
      <div className="grid min-h-dvh lg:grid-cols-[42fr_58fr]">
        <section className="hidden border-r border-border bg-secondary/20 px-10 py-10 lg:flex lg:flex-col lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-sm font-semibold text-primary">
                W
              </div>
              <div>
                <div className="text-sm font-semibold">WebTermAI</div>
                <div className="text-xs text-muted-foreground">{t("login.brand_subtitle")}</div>
              </div>
            </div>

            <div className="mt-20 max-w-xl">
              <p className="text-xs font-medium uppercase tracking-[0.16em] text-primary">{t("login.kicker")}</p>
              <h2 className="mt-4 text-4xl font-semibold leading-tight text-foreground">{t("login.hero_title")}</h2>
              <p className="mt-4 max-w-lg text-sm leading-6 text-muted-foreground">{t("login.hero_desc")}</p>
            </div>
          </div>

          <div className="grid gap-3 text-sm text-muted-foreground">
            <div className="flex items-center gap-3">
              <Server className="h-4 w-4 text-primary" />
              <span>{t("login.bullet_ssh")}</span>
            </div>
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>{t("login.bullet_sso")}</span>
            </div>
            <div className="flex items-center gap-3">
              <LockKeyhole className="h-4 w-4 text-primary" />
              <span>{t("login.bullet_session")}</span>
            </div>
          </div>
        </section>

        <main className="flex min-h-dvh items-center justify-center px-5 py-8">
          <div className="w-full max-w-[440px]">
            <div className="mb-8 flex items-start justify-between gap-4">
              <div>
                <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-sm font-semibold text-primary lg:hidden">
                  W
                </div>
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-primary">{t("login.eyebrow")}</p>
                <h1 className="mt-2 text-2xl font-semibold text-foreground">{t("login.title")}</h1>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("login.subtitle")}</p>
              </div>
              <div className="inline-flex overflow-hidden rounded-lg border border-border text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setLang("en")}
                  className={cn("h-10 px-3 transition-colors", lang === "en" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}
                  aria-pressed={lang === "en"}
                >
                  EN
                </button>
                <button
                  type="button"
                  onClick={() => setLang("ru")}
                  className={cn("h-10 px-3 transition-colors", lang === "ru" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}
                  aria-pressed={lang === "ru"}
                >
                  RU
                </button>
              </div>
            </div>

            <div className="mb-5 grid grid-cols-2 rounded-lg border border-border bg-secondary/25 p-1">
              <button
                type="button"
                onClick={() => selectMode("local")}
                className={cn(
                  "min-h-11 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isLocal ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
                aria-pressed={isLocal}
              >
                {t("login.local_tab")}
              </button>
              <button
                type="button"
                onClick={() => selectMode("sso")}
                className={cn(
                  "min-h-11 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  !isLocal ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
                aria-pressed={!isLocal}
              >
                {t("login.sso_tab")}
              </button>
            </div>

            {isLocal ? (
              <form onSubmit={handleLocalSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username" className="text-sm text-muted-foreground">
                    {t("login.username")}
                  </Label>
                  <Input
                    id="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder="admin"
                    className="h-11 border-border bg-card"
                    autoComplete="username"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password" className="text-sm text-muted-foreground">
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
                      className="h-11 border-border bg-card pr-12"
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      className="absolute right-0.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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

                <Button type="submit" className="h-11 w-full" disabled={loading || !username.trim() || !password.trim()}>
                  {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  {t("login.submit")}
                </Button>
              </form>
            ) : (
              <div className="space-y-4 rounded-xl border border-border bg-card/60 p-4">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                    <ShieldCheck className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-foreground">{t("login.sso_title")}</h2>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">{t("login.sso_desc")}</p>
                  </div>
                </div>
                <div className="rounded-lg border border-border/70 bg-background/50 px-3 py-3 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">{t("login.sso_provider_label")}</span>
                  <span className="ml-2">{t("login.sso_provider_value")}</span>
                </div>

                <LoginError detail={errorDetail} />

                <Button type="button" className="h-11 w-full" onClick={handleSsoContinue} disabled={loading}>
                  {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  {t("login.sso_submit")}
                </Button>
              </div>
            )}

            <p className="mt-5 text-sm leading-6 text-muted-foreground">{t("login.help")}</p>
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
    <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <div className="font-medium">{t("login.error_title")}</div>
          <div className="mt-0.5 text-destructive/90">{t("login.error_desc")}</div>
        </div>
      </div>
      <details className="mt-2 text-xs text-destructive/80">
        <summary className="cursor-pointer">{t("login.error_details")}</summary>
        <p className="mt-1 break-words">{detail}</p>
      </details>
    </div>
  );
}
