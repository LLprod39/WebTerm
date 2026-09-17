import { Bot, FileText, Loader2, Paperclip, Send, Square, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { localize } from "@/lib/i18n";

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
  } = c;
  const reconcilingUserMessage = Boolean(pendingUserText) && !isBusy;
  const canSend = Boolean(draft.trim() || attachedFiles.length) && !reconcilingUserMessage && !attachBusy;

  return (
    <form
      className="shrink-0 border-t border-border/50 bg-card/95 px-3 pb-3 pt-2 sm:px-6 sm:pb-4"
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
      <div className="relative mx-auto max-w-[42rem]">
        <PinnedContextChips
          servers={pinnedServers}
          onUnpinServer={unpinServer}
        />
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
                className="inline-flex max-w-[16rem] items-center gap-1 rounded-sm border border-border/70 bg-muted/40 px-2 py-0.5 text-[11px] text-foreground"
                title={
                  file.kind === "text"
                    ? file.truncated
                      ? localize(lang, "Текст усечён для лимита сообщения", "Text truncated for message limit")
                      : localize(lang, "Текст будет отправлен в контекст", "Text will be sent in context")
                    : localize(
                        lang,
                        "Бинарный файл — в контекст попадёт только имя",
                        "Binary file — only the name is sent in context",
                      )
                }
              >
                <FileText className="h-3 w-3 shrink-0 opacity-70" strokeWidth={1.75} />
                <span className="truncate font-medium tracking-tight">{file.name}</span>
                <span className="shrink-0 text-muted-foreground/70">{formatBytes(file.size)}</span>
                <button
                  type="button"
                  className="rounded-sm p-0.5 opacity-70 hover:bg-muted hover:opacity-100"
                  onClick={() => removeAttachedFile(file.id)}
                  aria-label={localize(lang, "Убрать файл", "Remove file")}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        ) : null}
        <div className="rounded-sm border border-border/70 bg-muted/25 p-1.5 transition-[border-color,background-color] duration-200 ease-out focus-within:border-primary/40 focus-within:bg-muted/35 focus-within:ring-2 focus-within:ring-primary/20 motion-reduce:transition-none">
          <div className="flex items-end gap-1">
            <Textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                setCaret(event.target.selectionStart || 0);
              }}
              onSelect={(event) => {
                setCaret(event.currentTarget.selectionStart || 0);
              }}
              onClick={(event) => {
                setCaret(event.currentTarget.selectionStart || 0);
              }}
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
                  if (canSend) {
                    event.currentTarget.form?.requestSubmit();
                  }
                }
              }}
              placeholder={
                isBusy
                  ? localize(lang, "Оператор работает… Esc — остановить", "Operator is working… Esc to stop")
                  : reconcilingUserMessage
                    ? localize(lang, "Сохраняю сообщение…", "Saving message…")
                  : localize(lang, "Что нужно сделать? Для точного сервера введите @", "What should I do? Type @ for an exact server")
              }
              className="max-h-40 min-h-12 flex-1 resize-none border-0 bg-transparent px-3.5 py-2.5 text-[15px] leading-6 shadow-none focus-visible:ring-0"
              rows={1}
            />
            <div className="mb-1 mr-1 h-9 w-9 shrink-0">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={isBusy ? "stop" : "send"}
                  initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={reduceMotion ? undefined : { opacity: 0, scale: 0.96 }}
                  whileTap={reduceMotion ? undefined : { scale: 0.98 }}
                  transition={{ duration: reduceMotion ? 0 : 0.16, ease: CHAT_EASE }}
                  className="h-9 w-9"
                >
                  {isBusy ? (
                    <Button
                      type="button"
                      size="icon"
                      variant="secondary"
                      className="h-9 w-9 rounded-sm"
                      onClick={handleStop}
                      aria-label={localize(lang, "Остановить", "Stop")}
                      title={localize(lang, "Остановить · Esc", "Stop · Esc")}
                    >
                      <Square className="h-3.5 w-3.5 fill-current" />
                    </Button>
                  ) : (
                    <Button
                      type="submit"
                      size="icon"
                      className="h-9 w-9 rounded-sm"
                      disabled={!canSend}
                      aria-label={localize(lang, "Отправить", "Send")}
                      title={localize(lang, "Отправить · Enter", "Send · Enter")}
                    >
                      <Send className="h-4 w-4" />
                    </Button>
                  )}
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
        <div className="mt-2 flex min-w-0 items-center justify-between gap-3 px-1 text-[10.5px] text-muted-foreground/65">
          <button
            type="button"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-1 font-medium transition-colors hover:bg-muted/50 hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
            onClick={openFilePicker}
            disabled={isBusy || attachBusy || attachedFiles.length >= CHAT_ATTACH_MAX_FILES}
            title={localize(
              lang,
              "Прикрепить файлы к сообщению — текст попадёт в контекст модели",
              "Attach files to the message — text is added to model context",
            )}
          >
            {attachBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Paperclip className="h-3.5 w-3.5" />}
            {localize(lang, "Файл / проект", "File / project")}
          </button>
          <span className="hidden min-w-0 truncate text-right sm:inline">
            <Bot className="mr-1 inline h-3 w-3" />
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
