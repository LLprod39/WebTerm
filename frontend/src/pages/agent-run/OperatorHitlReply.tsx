import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { RefreshCw, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type Props = {
  question: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: (answer: string) => void | Promise<void>;
  submitting?: boolean;
  /** Compact single-line layout for agent list rows. */
  compact?: boolean;
  autoFocus?: boolean;
  className?: string;
};

const QUICK = ["да", "нет"] as const;

/**
 * Minimal operator reply for agent ask_user / SAFE approval prompts.
 * Quick chips + short field + one send — no confirm dialog.
 */
export function OperatorHitlReply({
  question,
  value,
  onChange,
  onSubmit,
  submitting = false,
  compact = false,
  autoFocus = false,
  className,
}: Props) {
  const { lang } = useI18n();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!autoFocus) return;
    const id = window.setTimeout(() => inputRef.current?.focus(), 50);
    return () => window.clearTimeout(id);
  }, [autoFocus, question]);

  const send = async (raw: string) => {
    const answer = raw.trim();
    if (!answer || submitting) return;
    setLocalError(null);
    try {
      await onSubmit(answer);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : localize(lang, "Не удалось отправить", "Failed to send"));
    }
  };

  return (
    <section
      aria-labelledby={`${inputId}-heading`}
      className={cn(
        "rounded-sm border border-warning/35 bg-warning/10",
        compact ? "p-2.5" : "p-4",
        className,
      )}
    >
      <h2 id={`${inputId}-heading`} className={cn("font-semibold text-foreground", compact ? "text-xs" : "text-sm")}>
        {localize(lang, "Агент ждёт вашего ответа", "Agent is waiting for your reply")}
      </h2>
      <p className={cn("mt-1 whitespace-pre-wrap break-words text-muted-foreground", compact ? "text-xs leading-4" : "text-sm leading-6")}>
        {question}
      </p>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {QUICK.map((chip) => (
          <Button
            key={chip}
            type="button"
            size="sm"
            variant="outline"
            className="h-8 px-3 capitalize"
            disabled={submitting}
            onClick={() => void send(chip)}
          >
            {chip}
          </Button>
        ))}
      </div>

      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
        {compact ? (
          <Input
            id={inputId}
            ref={inputRef as RefObject<HTMLInputElement>}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={localize(lang, "Короткий ответ…", "Short reply…")}
            className="h-9"
            disabled={submitting}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void send(value);
              }
            }}
          />
        ) : (
          <textarea
            id={inputId}
            ref={inputRef as RefObject<HTMLTextAreaElement>}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={localize(lang, "Или напишите ответ…", "Or type a reply…")}
            aria-label={localize(lang, "Ответ агенту", "Reply to agent")}
            className="min-h-20 w-full flex-1 rounded-sm border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled={submitting}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void send(value);
              }
            }}
          />
        )}
        <Button
          type="button"
          size="sm"
          className={cn("h-9 shrink-0 gap-1.5", !compact && "sm:h-10")}
          disabled={submitting || !value.trim()}
          onClick={() => void send(value)}
        >
          {submitting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Send className="h-3.5 w-3.5" aria-hidden />}
          {submitting
            ? localize(lang, "Отправляем…", "Sending…")
            : localize(lang, "Отправить", "Send")}
        </Button>
      </div>
      {localError ? (
        <p role="alert" className="mt-2 text-xs text-destructive">{localError}</p>
      ) : null}
    </section>
  );
}
