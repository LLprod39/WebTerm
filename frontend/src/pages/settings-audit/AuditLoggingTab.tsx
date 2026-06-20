import { Database, Eye, Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { LOGGING_ITEM_KEYS, type LoggingConfig, type LoggingConfigKey } from "./auditSettingsModel";

type AuditLoggingTabProps = {
  loggingConfig: LoggingConfig;
  saving: boolean;
  loggingSaved: boolean;
  onUpdateLogging: (key: LoggingConfigKey, value: unknown) => void;
  onSaveLogging: () => void | Promise<void>;
};

export function AuditLoggingTab({
  loggingConfig,
  saving,
  loggingSaved,
  onUpdateLogging,
  onSaveLogging,
}: AuditLoggingTabProps) {
  const { t } = useI18n();
  const loggingItems = LOGGING_ITEM_KEYS.map((item) => ({ ...item, label: t(item.labelKey), desc: t(item.descKey) }));
  const activeItems = loggingItems.filter((item) => loggingConfig[item.key]);

  return (
    <>
      <SectionCard
        title={t("audit.log_settings")}
        icon={Eye}
        description={t("audit.log_settings_desc")}
        actions={
          <Button size="sm" className="h-7 gap-1.5" onClick={() => void onSaveLogging()} disabled={saving}>
            <Save className="h-3 w-3" />
            {saving ? t("audit.saving") : loggingSaved ? t("ai.saved") : t("audit.save")}
          </Button>
        }
      >
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
                    <p className="line-clamp-2 text-[11px] font-medium leading-4 text-muted-foreground/80">{item.desc}</p>
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
            <Label className="text-xs">{t("audit.retention_label")}</Label>
            <Select
              value={String(loggingConfig.retention_days)}
              onValueChange={(value) => onUpdateLogging("retention_days", Number(value))}
            >
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
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
            <Label className="text-xs">{t("audit.export_format")}</Label>
            <Select
              value={loggingConfig.export_format}
              onValueChange={(value) => onUpdateLogging("export_format", value)}
            >
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="json">JSON</SelectItem>
                <SelectItem value="csv">CSV</SelectItem>
                <SelectItem value="syslog">Syslog</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="mt-4 rounded-lg border border-border bg-muted/20 px-4 py-3">
          <p className="text-[11px] text-muted-foreground">
            Логи хранятся на сервере в таблице <code className="text-foreground">core_ui_useractivitylog</code>.
            При превышении срока хранения старые записи автоматически удаляются.
          </p>
        </div>
      </SectionCard>

      <div className="rounded-xl border border-border/60 bg-secondary/10 px-5 py-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
            <Eye className="h-3.5 w-3.5 text-primary" />
          </div>
          <span className="text-xs font-semibold text-foreground">{t("audit.filter_tab")}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {activeItems.map((item) => (
            <Badge key={item.key} variant="secondary" className="gap-1 text-[10px]">
              <item.icon className="h-2.5 w-2.5" /> {item.label}
            </Badge>
          ))}
          {activeItems.length === 0 && (
            <p className="text-[11px] text-muted-foreground">{t("audit.log_settings")}</p>
          )}
        </div>
      </div>
    </>
  );
}
