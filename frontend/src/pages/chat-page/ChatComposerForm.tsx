import { Bot, Paperclip, Send, Square } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { localize } from "@/lib/i18n";

import { ComposeCommandPalette } from "./ComposeCommandPalette";
import { PinnedContextChips } from "./PinnedContextChips";
import { CHAT_EASE } from "./chatMotion";
import type { ChatPageController } from "./useChatPageController";

type ChatComposerFormProps = {
  c: ChatPageController;
};

export function ChatComposerForm({ c }: ChatComposerFormProps) {
  const reduceMotion = useReducedMotion();
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
    isBusy,
    pendingUserText,
    handleStop,
    submitMessage,
  } = c;
  const reconcilingUserMessage = Boolean(pendingUserText) && !isBusy;

  return (
    <form
      className="shrink-0 border-t border-border/50 bg-card/95 px-3 pb-3 pt-2 sm:px-6 sm:pb-4"
      onSubmit={(event) => {
        event.preventDefault();
        submitMessage();
      }}
    >
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
        <div className="rounded-2xl border border-border/70 bg-muted/25 p-1.5 shadow-sm transition-[border-color,background-color,box-shadow] duration-200 ease-out focus-within:border-primary/40 focus-within:bg-muted/35 focus-within:shadow-[0_0_0_3px_hsl(var(--primary)/0.08)] motion-reduce:transition-none">
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
                  if (!isBusy && !reconcilingUserMessage) {
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
                      className="h-9 w-9 rounded-full"
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
                      className="h-9 w-9 rounded-full"
                      disabled={!draft.trim() || reconcilingUserMessage}
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
          <Link
            to="/automation"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-1 font-medium transition-colors hover:bg-muted/50 hover:text-foreground"
            title={localize(
              lang,
              "Чат пока не загружает файлы напрямую. Откроется импорт Ansible-проекта.",
              "Chat does not upload files directly yet. This opens Ansible project import.",
            )}
          >
            <Paperclip className="h-3.5 w-3.5" />
            {localize(lang, "Файл / проект", "File / project")}
          </Link>
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
