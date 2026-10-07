import {
  FileText,
  Loader2,
  Plus,
  Send,
  Square,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useRef } from "react";

import { ComposerLoader } from "@/boardui/components/application/composer-loader/composer-loader";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import type { OperatorAutonomyMode } from "@/api";

import { ComposeCommandPalette } from "./ComposeCommandPalette";
import { PinnedContextChips } from "./PinnedContextChips";
import { CHAT_ATTACH_MAX_FILES } from "./chatAttachments";
import { CHAT_EASE } from "./chatMotion";
import type { ChatPageController } from "./useChatPageController";
import { DEFAULT_AUTONOMY_MODE } from "./useChatPagePins";

const AUTONOMY_OPTIONS: Array<{
  value: OperatorAutonomyMode;
  labelRu: string;
  labelEn: string;
  hintRu: string;
  hintEn: string;
}> = [
  {
    value: "confirm_each",
    labelRu: "Каждый шаг",
    labelEn: "Confirm each",
    hintRu: "Подтверждать каждое действие",
    hintEn: "Confirm every mutating action",
  },
  {
    value: "plan_once",
    labelRu: "План целиком",
    labelEn: "Plan once",
    hintRu: "Один раз утвердить план",
    hintEn: "Approve the plan once, then auto-run steps",
  },
  {
    value: "autonomous",
    labelRu: "Автономно",
    labelEn: "Autonomous",
    hintRu: "Без подтверждений (кроме опасных)",
    hintEn: "Auto-run except typed-dangerous actions",
  },
];

function AutonomyModeSwitcher({
  lang,
  value,
  onChange,
  disabled,
}: {
  lang: "ru" | "en" | string;
  value: OperatorAutonomyMode;
  onChange: (mode: OperatorAutonomyMode) => void;
  disabled?: boolean;
}) {
  const current = AUTONOMY_OPTIONS.find((opt) => opt.value === value) || AUTONOMY_OPTIONS[0];
  return (
    <label
      className="inline-flex h-8 max-w-[12rem] items-center gap-1 rounded-lg border border-border/50 bg-background/70 px-2 text-[11px] text-muted-foreground"
      title={localize(lang, current.hintRu, current.hintEn)}
    >
      <span className="sr-only">
        {localize(lang, "Режим автономии", "Autonomy mode")}
      </span>
      <select
        data-testid="autonomy-mode-switcher"
        className="max-w-[9.5rem] truncate border-0 bg-transparent py-0 pe-0 text-[11px] text-foreground outline-none disabled:opacity-50"
        value={value}
        disabled={disabled}
        aria-label={localize(lang, "Режим автономии", "Autonomy mode")}
        onChange={(event) => onChange(event.target.value as OperatorAutonomyMode)}
      >
        {AUTONOMY_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {localize(lang, opt.labelRu, opt.labelEn)}
          </option>
        ))}
      </select>
    </label>
  );
}

type ChatComposerFormProps = {
  c: ChatPageController;
};

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10_240 ? 1 : 0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

const CONTEXT_SOFT_LIMIT = 128_000;

/** Soft theme-token loader palette — no neon hex. */
const LOADER_COLORS: [string, string, string, string] = [
  "hsl(var(--ai))",
  "hsl(var(--primary))",
  "hsl(var(--info))",
  "hsl(var(--success))",
];

function ContextMeter({ tokensLabel, percent }: { tokensLabel: string | null; percent: number }) {
  if (!tokensLabel) return null;
  const r = 6;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.min(1, Math.max(0, percent / 100)));
  return (
    <div
      className="flex items-center gap-1 rounded-md bg-muted/70 py-1 pe-2 ps-1.5"
      title={`${tokensLabel} tok`}
    >
      <svg aria-hidden width="16" height="16" viewBox="0 0 16 16" className="shrink-0 -rotate-90">
        <circle cx="8" cy="8" r={r} fill="none" stroke="hsl(var(--border))" strokeWidth="2.5" />
        <circle
          cx="8"
          cy="8"
          r={r}
          fill="none"
          stroke="hsl(var(--muted-foreground))"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={`${circ}`}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="text-[11px] tabular-nums text-muted-foreground">{percent}%</span>
    </div>
  );
}

export function ChatComposerForm({ c }: ChatComposerFormProps) {
  const reduceMotion = useReducedMotion();
  const dropDepthRef = useRef(0);
  const {
    lang,
    draft,
    setDraft,
    caret,
    setCaret,
    paletteOpen,
    setPaletteOpen,
    pinnedServers,
    unpinServer,
    pinServer,
    paletteRef,
    textareaRef,
    fileInputRef,
    attachedFiles,
    attachBusy,
    attachFilesFromList,
    removeAttachedFile,
    openFilePicker,
    isBusy,
    pendingUserText,
    handleStop,
    submitMessage,
    sessionTokens,
    activeChat,
    autonomyMode = DEFAULT_AUTONOMY_MODE,
    setAutonomyMode,
  } = c;
  const reconcilingUserMessage = Boolean(pendingUserText) && !isBusy;
  const canSend = Boolean(draft.trim() || attachedFiles.length) && !reconcilingUserMessage && !attachBusy;

  const usageTotal = useMemo(() => {
    const usage = activeChat?.total_usage as { input_tokens?: number; output_tokens?: number } | undefined;
    if (!usage) return 0;
    return Number(usage.input_tokens || 0) + Number(usage.output_tokens || 0);
  }, [activeChat?.total_usage]);
  const contextPercent = usageTotal
    ? Math.min(100, Math.max(1, Math.round((usageTotal / CONTEXT_SOFT_LIMIT) * 100)))
    : 0;

  return (
    <form
      className="shrink-0 px-3 pb-3 pt-1 sm:px-5 sm:pb-4"
      onSubmit={(event) => {
        event.preventDefault();
        submitMessage();
      }}
      onDragEnter={(event) => {
        event.preventDefault();
        dropDepthRef.current += 1;
      }}
      onDragOver={(event) => {
        event.preventDefault();
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        dropDepthRef.current = Math.max(0, dropDepthRef.current - 1);
      }}
      onDrop={(event) => {
        event.preventDefault();
        dropDepthRef.current = 0;
        void attachFilesFromList(event.dataTransfer.files);
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          void attachFilesFromList(event.target.files);
        }}
      />
      <div className="relative mx-auto max-w-[768px]">
        <PinnedContextChips servers={pinnedServers} onUnpinServer={unpinServer} />
        <ComposeCommandPalette
          ref={paletteRef}
          draft={draft}
          caret={caret}
          open={paletteOpen}
          onOpenChange={setPaletteOpen}
          onDraftChange={(next, nextCaret) => {
            setDraft(next);
            if (typeof nextCaret === "number") {
              setCaret(nextCaret);
              requestAnimationFrame(() => {
                const el = textareaRef.current;
                if (el) {
                  el.focus();
                  el.setSelectionRange(nextCaret, nextCaret);
                }
              });
            }
          }}
          pinnedServers={pinnedServers}
          onPinServer={pinServer}
          onUnpinServer={unpinServer}
        />
        {attachedFiles.length ? (
          <div className="mb-2 flex flex-wrap items-center gap-1.5 px-0.5">
            <span className="mr-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
              {localize(lang, "Файлы", "Files")}
            </span>
            {attachedFiles.map((file) => (
              <span
                key={file.id}
                className="inline-flex max-w-[16rem] items-center gap-1 rounded-md border border-border/70 bg-muted/40 px-2 py-0.5 text-[11px] text-foreground"
              >
                <FileText className="h-3 w-3 shrink-0 opacity-70" strokeWidth={1.75} />
                <span className="truncate font-medium tracking-tight">{file.name}</span>
                <span className="shrink-0 text-muted-foreground/70">{formatBytes(file.size)}</span>
                <button
                  type="button"
                  className="rounded-md p-0.5 opacity-70 hover:bg-muted hover:opacity-100"
                  onClick={() => removeAttachedFile(file.id)}
                  aria-label={localize(lang, "Убрать файл", "Remove file")}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <ComposerLoader
          active={isBusy && !reduceMotion}
          colors={LOADER_COLORS}
          surface
          radius={16}
        >
          <div
            className={cn(
              "relative flex w-full flex-col rounded-2xl border border-border/70 transition-[border-radius,box-shadow,background-color] duration-200",
              "bg-transparent shadow-none focus-within:border-primary/35 focus-within:ring-2 focus-within:ring-primary/15",
              !isBusy && "bg-muted/30 shadow-sm",
            )}
            data-composer-shape="block"
          >
            <div className="flex w-full px-2.5 pt-2.5 pb-1.5">
              <Textarea
                ref={textareaRef}
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setCaret(event.target.selectionStart || 0);
                }}
                onSelect={(event) => setCaret(event.currentTarget.selectionStart || 0)}
                onClick={(event) => setCaret(event.currentTarget.selectionStart || 0)}
                onPaste={(event) => {
                  const files = event.clipboardData?.files;
                  if (files?.length) {
                    event.preventDefault();
                    void attachFilesFromList(files);
                  }
                }}
                onKeyDown={(event) => {
                  if (paletteRef.current?.handleKeyDown(event)) {
                    event.preventDefault();
                    return;
                  }
                  if (event.key === "Escape" && isBusy) {
                    event.preventDefault();
                    handleStop();
                    return;
                  }
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    if (canSend) event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder={
                  isBusy
                    ? localize(lang, "Оператор работает… Esc — остановить", "Operator is working… Esc to stop")
                    : reconcilingUserMessage
                      ? localize(lang, "Сохраняю сообщение…", "Saving message…")
                      : localize(lang, "Сообщение или @сервер", "Message or @server")
                }
                aria-label={localize(lang, "Сообщение", "Message")}
                className="max-h-36 min-h-[52px] flex-1 resize-none border-0 bg-transparent px-1 py-2 text-[14px] leading-5 shadow-none focus-visible:ring-0"
                rows={2}
              />
            </div>

            <div className="flex flex-wrap items-center gap-1.5 border-t border-border/45 px-2.5 py-2">
              <button
                type="button"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-background/70 text-foreground transition-colors hover:bg-muted disabled:opacity-50"
                onClick={openFilePicker}
                disabled={isBusy || attachBusy || attachedFiles.length >= CHAT_ATTACH_MAX_FILES}
                aria-label={localize(lang, "Файл / проект", "File / project")}
              >
                {attachBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              </button>
              <AutonomyModeSwitcher
                lang={lang}
                value={autonomyMode}
                onChange={(mode) => setAutonomyMode?.(mode)}
                disabled={isBusy || !setAutonomyMode}
              />
              <ContextMeter tokensLabel={sessionTokens} percent={contextPercent} />
              <div className="ms-auto flex items-center gap-1.5">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={isBusy ? "stop" : "send"}
                    initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={reduceMotion ? undefined : { opacity: 0, scale: 0.96 }}
                    transition={{ duration: reduceMotion ? 0 : 0.16, ease: CHAT_EASE }}
                  >
                    {isBusy ? (
                      <Button
                        type="button"
                        size="icon"
                        variant="secondary"
                        className="h-9 w-9 rounded-xl"
                        onClick={handleStop}
                        aria-label={localize(lang, "Остановить", "Stop")}
                      >
                        <Square className="h-3.5 w-3.5 fill-current" />
                      </Button>
                    ) : (
                      <Button
                        type="submit"
                        size="icon"
                        className="h-9 w-9 rounded-xl"
                        disabled={!canSend}
                        aria-label={localize(lang, "Отправить", "Send")}
                      >
                        <Send className="h-4 w-4" />
                      </Button>
                    )}
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
          </div>
        </ComposerLoader>
      </div>
    </form>
  );
}
