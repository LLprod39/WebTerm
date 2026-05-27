import { useMemo, useState } from "react";
import { Check, HelpCircle, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import type { AiMessage } from "./ai-types";

interface AiQuestionCardProps {
  msg: AiMessage;
  onReply?: (qId: string, text: string) => void;
}

function fillTemplate(template: string, values: Record<string, string | number>) {
  return Object.entries(values).reduce(
    (result, [key, value]) => result.replaceAll(`{${key}}`, String(value)),
    template,
  );
}

function buildReply(selectedValues: string[], freeText: string) {
  const text = freeText.trim();
  if (selectedValues.length > 0 && text) {
    return `${selectedValues.join(", ")}\n\n${text}`;
  }
  if (selectedValues.length > 0) {
    return selectedValues.join(", ");
  }
  return text;
}

export function AiQuestionCard({ msg, onReply }: AiQuestionCardProps) {
  const { t } = useI18n();
  const [answer, setAnswer] = useState("");
  const [selectedValues, setSelectedValues] = useState<string[]>([]);

  const options = msg.questionOptions ?? [];
  const allowMultiple = Boolean(msg.questionAllowMultiple);
  const answered = Boolean(msg.questionAnswered);
  const freeTextAllowed = msg.questionFreeTextAllowed !== false || options.length === 0;
  const sourceLabel = msg.questionSource === "agent"
    ? t("terminal.ai.question.source.agent")
    : t("terminal.ai.question.source.default");

  const replyText = useMemo(
    () => buildReply(selectedValues, answer),
    [answer, selectedValues],
  );

  const submit = (text: string) => {
    const clean = text.trim();
    if (!clean || !msg.qId || answered) {
      return;
    }
    onReply?.(msg.qId, clean);
  };

  const toggleOption = (value: string) => {
    if (!allowMultiple) {
      submit(value);
      return;
    }
    setSelectedValues((current) => (
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value]
    ));
  };

  return (
    <div className="relative overflow-hidden rounded-md border border-border/60 bg-card/80">
      <span className="absolute inset-y-0 left-0 w-0.5 bg-primary/80" aria-hidden="true" />
      <div className="flex items-center justify-between gap-2 border-b border-border/50 px-4 py-2 pl-[18px] text-[12px] font-medium text-foreground">
        <div className="flex items-center gap-2">
          <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
          <span>{t("terminal.ai.question.title")}</span>
        </div>
        <span className="rounded border border-border/50 bg-background/50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          {sourceLabel}
        </span>
      </div>
      <div className="space-y-2.5 px-4 py-3 pl-[18px]">
        <p className="text-[13px] leading-relaxed text-foreground">{msg.question || msg.content}</p>
        {msg.questionCmd ? (
          <code className="block rounded border border-border/40 bg-background/60 px-2.5 py-1.5 text-xs font-mono text-muted-foreground">
            $ {msg.questionCmd}
          </code>
        ) : null}
        {msg.questionExitCode !== undefined ? (
          <p className="text-xs text-muted-foreground">{fillTemplate(t("terminal.ai.question.exitCode"), { code: msg.questionExitCode })}</p>
        ) : null}
        {options.length > 0 ? (
          <div className="space-y-2">
            <div className="text-[11px] text-muted-foreground">
              {allowMultiple ? t("terminal.ai.question.pickMany") : t("terminal.ai.question.pickOne")}
            </div>
            <div className="grid gap-2">
              {options.map((option) => {
                const selected = selectedValues.includes(option.value);
                return (
                  <button
                    key={`${option.value}-${option.label}`}
                    type="button"
                    onClick={() => toggleOption(option.value)}
                    disabled={answered}
                    className={`flex items-start gap-2 rounded-md border px-3 py-2 text-left transition-colors ${selected ? "border-primary/50 bg-primary/10 text-foreground" : "border-border/50 bg-background/40 text-foreground hover:bg-secondary/40"} ${answered ? "cursor-default opacity-70" : ""}`}
                  >
                    <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border ${selected ? "border-primary bg-primary text-primary-foreground" : "border-border/60 text-transparent"}`}>
                      <Check className="h-3 w-3" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium">{option.label}</span>
                      {option.description ? (
                        <span className="mt-0.5 block text-[11px] text-muted-foreground">{option.description}</span>
                      ) : null}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
        {freeTextAllowed && !answered ? (
          <div className="space-y-1.5">
            {options.length > 0 ? (
              <div className="text-[11px] text-muted-foreground">{t("terminal.ai.question.customAnswer")}</div>
            ) : null}
            <div className="flex gap-1.5">
              <input
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    submit(replyText);
                  }
                }}
                placeholder={msg.questionPlaceholder || t("terminal.ai.question.answerPlaceholder")}
                aria-label="Reply to AI question"
                autoFocus
                className="flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-[13px] text-foreground transition-colors placeholder:text-muted-foreground/60 focus:border-primary/60 focus:outline-none"
              />
              <Button size="sm" className="h-8 gap-1 px-3 text-xs" onClick={() => submit(replyText)} disabled={!replyText.trim()}>
                <Send className="h-3 w-3" />
                {t("terminal.ai.question.submit")}
              </Button>
            </div>
          </div>
        ) : null}
        {!freeTextAllowed && allowMultiple && !answered ? (
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-muted-foreground">{fillTemplate(t("terminal.ai.question.selected"), { count: selectedValues.length })}</span>
            <Button size="sm" className="h-8 gap-1 px-3 text-xs" onClick={() => submit(replyText)} disabled={!selectedValues.length}>
              <Send className="h-3 w-3" />
              {t("terminal.ai.question.submit")}
            </Button>
          </div>
        ) : null}
        {answered ? (
          <p className="text-xs italic text-muted-foreground">
            {msg.questionAnswer
              ? fillTemplate(t("terminal.ai.question.sentWithAnswer"), { answer: msg.questionAnswer })
              : t("terminal.ai.question.sent")}
          </p>
        ) : null}
      </div>
    </div>
  );
}
