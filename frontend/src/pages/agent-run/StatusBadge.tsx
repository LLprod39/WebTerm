import { StatusBadge as SystemStatusBadge } from "@/components/system/StatusBadge";
import { agentRunStatusPresentation } from "@/design/status";
import { useI18n } from "@/lib/i18n";

export function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const presentation = agentRunStatusPresentation(status);
  return <SystemStatusBadge label={t(presentation.labelKey)} tone={presentation.tone} pulse={presentation.pulse} />;
}
