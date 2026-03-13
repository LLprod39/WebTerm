import { useLocation } from "react-router-dom";
import { useEffect } from "react";
import { useI18n } from "@/lib/i18n";

const NotFound = () => {
  const location = useLocation();
  const { t } = useI18n();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center">
        <h1 className="mb-4 text-4xl font-bold text-foreground">{t("not_found.title")}</h1>
        <p className="mb-4 text-xl text-muted-foreground">{t("not_found.text")}</p>
        <a href="/" className="text-primary underline hover:text-primary/90">
          {t("not_found.back")}
        </a>
      </div>
    </div>
  );
};

export default NotFound;
