import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, Loader2, LockKeyhole, Server, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authLogin, fetchAuthSession } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export default function Login() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t, lang, setLang } = useI18n();
  const [searchParams] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [localOnly, setLocalOnly] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const nextFromUrl = searchParams.get("next") || "";

  const { data: session } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
    refetchOnMount: "always",
    enabled: !localOnly,
  });

  useEffect(() => {
    if (!localOnly && session?.authenticated) {
      navigate(nextFromUrl || "/dashboard", { replace: true });
    }
  }, [localOnly, session?.authenticated, navigate, nextFromUrl]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await authLogin(username, password, localOnly ? "local" : "auto");
      queryClient.setQueryData(["auth", "session"], {
        authenticated: true,
        user: result.user,
      });
      await queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
      const nextUrl = nextFromUrl || result.next_url || "/dashboard";
      navigate(nextUrl, { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <div className="grid min-h-dvh lg:grid-cols-[minmax(0,0.9fr)_minmax(380px,520px)]">
        <section className="hidden border-r border-border bg-secondary/20 px-10 py-10 lg:flex lg:flex-col lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-sm font-semibold text-primary">
                W
              </div>
              <div>
                <div className="text-sm font-semibold">WebTermAI</div>
                <div className="text-xs text-muted-foreground">Operations console</div>
              </div>
            </div>

            <div className="mt-24 max-w-xl">
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Secure operations</p>
              <h1 className="mt-4 text-4xl font-semibold leading-tight text-foreground">
                {lang === "ru" ? "Единая консоль для серверов, агентов и Studio." : "One console for servers, agents, and Studio."}
              </h1>
              <p className="mt-4 max-w-lg text-sm leading-6 text-muted-foreground">
                {lang === "ru"
                  ? "Вход открывает терминалы, мониторинг, автоматизации и доступы по ролям из одной консоли."
                  : "Sign in to access terminals, monitoring, automations, and role-based controls from one console."}
              </p>
            </div>
          </div>

          <div className="grid gap-3 text-sm text-muted-foreground">
            <div className="flex items-center gap-3">
              <Server className="h-4 w-4 text-primary" />
              <span>{lang === "ru" ? "SSH, RDP и файловые операции" : "SSH, RDP, and file operations"}</span>
            </div>
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>{lang === "ru" ? "Локальный вход или SSO через домен" : "Local login or domain SSO"}</span>
            </div>
            <div className="flex items-center gap-3">
              <LockKeyhole className="h-4 w-4 text-primary" />
              <span>{lang === "ru" ? "Защищённая сессия и проверка запросов" : "Protected session and request checks"}</span>
            </div>
          </div>
        </section>

        <main className="flex min-h-dvh items-center justify-center px-5 py-8">
          <div className="w-full max-w-[400px]">
            <div className="mb-8 flex items-start justify-between gap-4">
              <div>
                <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-sm font-semibold text-primary lg:hidden">
                  W
                </div>
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-primary">
                  {lang === "ru" ? "Вход" : "Sign in"}
                </p>
                <h1 className="mt-2 text-2xl font-semibold text-foreground">{t("login.title")}</h1>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("login.subtitle")}</p>
              </div>
              <div className="inline-flex overflow-hidden rounded-lg border border-border text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setLang("en")}
                  className={cn("px-3 py-1.5 transition-colors", lang === "en" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}
                  aria-pressed={lang === "en"}
                >
                  EN
                </button>
                <button
                  type="button"
                  onClick={() => setLang("ru")}
                  className={cn("px-3 py-1.5 transition-colors", lang === "ru" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}
                  aria-pressed={lang === "ru"}
                >
                  RU
                </button>
              </div>
            </div>

            <div className="mb-5 grid grid-cols-2 rounded-lg border border-border bg-secondary/25 p-1">
              <button
                type="button"
                onClick={() => setLocalOnly(true)}
                className={cn(
                  "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  localOnly ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
                aria-pressed={localOnly}
              >
                {lang === "ru" ? "Локально" : "Local"}
              </button>
              <button
                type="button"
                onClick={() => setLocalOnly(false)}
                className={cn(
                  "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  !localOnly ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
                aria-pressed={!localOnly}
              >
                {lang === "ru" ? "SSO / auto" : "SSO / auto"}
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username" className="text-sm text-muted-foreground">{t("login.username")}</Label>
                <Input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  className="h-11 bg-card border-border"
                  autoComplete="username"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-sm text-muted-foreground">{t("login.password")}</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11 bg-card border-border"
                  autoComplete="current-password"
                />
              </div>

              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button type="submit" className="h-11 w-full" disabled={loading || (localOnly && (!username.trim() || !password.trim()))}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {t("login.submit")}
              </Button>
            </form>

          </div>
        </main>
      </div>
    </div>
  );
}
