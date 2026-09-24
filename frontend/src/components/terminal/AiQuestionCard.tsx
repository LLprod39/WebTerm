import { useEffect, useMemo, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
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

/** Pull a long shell fragment out of prose so the card isn't a wall of text. */
export function splitQuestionContent(question: string, explicitCmd?: string) {
  const raw = question.trim();
  if (explicitCmd?.trim()) {
    const cmd = explicitCmd.trim();
    let prose = raw;
    if (prose.includes(cmd)) {
      prose = prose.replace(cmd, " ").replace(/\s{2,}/g, " ").trim();
    }
    prose = prose.replace(/[:：]\s*$/, "").trim();
    return { prose: prose || raw.slice(0, 120), cmd };
  }

  const tick = raw.match(/`([^`]{20,})`/);
  if (tick?.[1]) {
    const cmd = tick[1].trim();
    const prose = raw.replace(tick[0], " ").replace(/\s{2,}/g, " ").trim();
    return { prose: prose || raw.slice(0, 120), cmd };
  }

  const shellish = raw.match(
    /((?:sudo\s+)?(?:docker|systemctl|apt|yum|dnf|kubectl|ssh|curl|wget|bash|sh)\b[\s\S]{25,})/i,
  );
  if (shellish?.[1] && shellish[1].length >= 40) {
    const cmd = shellish[1].trim();
    const prose = raw.replace(cmd, " ").replace(/\s{2,}/g, " ").trim();
    return { prose: prose || raw.slice(0, 120), cmd };
  }

  return { prose: raw, cmd: undefined as string | undefined };
}

function isAllowOption(label: string, value: string) {
  return /allow|разреш|approve|once|один/i.test(label) || /allow|approve|once/i.test(value);
}

function isBlockOption(label: string, value: string) {
  return /block|запрет|отклон|deny|cancel/i.test(label) || /block|deny|cancel/i.test(value);
}

/**
 * Terminal-native confirm strip — Linear restraint, no nested cards,
 * no uppercase chrome, no colored option mosaics.
 */
export function AiQuestionCard({ msg, onReply }: AiQuestionCardProps) {
  const { t } = useI18n();
  const [answer, setAnswer] = useState("");
  const [selectedValues, setSelectedValues] = useState<string[]>([]);
  const [cmdOpen, setCmdOpen] = useState(false);

  const options = msg.questionOptions ?? [];
  const allowMultiple = Boolean(msg.questionAllowMultiple);
  const answered = Boolean(msg.questionAnswered);
  const freeTextAllowed = msg.questionFreeTextAllowed !== false || options.length === 0;

  const { prose, cmd } = useMemo(
    () => splitQuestionContent(msg.question || msg.content || "", msg.questionCmd),
    [msg.content, msg.question, msg.questionCmd],
  );

  // With options + command, prose is noise — keep only a short lead if tiny.
  const showProse = Boolean(prose) && !(cmd && options.length > 0 && prose.length > 90);

  const replyText = useMemo(
    () => buildReply(selectedValues, answer),
    [answer, selectedValues],
  );

  const submit = (text: string) => {
    const clean = text.trim();
    if (!clean || !msg.qId || answered) return;
    onReply?.(msg.qId, clean);
  };

  const toggleOption = (value: string) => {
    if (!allowMultiple) {
      submit(value);
      return;
    }
    setSelectedValues((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  };

  const answerPreview = (msg.questionAnswer || "").trim();
  const matchedOption = options.find(
    (o) => o.value === answerPreview || o.label === answerPreview,
  );

  useEffect(() => {
    if (answered) setCmdOpen(false);
  }, [answered]);

  // Done — one quiet line, nothing else.
  if (answered) {
    return (
      <div className="flex items-center gap-2 py-0.5 text-[12px] text-muted-foreground">
        <span className="text-success" aria-hidden="true">
          ✓
        </span>
        <span className="min-w-0 truncate">
          {matchedOption?.label || answerPreview || t("terminal.ai.question.sent")}
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-2 border-l-2 border-border py-0.5 pl-3">
      <div className="flex items-baseline gap-2 text-[12px]">
        <span className="font-medium text-foreground">
          {t("terminal.ai.question.title")}
        </span>
        {msg.questionExitCode !== undefined ? (
          <span className="text-muted-foreground">
            {fillTemplate(t("terminal.ai.question.exitCode"), { code: msg.questionExitCode })}
          </span>
        ) : null}
      </div>

      {showProse ? (
        <p className="text-[12px] leading-snug text-muted-foreground line-clamp-2" title={prose}>
          {prose}
        </p>
      ) : null}

      {cmd ? (
        <button
          type="button"
          onClick={() => setCmdOpen((v) => !v)}
          className="block w-full text-left"
          title={cmdOpen ? t("terminal.ai.question.showLess") : t("terminal.ai.question.showMore")}
        >
          <code
            className={cn(
              "block font-mono text-[11px] leading-snug text-foreground/80",
              cmdOpen ? "whitespace-pre-wrap break-all" : "truncate",
            )}
          >
            $ {cmd}
          </code>
        </button>
      ) : null}

      {options.length > 0 ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5">
          {options.map((option) => {
            const selected = selectedValues.includes(option.value);
            const allow = isAllowOption(option.label, option.value);
            const block = isBlockOption(option.label, option.value);
            return (
              <button
                key={`${option.value}-${option.label}`}
                type="button"
                onClick={() => toggleOption(option.value)}
                title={option.description || undefined}
                className={cn(
                  "text-[12px] font-medium transition-colors",
                  selected && "underline underline-offset-4",
                  allow && "text-success hover:text-success/80",
                  block && "text-destructive hover:text-destructive/80",
                  !allow && !block && "text-foreground hover:text-foreground/70",
                )}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      ) : null}

      {freeTextAllowed ? (
        <div className="flex gap-1.5 pt-0.5">
          <input
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit(replyText);
            }}
            placeholder={
              options.length > 0
                ? t("terminal.ai.question.customAnswer")
                : msg.questionPlaceholder || t("terminal.ai.question.answerPlaceholder")
            }
            aria-label="Reply to AI question"
            autoFocus={options.length === 0}
            className="min-w-0 flex-1 border-0 border-b border-border/60 bg-transparent px-0 py-1 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-foreground/40"
          />
          {(options.length === 0 || allowMultiple || answer.trim()) && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1 px-2 text-xs"
              onClick={() => submit(replyText)}
              disabled={!replyText.trim()}
            >
              <Send className="h-3 w-3" />
              {t("terminal.ai.question.submit")}
            </Button>
          )}
        </div>
      ) : null}

      {!freeTextAllowed && allowMultiple ? (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={() => submit(replyText)}
            disabled={!selectedValues.length}
          >
            {t("terminal.ai.question.submit")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
