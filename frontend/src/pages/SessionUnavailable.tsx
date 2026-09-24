import { RefreshCw } from "lucide-react";
import { ErrorScene } from "@/components/error-scene";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

export default function SessionUnavailable({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();

  return (
    <ErrorScene
      role="alert"
      code="503"
      mood="offline"
      title={t("app.session_unavailable_title")}
      description={t("app.session_unavailable_desc")}
      actions={
        <Button type="button" onClick={onRetry} className="h-10 gap-2 rounded-sm">
          <RefreshCw className="h-4 w-4" aria-hidden />
          {t("app.session_unavailable_action")}
        </Button>
      }
    />
  );
}
