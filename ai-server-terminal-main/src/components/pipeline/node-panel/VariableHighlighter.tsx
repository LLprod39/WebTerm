import { useLayoutEffect, useMemo, useRef } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { t, type NodePanelLang } from "./shared";
import { useVariables } from "./useVariables";

type VariableHighlighterProps = {
  id: string;
  lang: NodePanelLang;
  label: string;
  description: string;
  value: string;
  placeholder?: string;
  minRows?: number;
  readOnly?: boolean;
  onChange: (value: string) => void;
};

export function VariableHighlighter({
  id,
  lang,
  label,
  description,
  value,
  placeholder,
  minRows = 4,
  readOnly = false,
  onChange,
}: VariableHighlighterProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const variables = useVariables(value);
  const minHeightClassName = useMemo(() => {
    if (minRows >= 8) return "min-h-[184px]";
    if (minRows >= 6) return "min-h-[144px]";
    if (minRows >= 5) return "min-h-[124px]";
    return "min-h-[96px]";
  }, [minRows]);
  const hasDoubleBraceToken = variables.some((variable) =>
    variable.occurrences.some((occurrence) => occurrence.raw.startsWith("{{")),
  );

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.max(textarea.scrollHeight, minRows * 24)}px`;
  }, [minRows, value]);

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <Label htmlFor={id} className="text-sm font-semibold text-foreground">
          {label}
        </Label>
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      </div>

      <Textarea
        ref={textareaRef}
        id={id}
        value={value}
        placeholder={placeholder}
        readOnly={readOnly}
        rows={minRows}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "resize-none rounded-2xl border-border/70 bg-background/70 text-sm leading-relaxed",
          minHeightClassName,
          readOnly && "cursor-text",
        )}
      />

      {variables.length ? (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {variables.map((variable) => (
              <button
                key={variable.name}
                type="button"
                onClick={() => {
                  const textarea = textareaRef.current;
                  const occurrence = variable.occurrences[0];
                  if (!textarea || !occurrence) return;
                  textarea.focus();
                  textarea.setSelectionRange(occurrence.start, occurrence.end);
                }}
                className="rounded-full border border-primary/25 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary transition-colors hover:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {`{{${variable.name}}}`}
              </button>
            ))}
          </div>

          {hasDoubleBraceToken ? (
            <p className="text-[11px] text-amber-200">
              {t(
                lang,
                "Runtime сейчас подставляет одинарные плейсхолдеры вида {variable}. Двойные скобки подсвечиваются для удобства редактирования.",
                "Runtime currently substitutes single-brace placeholders like {variable}. Double-brace tags are highlighted for editing only.",
              )}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
