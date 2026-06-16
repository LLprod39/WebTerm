import { Database, Eye, Save, ScrollText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { DEFAULT_LOGGING_CONFIG, LOGGING_ITEMS } from "./constants";
import { SectionCard } from "./SectionCard";

type LoggingSettingsPanelProps = {
  loggingConfig: typeof DEFAULT_LOGGING_CONFIG;
  loggingSaved: boolean;
  saving: boolean;
  onSave: () => void;
  onUpdate: (key: string, value: unknown) => void;
};

export function LoggingSettingsPanel({
  loggingConfig,
  loggingSaved,
  saving,
  onSave,
  onUpdate,
}: LoggingSettingsPanelProps) {
  return (
    <>
      <SectionCard
        title="Настройки логирования"
        icon={ScrollText}
        description="Выберите какие действия пользователей записывать в журнал"
        actions={
          <Button size="sm" className="gap-1.5 h-7" onClick={onSave} disabled={saving}>
            <Save className="h-3 w-3" />
            {saving ? "Сохранение..." : loggingSaved ? "✓ Сохранено" : "Сохранить"}
          </Button>
        }
      >
        <div className="space-y-1">
          {LOGGING_ITEMS.map((item) => {
            const Icon = item.icon;
            const enabled = Boolean(loggingConfig[item.key]);
            return (
              <label
                key={item.key}
                className="flex items-center gap-3 rounded-lg px-3 py-3 hover:bg-muted/30 transition-colors cursor-pointer"
              >
                <div className={cn(
                  "h-8 w-8 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                  enabled ? "bg-primary/10" : "bg-muted/50",
                )}>
                  <Icon className={cn("h-4 w-4", enabled ? "text-primary" : "text-muted-foreground")} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium">{item.label}</p>
                  <p className="text-[10px] text-muted-foreground">{item.desc}</p>
                </div>
                <Switch
                  checked={enabled}
                  onCheckedChange={(value) => onUpdate(item.key, value)}
                />
              </label>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard title="Хранение и экспорт" icon={Database} description="Настройки ротации и формата логов">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label className="text-xs">Хранить логи (дней)</Label>
            <Select
              value={String(loggingConfig.retention_days)}
              onValueChange={(value) => onUpdate("retention_days", Number(value))}
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
            <Label className="text-xs">Формат экспорта</Label>
            <Select
              value={loggingConfig.export_format}
              onValueChange={(value) => onUpdate("export_format", value)}
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
            Экспорт доступен через API: <code className="text-foreground">GET /api/settings/activity/?format=json&days=30</code>
          </p>
        </div>
      </SectionCard>

      <div className="rounded-lg border border-border bg-card px-5 py-4">
        <div className="flex items-center gap-2 mb-3">
          <Eye className="h-4 w-4 text-primary" />
          <span className="text-xs font-medium">Активные категории</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {LOGGING_ITEMS.filter((item) => loggingConfig[item.key]).map((item) => (
            <Badge key={item.key} variant="secondary" className="text-[10px] gap-1">
              <item.icon className="h-2.5 w-2.5" /> {item.label}
            </Badge>
          ))}
          {LOGGING_ITEMS.every((item) => !loggingConfig[item.key]) && (
            <p className="text-[11px] text-muted-foreground">Все категории отключены</p>
          )}
        </div>
      </div>
    </>
  );
}
