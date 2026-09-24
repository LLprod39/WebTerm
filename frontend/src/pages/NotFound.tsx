import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorScene } from "@/components/error-scene";
import { useI18n } from "@/lib/i18n";

const NotFound = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useI18n();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <ErrorScene
      code="404"
      mood="lost"
      title={t("not_found.title_long")}
      description={t("not_found.text_long")}
      meta={
        location.pathname !== "/" ? (
          <div className="inline-flex max-w-full items-center gap-2 rounded-sm border border-border bg-card px-3 py-1.5">
            <span className="shrink-0 text-xs text-muted-foreground">{t("not_found.path")}</span>
            <code className="truncate font-mono text-xs text-foreground">{location.pathname}</code>
          </div>
        ) : null
      }
      actions={
        <>
          <Button variant="outline" onClick={() => navigate(-1)} className="h-10 gap-2 rounded-sm">
            <ArrowLeft className="h-4 w-4" aria-hidden />
            {t("not_found.back_btn")}
          </Button>
          <Button onClick={() => navigate("/dashboard", { replace: true })} className="h-10 gap-2 rounded-sm">
            <Home className="h-4 w-4" aria-hidden />
            {t("not_found.home_btn")}
          </Button>
          <div className="basis-full pt-1 text-center sm:text-left">
            <button
              type="button"
              onClick={() => navigate("/dashboard", { replace: true })}
              className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              {t("not_found.cta_fun")}
            </button>
          </div>
        </>
      }
    />
  );
};

export default NotFound;
