import type { ElementType } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsField } from "@/components/settings/SettingsPageShell";
import { cn } from "@/lib/utils";
import { getProviderLabel, LLM_PROVIDERS } from "./constants";

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
          {availableModels.length > 0 ? (
            <Select value={model} onValueChange={onModelChange} disabled={disabled}>
              <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {availableModels.map((m) => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <div className="flex gap-1.5">
              <Input
                value={model}
                onChange={(e) => onModelChange(e.target.value)}
                placeholder="Model name"
                className="h-9 text-sm"
                disabled={disabled}
              />
              <Button
                size="icon"
                variant="outline"
                className="h-9 w-9 shrink-0"
                onClick={onRefresh}
                disabled={disabled || refreshing}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
              </Button>
            </div>
          )}
        </SettingsField>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-3 text-xs text-muted-foreground">
        <span>{getProviderLabel(provider)}</span>
        <span>{availableModels.length ? `${availableModels.length} в каталоге` : "Ручной ввод"}</span>
      </div>

      {availableModels.length > 0 && !disabled ? (
        <Button
          size="sm"
          variant="ghost"
          className="h-8 justify-start px-2 text-xs text-muted-foreground"
          onClick={onRefresh}
          disabled={refreshing}
        >
          <RefreshCw className={cn("mr-1.5 h-3 w-3", refreshing && "animate-spin")} />
          Обновить список
        </Button>
      ) : null}
    </div>
  );
}
