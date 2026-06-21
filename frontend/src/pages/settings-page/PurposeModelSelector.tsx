import type { ElementType } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { getProviderLabel, LLM_PROVIDERS } from "./constants";

type PurposeModelSelectorProps = {
  label: string;
  description: string;
  icon: ElementType;
  provider: string;
  model: string;
  availableModels: string[];
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
  onProviderChange,
  onModelChange,
  onRefresh,
  refreshing,
}: PurposeModelSelectorProps) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-secondary/20 p-4">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-background text-primary">
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground uppercase">Провайдер</label>
          <Select value={provider} onValueChange={onProviderChange}>
            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {LLM_PROVIDERS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground uppercase">Модель</label>
          {availableModels.length > 0 ? (
            <Select value={model} onValueChange={onModelChange}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {availableModels.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          ) : (
            <div className="flex gap-1.5">
              <Input value={model} onChange={(e) => onModelChange(e.target.value)} placeholder="Model name" className="h-8 text-xs" />
              <Button size="icon" variant="outline" className="h-8 w-8 shrink-0" onClick={onRefresh} disabled={refreshing}>
                <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
              </Button>
            </div>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{getProviderLabel(provider)}</span>
        <span>{availableModels.length ? `${availableModels.length} моделей в каталоге` : "Ручной ввод модели"}</span>
      </div>
      {availableModels.length > 0 && (
        <Button size="sm" variant="ghost" className="h-7 justify-start px-2 text-xs text-muted-foreground" onClick={onRefresh} disabled={refreshing}>
          <RefreshCw className={cn("h-2.5 w-2.5", refreshing && "animate-spin")} /> Обновить список
        </Button>
      )}
    </div>
  );
}
