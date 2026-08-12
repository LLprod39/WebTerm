import { Send, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { localize } from "@/lib/i18n";

import { ComposeCommandPalette } from "./ComposeCommandPalette";
import { PinnedContextChips } from "./PinnedContextChips";
import type { ChatPageController } from "./useChatPageController";

type ChatComposerFormProps = {
  c: ChatPageController;
};

export function ChatComposerForm({ c }: ChatComposerFormProps) {
  const {
    lang,
    draft,
    setDraft,
    caret,
    setCaret,
    paletteOpen,
    setPaletteOpen,
    pinnedServers,
    pinnedUsers,
    unpinServer,
    unpinUser,
    pinServer,
    paletteRef,
    textareaRef,
    isBusy,
    handleStop,
    submitMessage,
    providerOptions,
    providerOverride,
    setProviderOverride,
  } = c;

  return (
    <form
      className="shrink-0 border-t border-border/50 bg-card px-3 pb-4 pt-2 sm:px-6 sm:pb-5"
      onSubmit={(event) => {
        event.preventDefault();
        submitMessage();
      }}
    >
      <div className="relative mx-auto max-w-[42rem]">
        <PinnedContextChips
          servers={pinnedServers}
          users={pinnedUsers}
          onUnpinServer={unpinServer}
          onUnpinUser={unpinUser}
        />
        {providerOptions.length ? (
          <div className="mb-2 flex justify-end">
            <Select value={providerOverride || "inherit"} onValueChange={(value) => setProviderOverride(value === "inherit" ? "" : value)}>
              <SelectTrigger className="h-8 w-auto min-w-44 border-border/60 bg-muted/20 text-xs">
                <SelectValue placeholder={localize(lang, "Провайдер чата", "Chat provider")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="inherit">{localize(lang, "По умолчанию", "Default")}</SelectItem>
                {providerOptions.map((option) => <SelectItem key={option.key} value={option.key}>{option.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        ) : null}
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
        <div className="rounded-3xl border border-border/70 bg-muted/25 p-1.5 shadow-sm focus-within:border-border focus-within:bg-muted/35">
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
                  if (!isBusy) event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={
                isBusy
                  ? localize(lang, "Оператор работает… Esc — остановить", "Operator is working… Esc to stop")
                  : localize(lang, "Спросите что угодно…", "Ask anything…")
              }
              className="max-h-40 min-h-12 flex-1 resize-none border-0 bg-transparent px-3.5 py-2.5 text-[15px] leading-6 shadow-none focus-visible:ring-0"
              rows={1}
            />
            {isBusy ? (
              <Button
                type="button"
                size="icon"
                variant="secondary"
                className="mb-1 mr-1 h-9 w-9 shrink-0 rounded-full"
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
                className="mb-1 mr-1 h-9 w-9 shrink-0 rounded-full"
                disabled={!draft.trim()}
                aria-label={localize(lang, "Отправить", "Send")}
                title={localize(lang, "Отправить · Enter", "Send · Enter")}
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
        <p className="mt-2 px-1 text-center text-[11px] text-muted-foreground/60">
          {localize(
            lang,
            "Диалог продолжается в фоне, если уйти со страницы",
            "Conversation keeps running if you leave the page",
          )}
        </p>
      </div>
    </form>
  );
}
