import type { ReactNode } from "react";
import { Check, RotateCcw, Settings2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { localize, useI18n } from "@/lib/i18n";
import type { AiAssistantSettings } from "../ai-types";
import { NovaContextSettings } from "../nova/NovaContextSettings";

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2.5">
      <div className="px-0.5">
        <h4 className="text-[13px] font-semibold text-foreground">{title}</h4>
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>
      </div>
      <div className="rounded-lg border border-border/50 bg-secondary/15 p-3">
        {children}
      </div>
    </section>
  );
}

function ToggleRow({
  title,
  description,
  checked,
  onCheckedChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-foreground">{title}</div>
        <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}

export function AiPanelSettingsDialog({
  open,
  onOpenChange,
  chatModeControl,
  executionModeControl,
  settings,
  onSettingsPatch,
  onClearMemory,
  onSaveDefaults,
  onResetToDefaults,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatModeControl: ReactNode;
  executionModeControl: ReactNode;
  settings: AiAssistantSettings;
  onSettingsPatch: (patch: Partial<AiAssistantSettings>) => void;
  onClearMemory?: () => void;
  onSaveDefaults?: () => void;
  onResetToDefaults?: () => void;
}) {
  const { lang } = useI18n();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-2xl grid-rows-[auto,minmax(0,1fr),auto] overflow-hidden rounded-xl border-border/60 sm:max-h-[85vh]">
        <DialogHeader className="pb-0">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4 text-muted-foreground" />
            {localize(lang, "Настройки ИИ", "AI settings")}
          </DialogTitle>
          <DialogDescription className="text-xs">
            {localize(lang, "Изменения применяются сразу.", "Changes apply immediately.")}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="min-h-0 space-y-5 overflow-y-auto py-2">
          <SettingsSection
            title={localize(lang, "Режим", "Mode")}
            description={localize(lang, "Диалог и выполнение команд.", "Conversation and command execution.")}
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[13px] text-foreground">{localize(lang, "Диалог", "Conversation")}</span>
                {chatModeControl}
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-[13px] text-foreground">{localize(lang, "Выполнение", "Execution")}</span>
                {executionModeControl}
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-[13px] text-foreground">{localize(lang, "Автоотчёт", "Automatic report")}</span>
                <Select
                  value={settings.autoReport}
                  onValueChange={(value) => onSettingsPatch({ autoReport: value === "on" || value === "off" ? value : "auto" })}
                >
                  <SelectTrigger className="h-8 w-36 rounded-md bg-background text-xs" aria-label={localize(lang, "Автоотчёт", "Automatic report")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">{localize(lang, "Авто", "Auto")}</SelectItem>
                    <SelectItem value="on">{localize(lang, "Всегда", "Always")}</SelectItem>
                    <SelectItem value="off">{localize(lang, "Никогда", "Never")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </SettingsSection>

          <SettingsSection
            title={localize(lang, "Память", "Memory")}
            description={localize(lang, "Контекст предыдущих запросов.", "Context from previous requests.")}
          >
            <div className="space-y-2">
              <ToggleRow
                title={localize(lang, "Учитывать контекст", "Use context")}
                description={localize(lang, "ИИ учитывает предыдущие запросы этой сессии.", "AI uses earlier requests from this session.")}
                checked={settings.memoryEnabled}
                onCheckedChange={(checked) => onSettingsPatch({ memoryEnabled: checked })}
              />

              <div className="flex items-center justify-between gap-3 py-1.5">
                <div>
                  <div className="text-[13px] font-medium text-foreground">{localize(lang, "Глубина памяти", "Memory depth")}</div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{localize(lang, "Последние запросы: 1–20", "Recent requests: 1–20")}</p>
                </div>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={settings.memoryTtlRequests}
                  disabled={!settings.memoryEnabled}
                  onChange={(event) => onSettingsPatch({ memoryTtlRequests: Math.max(1, Math.min(20, Number(event.target.value || 1))) })}
                  className="h-8 w-16 rounded-md border border-border bg-background px-2.5 text-center text-xs text-foreground focus:border-primary focus:outline-none disabled:opacity-40"
                />
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                <span className="text-[13px] text-foreground">{localize(lang, "Очистить память", "Clear memory")}</span>
                <Button type="button" variant="outline" size="xs" onClick={onClearMemory} className="h-8 gap-1.5 px-3 text-xs">
                  <Trash2 className="h-3 w-3" />
                  {localize(lang, "Очистить", "Clear")}
                </Button>
              </div>
            </div>
          </SettingsSection>

          <NovaContextSettings settings={settings} onChange={onSettingsPatch} />

          <SettingsSection
            title={localize(lang, "Отображение", "Display")}
            description={localize(lang, "Какие команды показывать.", "Which commands to show.")}
          >
            <div className="space-y-1">
              <ToggleRow
                title={localize(lang, "Предлагаемые команды", "Suggested commands")}
                description={localize(lang, "Показывать команды до подтверждения.", "Show commands before approval.")}
                checked={settings.showSuggestedCommands}
                onCheckedChange={(checked) => onSettingsPatch({ showSuggestedCommands: checked })}
              />
              <ToggleRow
                title={localize(lang, "Завершённые команды", "Completed commands")}
                description={localize(lang, "Показывать выполненные и отменённые команды.", "Show completed and cancelled commands.")}
                checked={settings.showExecutedCommands}
                onCheckedChange={(checked) => onSettingsPatch({ showExecutedCommands: checked })}
              />
            </div>
          </SettingsSection>
        </DialogBody>

        <DialogFooter className="gap-2 pt-0">
          <Button type="button" variant="ghost" size="sm" onClick={onResetToDefaults} className="gap-1.5 text-xs text-muted-foreground">
            <RotateCcw className="h-3 w-3" />
            {localize(lang, "Сбросить", "Reset")}
          </Button>
          <Button type="button" size="sm" onClick={onSaveDefaults} className="gap-1.5 text-xs">
            <Check className="h-3 w-3" />
            {localize(lang, "Сохранить по умолчанию", "Save as default")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
