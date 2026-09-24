import type { ElementType } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsField } from "@/components/settings/SettingsPageShell";
import { cn } from "@/lib/utils";
import { getProviderLabel, LLM_PROVIDERS } from "./constants";
import { ProviderModelPicker } from "./ProviderModelPicker";

type PurposeModelSelectorProps = {
  label: string;
  description: string;
  icon: ElementType;
  provider: string;
  model: string;
  availableModels: string[];
  disabled?: boolean;
  onProviderChange: (provider: string) => void;
  onModelChange: (model: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
};

export function PurposeModelSelector({
  label,
  description,
  icon: Icon,
  provider,
  model,
  availableModels,
  disabled = false,
  onProviderChange,
  onModelChange,
  onRefresh,
  refreshing,
}: PurposeModelSelectorProps) {
  return (
    <div
      className={cn(
        "flex h-full flex-col gap-4 border-border bg-surface-0/50 p-4",
        "rounded-sm border xl:rounded-none xl:border-0 xl:border-r xl:last:border-r-0",
        disabled && "opacity-80",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-border bg-card text-primary">
          <Icon className="h-4 w-4" strokeWidth={1.5} />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</p>
        </div>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-3">
        <SettingsField label="Провайдер">
          <Select value={provider} onValueChange={onProviderChange} disabled={disabled}>
            <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              {LLM_PROVIDERS.map((p) => (
                <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="Модель">
          <ProviderModelPicker
            provider={provider}
            value={model}
            availableModels={availableModels}
            disabled={disabled}
            refreshing={refreshing}
            onChange={onModelChange}
            onRefresh={onRefresh}
          />
        </SettingsField>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-3 text-xs text-muted-foreground">
        <span>{getProviderLabel(provider)}</span>
        <span>{availableModels.length ? `${availableModels.length} в каталоге` : "Ручной ввод"}</span>
      </div>
    </div>
  );
}
