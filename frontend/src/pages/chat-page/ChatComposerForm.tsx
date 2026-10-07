import {
  Bot,
  ChevronDown,
  FileText,
  GitBranch,
  Loader2,
  Plus,
  Send,
  Square,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useRef } from "react";

import { AgentThinking } from "@/boardui/components/application/agent-thinking/agent-thinking";
import { ComposerLoader } from "@/boardui/components/application/composer-loader/composer-loader";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { ComposeCommandPalette } from "./ComposeCommandPalette";
import { PinnedContextChips } from "./PinnedContextChips";
import { CHAT_ATTACH_MAX_FILES } from "./chatAttachments";
import { CHAT_EASE } from "./chatMotion";
import type { ChatPageController } from "./useChatPageController";

type ChatComposerFormProps = {
  c: ChatPageController;
};

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10_240 ? 1 : 0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

const CONTEXT_SOFT_LIMIT = 128_000;

function ContextMeter({ tokensLabel, percent }: { tokensLabel: string | null; percent: number }) {
  const r = 6;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.min(1, Math.max(0, percent / 100)));
  return (
    <div
      className="flex items-center gap-1 rounded-full bg-muted/70 py-1 pe-2 ps-1.5"
      title={tokensLabel ? `${tokensLabel} tok` : undefined}
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
      <span className="text-[11px] tabular-nums text-muted-foreground">
        {tokensLabel ? `${percent}%` : "—"}
      </span>
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
    operatorWs,
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
  const projectLabel = localize(lang, "WebTerm", "WebTerm");
  const thinkingLabel =
    operatorWs?.phase === "tools"
      ? localize(lang, "Working…", "Working…")
      : operatorWs?.phase === "streaming"
        ? localize(lang, "Writing…", "Writing…")
        : "Thinking…";

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
                className="inline-flex max-w-[16rem] items-center gap-1 rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 text-[11px] text-foreground"
              >
                <FileText className="h-3 w-3 shrink-0 opacity-70" strokeWidth={1.75} />
                <span className="truncate font-medium tracking-tight">{file.name}</span>
                <span className="shrink-0 text-muted-foreground/70">{formatBytes(file.size)}</span>
                <button
                  type="button"
                  className="rounded-full p-0.5 opacity-70 hover:bg-muted hover:opacity-100"
                  onClick={() => removeAttachedFile(file.id)}
                  aria-label={localize(lang, "Убрать файл", "Remove file")}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <AnimatePresence initial={false}>
          {isBusy ? (
            <motion.div
              key="agent-thinking"
              initial={reduceMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: 2 }}
              transition={{ duration: reduceMotion ? 0 : 0.18, ease: CHAT_EASE }}
              className="mb-1.5 px-1"
            >
              <AgentThinking
                label={thinkingLabel}
                variant={operatorWs?.phase === "tools" ? "spin" : "wave"}
                tone="default"
                showTimer
              />
            </motion.div>
          ) : null}
        </AnimatePresence>

        <ComposerLoader
          active={isBusy && !reduceMotion}
          colors={["#5eead4", "#46baec", "#c8f542", "#49d4d1"]}
          surface
        >
          <div
            className={cn(
              "relative flex min-h-[52px] w-full items-end gap-2 rounded-full border border-border/70 py-2 pe-2 ps-2 transition-[border-color] duration-200",
              "bg-transparent shadow-none focus-within:border-primary/35 focus-within:ring-2 focus-within:ring-primary/15",
              !isBusy && "bg-muted/30 shadow-sm",
            )}
          >
            <button
              type="button"
              className="flex size-9 shrink-0 items-center justify-center rounded-full border border-border/60 bg-background/80 text-foreground transition-colors hover:bg-muted disabled:opacity-50"
              onClick={openFilePicker}
              disabled={isBusy || attachBusy || attachedFiles.length >= CHAT_ATTACH_MAX_FILES}
              aria-label={localize(lang, "Файл / проект", "File / project")}
            >
              {attachBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            </button>

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
                    : localize(
                        lang,
                        "Что нужно сделать? Для точного сервера введите @",
                        "What should I do? Type @ for an exact server",
                      )
              }
              aria-label={localize(lang, "Сообщение", "Message")}
              className="max-h-36 min-h-[24px] flex-1 resize-none border-0 bg-transparent px-1 py-2 text-[14px] leading-5 shadow-none focus-visible:ring-0"
              rows={1}
            />

            <div className="flex shrink-0 items-center gap-1.5 pb-0.5">
              <span className="hidden h-8 items-center gap-0.5 rounded-xl border border-border/50 bg-background/70 px-2 text-[12px] text-muted-foreground sm:inline-flex">
                <Bot className="h-3.5 w-3.5" />
                <span>Operator</span>
                <ChevronDown className="h-3.5 w-3.5 opacity-60" />
              </span>
              <div className="h-9 w-9 shrink-0">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={isBusy ? "stop" : "send"}
                    initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={reduceMotion ? undefined : { opacity: 0, scale: 0.96 }}
                    transition={{ duration: reduceMotion ? 0 : 0.16, ease: CHAT_EASE }}
                    className="h-9 w-9"
                  >
                    {isBusy ? (
                      <Button
                        type="button"
                        size="icon"
                        variant="secondary"
                        className="h-9 w-9 rounded-full"
                        onClick={handleStop}
                        aria-label={localize(lang, "Остановить", "Stop")}
                      >
                        <Square className="h-3.5 w-3.5 fill-current" />
                      </Button>
                    ) : (
                      <Button
                        type="submit"
                        size="icon"
                        className="h-9 w-9 rounded-full"
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

        <div className="mt-2 flex min-w-0 items-center justify-between gap-3 px-1 text-[11px] text-muted-foreground">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1">
              <GitBranch className="h-3.5 w-3.5" />
              <span className="truncate">main</span>
            </span>
            <button
              type="button"
              className="inline-flex max-w-[10rem] items-center gap-0.5 truncate rounded-md px-1 py-0.5 hover:bg-muted/50 hover:text-foreground"
              onClick={() => textareaRef.current?.focus()}
            >
              <span className="truncate">{projectLabel}</span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
            </button>
            <span className="inline-flex items-center gap-0.5">
              <span>Agent</span>
              <ChevronDown className="h-3.5 w-3.5 opacity-60" />
            </span>
            <ContextMeter tokensLabel={sessionTokens} percent={contextPercent} />
          </div>
          <span className="hidden min-w-0 truncate text-right text-[10.5px] text-muted-foreground/65 sm:inline">
            {localize(
              lang,
              "@ — точный сервер · Enter — отправить · Shift+Enter — новая строка",
              "@ — exact server · Enter to send · Shift+Enter for a new line",
            )}
          </span>
        </div>
      </div>
    </form>
  );
}
