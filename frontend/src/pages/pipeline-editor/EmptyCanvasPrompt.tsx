import { Clock, Link2, Play } from "lucide-react";

import { Button } from "@/components/ui/button";

import { localize } from "./presentation";

export type EmptyCanvasTriggerType = "trigger/manual" | "trigger/webhook" | "trigger/schedule";

const TRIGGER_OPTIONS: Array<{
  type: EmptyCanvasTriggerType;
  labelRu: string;
  labelEn: string;
  icon: typeof Play;
}> = [
  { type: "trigger/manual", labelRu: "Manual", labelEn: "Manual", icon: Play },
  { type: "trigger/webhook", labelRu: "Webhook", labelEn: "Webhook", icon: Link2 },
  { type: "trigger/schedule", labelRu: "Schedule", labelEn: "Schedule", icon: Clock },
];

/**
 * Empty-canvas CTA for Studio L→R. Stream B wires this via Canvas `emptySlot`.
 */
export function EmptyCanvasPrompt({
  lang,
  onAddTrigger,
}: {
  lang: "en" | "ru";
  onAddTrigger: (type: EmptyCanvasTriggerType) => void;
}) {
  return (
    <div className="pointer-events-auto select-none space-y-4 text-center">
      <div className="space-y-1.5">
        <p className="text-sm font-semibold text-foreground">
          {localize(lang, "Начните с триггера", "Start with a trigger")}
        </p>
        <p className="mx-auto max-w-xs text-xs text-muted-foreground">
          {localize(lang, "Выберите, как запускать пайплайн.", "Choose how the pipeline should start.")}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {TRIGGER_OPTIONS.map((option) => {
          const Icon = option.icon;
          return (
            <Button
              key={option.type}
              type="button"
              variant="outline"
              size="sm"
              className="h-9 gap-1.5"
              onClick={() => onAddTrigger(option.type)}
            >
              <Icon className="h-3.5 w-3.5 text-warning" />
              {localize(lang, option.labelRu, option.labelEn)}
            </Button>
          );
        })}
      </div>
    </div>
  );
}
