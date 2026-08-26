import { Database, Eye, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  AUDIT_LOGGING_PRESETS,
  LOGGING_ITEM_KEYS,
  type AuditLoggingPresetKey,
  type LoggingConfig,
  type LoggingConfigKey,
} from "./auditSettingsModel";

type AuditLoggingTabProps = {
  loggingConfig: LoggingConfig;
  saving: boolean;
  loggingSaved: boolean;
  onApplyPreset: (preset: AuditLoggingPresetKey) => void;
  onUpdateLogging: (key: LoggingConfigKey, value: unknown) => void;
  onSaveLogging: () => void | Promise<void>;
};

export function AuditLoggingTab({
  loggingConfig,
  saving,
  loggingSaved,
  onApplyPreset,
  onUpdateLogging,
  onSaveLogging,
}: AuditLoggingTabProps) {
  const { t, lang } = useI18n();
  const loggingItems = LOGGING_ITEM_KEYS.map((item) => ({ ...item, label: t(item.labelKey), desc: t(item.descKey) }));
  const presetLabels: Record<AuditLoggingPresetKey, { title: string; description: string }> = {
    pilot: {
      title: lang === "ru" ? "Пилот" : "Pilot",
      description: lang === "ru" ? "Основные события без шумного HTTP." : "Core events without noisy HTTP.",
    },
    strict: {
      title: lang === "ru" ? "Строгий" : "Strict",
      description: lang === "ru" ? "Больше категорий и длиннее хранение." : "More categories and longer retention.",
    },
    debug: {
      title: lang === "ru" ? "Отладка" : "Debug",
      description: lang === "ru" ? "HTTP и файловые операции на короткий срок." : "HTTP and file events for short investigations.",
    },
  };

  return (
    <>
      <SectionCard
        title={t("audit.log_settings")}
        icon={Eye}
        description={t("audit.log_settings_desc")}
        actions={
          <Button size="sm" className="h-9 gap-1.5" onClick={() => void onSaveLogging()} disabled={saving}>
            <Save className="h-3 w-3" />
            {saving ? t("audit.saving") : loggingSaved ? t("ai.saved") : t("audit.save")}
          </Button>
        }
      >
        <div className="mb-4 grid gap-2 md:grid-cols-3">
          {(Object.keys(AUDIT_LOGGING_PRESETS) as AuditLoggingPresetKey[]).map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => onApplyPreset(preset)}
              className="rounded-lg border border-border/60 bg-secondary/20 px-3 py-3 text-left transition-colors hover:bg-secondary/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="text-sm font-semibold text-foreground">{presetLabels[preset].title}</div>
              <div className="mt-1 text-xs leading-5 text-muted-foreground">{presetLabels[preset].description}</div>
            </button>
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {loggingItems.map((item) => {
            const Icon = item.icon;
            const enabled = loggingConfig[item.key];
            return (
              <label
                key={item.key}
                className="group flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-primary/5 bg-background/50 px-4 py-4 shadow-sm transition-all duration-300 hover:border-primary/20 hover:bg-background/80 hover:shadow-md"
              >
                <div className="flex items-center gap-4 min-w-0">
                  <div className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl shadow-inner transition-colors duration-300",
                    enabled ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground group-hover:bg-muted/80"
                  )}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className={cn("text-sm font-bold tracking-tight transition-colors", enabled ? "text-foreground" : "text-foreground/70")}>{item.label}</p>
                    <p className="line-clamp-2 text-xs font-medium leading-4 text-muted-foreground/80">{item.desc}</p>
                  </div>
                </div>
                <Switch
                  checked={Boolean(enabled)}
                  onCheckedChange={(value) => onUpdateLogging(item.key, value)}
                  className="data-[state=checked]:bg-primary"
                />
              </label>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard title={t("audit.storage_title")} icon={Database} description={t("audit.storage_desc")}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label className="text-sm">{t("audit.retention_label")}</Label>
            <Select
              value={String(loggingConfig.retention_days)}
              onValueChange={(value) => onUpdateLogging("retention_days", Number(value))}
            >
              <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="30">30 дней</SelectItem>
                <SelectItem value="60">60 дней</SelectItem>
                <SelectItem value="90">90 дней</SelectItem>
                <SelectItem value="180">180 дней</SelectItem>
                <SelectItem value="365">1 год</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label className="text-sm">{t("audit.export_format")}</Label>
            <Select
              value={loggingConfig.export_format}
              onValueChange={(value) => onUpdateLogging("export_format", value)}
            >
              <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="json">JSON</SelectItem>
                <SelectItem value="csv">CSV</SelectItem>
                <SelectItem value="syslog">Syslog</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="mt-4 rounded-lg border border-border bg-muted/20 px-4 py-3">
          <p className="text-xs text-muted-foreground">
            Старые записи удаляются автоматически по истечении выбранного срока.
          </p>
        </div>
      </SectionCard>
    </>
  );
}
