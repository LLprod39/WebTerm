import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n";
import type { AiAssistantSettings } from "../ai-types";

interface NovaContextSettingsProps {
  settings: AiAssistantSettings;
  onChange: (patch: Partial<AiAssistantSettings>) => void;
}

export function NovaContextSettings({ settings, onChange }: NovaContextSettingsProps) {
  const { t } = useI18n();

  return (
    <section className="space-y-2.5">
      <div className="px-0.5">
        <h4 className="text-[13px] font-semibold text-foreground">{t("terminal.ai.nova.settings.title")}</h4>
        <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{t("terminal.ai.nova.settings.description")}</p>
      </div>
      <div className="space-y-2 rounded-lg border border-border/50 bg-secondary/15 p-3">
        <div className="flex items-center justify-between gap-3 py-1.5">
          <div>
            <div className="text-[13px] font-medium text-foreground">{t("terminal.ai.nova.settings.sessionContext.title")}</div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{t("terminal.ai.nova.settings.sessionContext.description")}</p>
          </div>
          <Switch
            checked={settings.novaSessionContextEnabled}
            onCheckedChange={(checked) => onChange({ novaSessionContextEnabled: checked })}
          />
        </div>
        <div className="flex items-center justify-between gap-3 py-1.5">
          <div>
            <div className="text-[13px] font-medium text-foreground">{t("terminal.ai.nova.settings.recentActivity.title")}</div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{t("terminal.ai.nova.settings.recentActivity.description")}</p>
          </div>
          <Switch
            checked={settings.novaRecentActivityEnabled}
            onCheckedChange={(checked) => onChange({ novaRecentActivityEnabled: checked })}
          />
        </div>
      </div>
    </section>
  );
}
