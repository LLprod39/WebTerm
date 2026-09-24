import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ErrorScene } from "@/components/error-scene";
import { Button } from "@/components/ui/button";
import { fetchAuthSession } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { firstAllowedApplicationPath } from "@/lib/navigation";

export default function PermissionDenied() {
  const { t } = useI18n();
  const { data } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const destination = firstAllowedApplicationPath(data?.user);

  return (
    <ErrorScene
      fullBleed={false}
      code="403"
      mood="locked"
      kicker={t("app.permission_denied_kicker")}
      title={t("app.permission_denied_title")}
      description={t("app.permission_denied_desc")}
      actions={
        destination ? (
          <Button asChild className="h-10 rounded-sm">
            <Link to={destination}>{t("app.permission_denied_action")}</Link>
          </Button>
        ) : null
      }
    />
  );
}
