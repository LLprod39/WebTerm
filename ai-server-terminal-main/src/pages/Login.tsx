import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authLogin, fetchAuthSession } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useI18n } from "@/lib/i18n";

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
      navigate(nextFromUrl || "/servers", { replace: true });
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
      const nextUrl = nextFromUrl || result.next_url || "/servers";
      navigate(nextUrl, { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-10 text-center">
          <div className="flex items-center justify-center gap-2 mb-6">
            <div className="h-10 w-10 rounded-lg bg-primary/15 flex items-center justify-center">
              <span className="text-base font-bold text-primary">W</span>
            </div>
          </div>
          <h1 className="text-xl font-semibold text-foreground">
            {t("login.title")}
          </h1>
          <p className="text-sm text-muted-foreground mt-2">{t("login.subtitle")}</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="username" className="text-sm text-muted-foreground">{t("login.username")}</Label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              className="h-10 bg-card border-border"
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
              className="h-10 bg-card border-border"
              autoComplete="current-password"
            />
          </div>

          <label className="flex cursor-pointer items-center gap-2 py-1 text-sm text-muted-foreground">
            <Checkbox
              checked={localOnly}
              onCheckedChange={(checked) => setLocalOnly(checked === true)}
            />
            <span>{lang === "ru" ? "Локальный вход" : "Local login"}</span>
          </label>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <Button type="submit" className="w-full h-10" disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            {t("login.submit")}
          </Button>
        </form>

        {/* Footer */}
        <div className="flex items-center justify-between mt-8">
          <p className="text-xs text-muted-foreground">
            {t("login.footer")}
          </p>
          <div className="inline-flex rounded-lg border border-border overflow-hidden text-xs font-medium">
            <button
              type="button"
              onClick={() => setLang("en")}
              className={`px-3 py-1 transition-colors ${lang === "en" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"}`}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => setLang("ru")}
              className={`px-3 py-1 transition-colors ${lang === "ru" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"}`}
            >
              RU
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
