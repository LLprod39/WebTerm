import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n";
import type { AiAssistantSettings, NovaSudoPolicy } from "../ai-types";

const SUDO_OPTIONS: Array<{ value: NovaSudoPolicy; titleKey: string; descKey: string }> = [
  {
    value: "disabled",
    titleKey: "terminal.ai.nova.settings.sudo.disabled",
    descKey: "terminal.ai.nova.settings.sudo.disabled.description",
  },
  {
    value: "ask",
    titleKey: "terminal.ai.nova.settings.sudo.ask",
    descKey: "terminal.ai.nova.settings.sudo.ask.description",
  },
  {
    value: "approved",
    titleKey: "terminal.ai.nova.settings.sudo.approved",
    descKey: "terminal.ai.nova.settings.sudo.approved.description",
  },
];

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
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{t("terminal.ai.nova.settings.description")}</p>
      </div>
      <div className="space-y-2 rounded-lg border border-border/50 bg-secondary/15 p-3">
        <div className="flex items-center justify-between gap-3 py-1.5">
          <div>
            <div className="text-[13px] font-medium text-foreground">{t("terminal.ai.nova.settings.sessionContext.title")}</div>
            <p className="mt-0.5 text-xs text-muted-foreground">{t("terminal.ai.nova.settings.sessionContext.description")}</p>
          </div>
          <Switch
            checked={settings.novaSessionContextEnabled}
            onCheckedChange={(checked) => onChange({ novaSessionContextEnabled: checked })}
          />
        </div>
        <div className="flex items-center justify-between gap-3 py-1.5">
          <div>
            <div className="text-[13px] font-medium text-foreground">{t("terminal.ai.nova.settings.recentActivity.title")}</div>
            <p className="mt-0.5 text-xs text-muted-foreground">{t("terminal.ai.nova.settings.recentActivity.description")}</p>
          </div>
          <Switch
            checked={settings.novaRecentActivityEnabled}
            onCheckedChange={(checked) => onChange({ novaRecentActivityEnabled: checked })}
          />
        </div>
        <div className="space-y-2 border-t border-border/50 pt-3">
          <div>
            <div className="text-[13px] font-medium text-foreground">{t("terminal.ai.nova.settings.sudo.title")}</div>
            <p className="mt-0.5 text-xs text-muted-foreground">{t("terminal.ai.nova.settings.sudo.description")}</p>
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            {SUDO_OPTIONS.map((option) => {
              const active = settings.novaSudoPolicy === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onChange({ novaSudoPolicy: option.value })}
                  className={`min-h-16 rounded-md border px-2 py-2 text-left transition-colors ${
                    active
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border/70 bg-background/50 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <span className="block text-[12px] font-semibold">{t(option.titleKey)}</span>
                  <span className="mt-1 block text-xs leading-snug">{t(option.descKey)}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
