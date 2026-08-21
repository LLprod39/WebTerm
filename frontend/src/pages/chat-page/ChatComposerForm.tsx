import { BookOpen, Bot, Paperclip, Send, Server, Square } from "lucide-react";
import { Link } from "react-router-dom";

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
    pinnedPlaybook,
    setPinnedPlaybook,
    playbookOptions,
  } = c;

  const openServerPicker = () => {
    const spacer = draft && !draft.endsWith(" ") ? " " : "";
    const next = `${draft}${spacer}@`;
    setDraft(next);
    setCaret(next.length);
    setPaletteOpen(true);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(next.length, next.length);
    });
  };

  return (
    <form
      className="shrink-0 border-t border-border/50 bg-card/95 px-3 pb-3 pt-2 sm:px-6 sm:pb-4"
      onSubmit={(event) => {
        event.preventDefault();
        submitMessage();
      }}
    >
      <div className="relative mx-auto max-w-[42rem]">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={openServerPicker}
            className="inline-flex h-8 max-w-full items-center gap-2 rounded-lg border border-border/60 bg-muted/20 px-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted/45 hover:text-foreground"
            aria-label={localize(lang, "Выбрать сервер для контекста", "Choose a server for context")}
          >
            <Server className="h-3.5 w-3.5 shrink-0 text-primary" />
            <span className="truncate">
              {pinnedServers.length
                ? localize(lang, `Контекст: ${pinnedServers.length} сервер(а)`, `Context: ${pinnedServers.length} server(s)`)
                : localize(lang, "Контекст: весь флот · выбрать сервер", "Context: all servers · choose server")}
            </span>
          </button>
          {playbookOptions.length ? (
            <Select
              value={pinnedPlaybook ? String(pinnedPlaybook.id) : "none"}
              onValueChange={(value) => {
                const selected = playbookOptions.find((item) => String(item.id) === value);
                setPinnedPlaybook(selected ? { id: selected.id, name: selected.name, kind: selected.kind } : null);
              }}
            >
              <SelectTrigger
                className="h-8 max-w-[18rem] border-border/60 bg-muted/20 text-xs"
                aria-label={localize(lang, "Выбрать playbook для контекста", "Choose playbook for context")}
              >
                <BookOpen className="mr-1.5 h-3.5 w-3.5 shrink-0 text-info" />
                <SelectValue placeholder={localize(lang, "Контекст playbook", "Playbook context")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{localize(lang, "Без playbook", "No playbook")}</SelectItem>
                {playbookOptions.map((item) => {
                  const duplicate = playbookOptions.filter((candidate) => candidate.name === item.name).length > 1;
                  return (
                    <SelectItem key={item.id} value={String(item.id)}>
                      {item.name}{duplicate ? ` · #${item.id}` : ""}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          ) : null}
          </div>
          {providerOptions.length ? (
            <div className="flex items-center gap-2">
              <span className="hidden text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60 sm:inline">
                {localize(lang, "Модель", "Model")}
              </span>
              <Select value={providerOverride || "inherit"} onValueChange={(value) => setProviderOverride(value === "inherit" ? "" : value)}>
                <SelectTrigger className="h-8 w-auto min-w-36 border-border/60 bg-muted/20 text-xs sm:min-w-44">
                  <SelectValue placeholder={localize(lang, "Провайдер чата", "Chat provider")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inherit">{localize(lang, "По умолчанию", "Default")}</SelectItem>
                  {providerOptions.map((option) => <SelectItem key={option.key} value={option.key}>{option.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          ) : null}
        </div>
        <PinnedContextChips
          servers={pinnedServers}
          users={pinnedUsers}
          onUnpinServer={unpinServer}
          onUnpinUser={unpinUser}
          playbook={pinnedPlaybook}
          onUnpinPlaybook={() => setPinnedPlaybook(null)}
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
        <div className="rounded-2xl border border-border/70 bg-muted/25 p-1.5 shadow-sm focus-within:border-primary/40 focus-within:bg-muted/35 focus-within:shadow-[0_0_0_3px_hsl(var(--primary)/0.08)]">
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
              "Enter — отправить · Shift+Enter — новая строка · работа продолжится в фоне",
              "Enter to send · Shift+Enter for a new line · work continues in background",
            )}
          </span>
        </div>
      </div>
    </form>
  );
}
