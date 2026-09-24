import { useMemo, useState } from "react";
import { Check, ChevronsUpDown, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export type ModelCatalogFilter = "all" | "free" | "paid";

type ProviderModelPickerProps = {
  provider: string;
  value: string;
  availableModels: string[];
  disabled?: boolean;
  refreshing?: boolean;
  placeholder?: string;
  onChange: (model: string) => void;
  onRefresh?: () => void;
};

function isFreeModel(modelId: string): boolean {
  return modelId.trim().toLowerCase().endsWith(":free");
}

function filterModels(models: string[], catalogFilter: ModelCatalogFilter): string[] {
  if (catalogFilter === "free") return models.filter(isFreeModel);
  if (catalogFilter === "paid") return models.filter((model) => !isFreeModel(model));
  return models;
}

export function ProviderModelPicker({
  provider,
  value,
  availableModels,
  disabled = false,
  refreshing = false,
  placeholder,
  onChange,
  onRefresh,
}: ProviderModelPickerProps) {
  const [open, setOpen] = useState(false);
  const [catalogFilter, setCatalogFilter] = useState<ModelCatalogFilter>("all");
  const isOpenRouter = provider === "openrouter";
  const inputPlaceholder =
    placeholder ||
    (isOpenRouter ? "z-ai/glm-5.2:free или id с openrouter.ai" : "Название модели");

  const filteredModels = useMemo(
    () => filterModels(availableModels, isOpenRouter ? catalogFilter : "all"),
    [availableModels, catalogFilter, isOpenRouter],
  );

  const freeCount = useMemo(
    () => (isOpenRouter ? availableModels.filter(isFreeModel).length : 0),
    [availableModels, isOpenRouter],
  );
  const paidCount = availableModels.length - freeCount;

  return (
    <div className="space-y-2">
      <div className="flex gap-1.5">
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onBlur={() => {
            const trimmed = value.trim();
            if (trimmed !== value) onChange(trimmed);
          }}
          placeholder={inputPlaceholder}
          className="h-9 min-w-0 flex-1 font-mono text-sm"
          disabled={disabled}
          spellCheck={false}
          autoComplete="off"
        />
        {availableModels.length > 0 ? (
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
              <Button
                type="button"
                size="icon"
                variant="outline"
                className="h-9 w-9 shrink-0"
                disabled={disabled}
                aria-label="Выбрать из каталога"
              >
                <ChevronsUpDown className="h-3.5 w-3.5" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[min(28rem,calc(100vw-2rem))] p-0" align="end">
              <Command>
                <CommandInput placeholder="Поиск модели…" />
                <CommandList>
                  <CommandEmpty>Ничего не найдено. Можно вставить id вручную.</CommandEmpty>
                  <CommandGroup heading={`${filteredModels.length} в списке`}>
                    {filteredModels.map((modelId) => (
                      <CommandItem
                        key={modelId}
                        value={modelId}
                        onSelect={() => {
                          onChange(modelId);
                          setOpen(false);
                        }}
                        className="font-mono text-xs"
                      >
                        <Check
                          className={cn(
                            "mr-2 h-3.5 w-3.5 shrink-0",
                            value === modelId ? "opacity-100" : "opacity-0",
                          )}
                        />
                        <span className="min-w-0 flex-1 truncate">{modelId}</span>
                        {isFreeModel(modelId) ? (
                          <span className="ml-2 shrink-0 text-[10px] uppercase tracking-wide text-success">
                            free
                          </span>
                        ) : null}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        ) : null}
        {onRefresh ? (
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-9 w-9 shrink-0"
            onClick={onRefresh}
            disabled={disabled || refreshing}
            aria-label="Обновить каталог"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
          </Button>
        ) : null}
      </div>

      {isOpenRouter && availableModels.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {(
            [
              { id: "all", label: "Все", count: availableModels.length },
              { id: "free", label: "Free", count: freeCount },
              { id: "paid", label: "Paid", count: paidCount },
            ] as const
          ).map((option) => (
            <button
              key={option.id}
              type="button"
              disabled={disabled}
              onClick={() => setCatalogFilter(option.id)}
              className={cn(
                "rounded-sm border px-2 py-0.5 text-[11px] transition-colors",
                catalogFilter === option.id
                  ? "border-primary/40 bg-primary/10 text-foreground"
                  : "border-border bg-surface-0/40 text-muted-foreground hover:border-border hover:bg-surface-1/60",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              {option.label}
              <span className="ml-1 tabular-nums opacity-70">{option.count}</span>
            </button>
          ))}
          <span className="text-[11px] text-muted-foreground">
            или вставьте id с openrouter.ai/models
          </span>
        </div>
      ) : null}
    </div>
  );
}
