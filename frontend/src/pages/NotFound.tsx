import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, Home } from "lucide-react";
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
    <div
      data-ui-slot="not-found-page"
      data-page-kind="utility"
      className="flex min-h-screen flex-col items-center justify-center bg-background px-6"
    >
      <div data-ui-slot="not-found-content" className="w-full max-w-md">
        <p className="font-mono text-xs tabular-nums text-muted-foreground">404</p>
        <h1 className="mt-2 type-h1 text-foreground">{t("not_found.title_long")}</h1>
        <p className="mt-2 type-body text-muted-foreground">{t("not_found.text_long")}</p>

        {location.pathname !== "/" ? (
          <div className="mt-4 inline-flex items-center gap-2 rounded-sm border border-border bg-card px-3 py-1.5">
            <span className="text-xs text-muted-foreground">{t("not_found.path")}</span>
            <code className="font-mono text-xs text-foreground">{location.pathname}</code>
          </div>
        ) : null}

        <div className="mt-8 flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => navigate(-1)} className="h-10 gap-2 rounded-sm">
            <ArrowLeft className="h-4 w-4" aria-hidden />
            {t("not_found.back_btn")}
          </Button>
          <Button onClick={() => navigate("/dashboard", { replace: true })} className="h-10 gap-2 rounded-sm">
            <Home className="h-4 w-4" aria-hidden />
            {t("not_found.home_btn")}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default NotFound;
