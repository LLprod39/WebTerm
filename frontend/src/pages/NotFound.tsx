import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, Home, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

const NotFound = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useI18n();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-border bg-card shadow-sm">
          <Search className="h-7 w-7 text-primary" />
        </div>

        <div className="mb-3 inline-flex items-center rounded-full border border-border bg-secondary/40 px-3 py-1 text-xs font-semibold text-muted-foreground">
          {t("not_found.title")}
        </div>

        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {t("not_found.title_long")}
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {t("not_found.text_long")}
        </p>

        {location.pathname !== "/" && (
          <div className="mx-auto mt-4 inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5">
            <span className="text-xs text-muted-foreground/60">{t("not_found.path")}</span>
            <code className="font-mono text-xs text-muted-foreground">{location.pathname}</code>
          </div>
        )}

        <div className="mt-8 flex items-center justify-center gap-3">
          <Button variant="outline" onClick={() => navigate(-1)} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            {t("not_found.back_btn")}
          </Button>
          <Button onClick={() => navigate("/dashboard", { replace: true })} className="gap-2">
            <Home className="h-4 w-4" />
            {t("not_found.home_btn")}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default NotFound;
