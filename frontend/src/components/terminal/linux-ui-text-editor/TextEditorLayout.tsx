import type { RefObject } from "react";
import {
  AlertTriangle,
  Copy,
  FileCode2,
  FolderOpen,
  Loader2,
  Plus,
  RotateCcw,
  Save,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { localize } from "@/lib/i18n";

import {
  getLanguageHint,
  TEXT_EDITOR_PRESET_PATHS,
  type EditorTab,
} from "./textEditorModel";

export function TextEditorHeader({
  activeTab,
  activeTabId,
  softWrap,
  lang,
  onOpen,
  onSave,
  onCopyPath,
  onToggleSoftWrap,
}: {
  activeTab: EditorTab | null;
  activeTabId: string | null;
  softWrap: boolean;
  lang: string;
  onOpen: () => void;
  onSave: () => void;
  onCopyPath: () => void;
  onToggleSoftWrap: () => void;
}) {
  return (
    <div className="border-b border-border bg-card px-3 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-foreground">{localize(lang, "Текстовый редактор", "Text Editor")}</div>
          <div className="mt-1 truncate text-xs text-muted-foreground">
            {activeTab?.path || localize(lang, "Откройте config, скрипт или заметку для inline-редактирования.", "Open a config, script, or note file to edit it inline.")}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-xl border-border bg-background px-3 text-xs text-foreground hover:bg-secondary"
            onClick={onOpen}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            {localize(lang, "Открыть", "Open")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-xl border-border bg-background px-3 text-xs text-foreground hover:bg-secondary"
            onClick={onSave}
            disabled={!activeTabId || !activeTab?.dirty}
          >
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {localize(lang, "Сохранить", "Save")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-xl border-border bg-background px-3 text-xs text-foreground hover:bg-secondary"
            onClick={onCopyPath}
            disabled={!activeTab?.path}
          >
            <Copy className="mr-1.5 h-3.5 w-3.5" />
            {localize(lang, "Копировать путь", "Copy Path")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant={softWrap ? "default" : "outline"}
            className="h-8 rounded-xl border-border px-3 text-xs"
            onClick={onToggleSoftWrap}
          >
            {localize(lang, "Перенос", "Wrap")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function TextEditorTabs({
  tabs,
  activeTabId,
  lang,
  onSelectTab,
  onCloseTab,
  onOpen,
}: {
  tabs: EditorTab[];
  activeTabId: string | null;
  lang: string;
  onSelectTab: (tabId: string) => void;
  onCloseTab: (tabId: string) => void;
  onOpen: () => void;
}) {
  return (
    <div className="flex items-center gap-0.5 border-b border-border bg-secondary/30 px-2">
      <ScrollArea className="flex-1">
        <div className="flex items-center gap-0.5 py-1">
          {tabs.map((tab) => (
            <div
              key={tab.id}
              className={cn(
                "group flex items-center gap-1.5 rounded-xl px-2 py-1 text-xs transition-colors",
                activeTabId === tab.id
                  ? "border border-border bg-background text-foreground"
                  : "text-muted-foreground hover:bg-background/80 hover:text-foreground",
              )}
            >
              <button
                type="button"
                onClick={() => onSelectTab(tab.id)}
                className="flex min-w-0 items-center gap-1.5 rounded-lg px-1 py-0.5 text-left"
              >
                <FileCode2 className="h-3 w-3 shrink-0" />
                <span className="max-w-32 truncate">{tab.filename}</span>
                {tab.dirty && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
              </button>
              <button
                type="button"
                onClick={() => onCloseTab(tab.id)}
                className="ml-0.5 flex h-4 w-4 items-center justify-center rounded opacity-0 transition-opacity group-hover:opacity-100 hover:bg-secondary focus:opacity-100"
                aria-label={localize(lang, `Закрыть ${tab.filename}`, `Close ${tab.filename}`)}
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </div>
          ))}
        </div>
      </ScrollArea>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="h-7 w-7 shrink-0 rounded-xl p-0 text-muted-foreground hover:bg-secondary hover:text-foreground"
        onClick={onOpen}
        aria-label={localize(lang, "Открыть файл", "Open file")}
      >
        <Plus className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

export function TextEditorOpenPanel({
  openPath,
  recentPaths,
  tabsCount,
  lang,
  onOpenPathChange,
  onOpenFile,
  onCancel,
}: {
  openPath: string;
  recentPaths: string[];
  tabsCount: number;
  lang: string;
  onOpenPathChange: (path: string) => void;
  onOpenFile: (path: string) => void;
  onCancel: () => void;
}) {
  const canOpen = Boolean(openPath.trim());
  return (
    <div className="border-b border-border bg-secondary/20 px-4 py-3">
      <div className="flex items-center gap-2">
        <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" />
        <Input
          value={openPath}
          onChange={(event) => onOpenPathChange(event.target.value)}
          placeholder={localize(lang, "/etc/nginx/nginx.conf или относительный путь (новые файлы допустимы)...", "/etc/nginx/nginx.conf or relative path (new files are allowed)...")}
          aria-label={localize(lang, "Путь файла для открытия или создания", "File path to open or create")}
          className="h-8 flex-1 rounded-xl border-border bg-background font-mono text-xs text-foreground placeholder:text-muted-foreground"
          onKeyDown={(event) => {
            if (event.key === "Enter" && canOpen) {
              event.preventDefault();
              onOpenFile(openPath.trim());
            }
          }}
          autoFocus
        />
        <Button
          type="button"
          size="sm"
          className="h-8 rounded-xl text-xs"
          disabled={!canOpen}
          onClick={() => onOpenFile(openPath.trim())}
        >
          {localize(lang, "Открыть / создать", "Open / Create")}
        </Button>
        {tabsCount > 0 && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 rounded-xl text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
            onClick={onCancel}
          >
            {localize(lang, "Отмена", "Cancel")}
          </Button>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {TEXT_EDITOR_PRESET_PATHS.map((path) => (
          <button
            key={path}
            type="button"
            onClick={() => onOpenFile(path)}
            className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:border-primary/20 hover:bg-secondary hover:text-foreground"
          >
            {path}
          </button>
        ))}
      </div>
      {recentPaths.length > 0 ? (
        <div className="mt-3">
          <div className="mb-1.5 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{localize(lang, "Недавние", "Recent")}</div>
          <div className="flex flex-wrap gap-1.5">
            {recentPaths.map((path) => (
              <button
                key={path}
                type="button"
                onClick={() => onOpenFile(path)}
                className="rounded-full border border-border bg-background px-2.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:border-primary/20 hover:bg-secondary hover:text-foreground"
              >
                {path}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function TextEditorWorkspace({
  activeTab,
  softWrap,
  textareaRef,
  lang,
  onContentChange,
  onTryAnotherFile,
}: {
  activeTab: EditorTab | null;
  softWrap: boolean;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  lang: string;
  onContentChange: (tabId: string, content: string) => void;
  onTryAnotherFile: (tab: EditorTab) => void;
}) {
  return (
    <div className="min-h-0 flex-1 overflow-hidden bg-transparent">
      {!activeTab ? (
        <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
          <div className="text-center">
            <FileCode2 className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
            <div>{localize(lang, "Откройте файл, чтобы начать редактирование", "Open a file to start editing")}</div>
            <div className="mt-1 text-xs">{localize(lang, "Используйте путь, шаблон или недавний файл из рабочего пространства.", "Use a path, a preset, or a recent file from this workspace.")}</div>
          </div>
        </div>
      ) : activeTab.loading ? (
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <span className="ml-2 text-sm text-muted-foreground">
            {localize(lang, `Загружаю ${activeTab.filename}...`, `Loading ${activeTab.filename}...`)}
          </span>
        </div>
      ) : activeTab.error ? (
        <div className="flex h-full items-center justify-center p-6">
          <div className="max-w-md rounded-[1.25rem] border border-destructive/25 bg-destructive/10 p-4 text-center">
            <AlertTriangle className="mx-auto h-5 w-5 text-destructive" />
            <div className="mt-2 text-sm text-destructive">{activeTab.error}</div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-3 h-8 rounded-xl border-border bg-background text-xs text-foreground hover:bg-secondary"
              onClick={() => onTryAnotherFile(activeTab)}
            >
              {localize(lang, "Попробовать другой файл", "Try another file")}
            </Button>
          </div>
        </div>
      ) : (
        <textarea
          ref={textareaRef}
          value={activeTab.content}
          onChange={(event) => onContentChange(activeTab.id, event.target.value)}
          spellCheck={false}
          className={cn(
            "h-full w-full resize-none border-0 bg-transparent p-5 font-mono text-[13px] leading-6 text-foreground outline-none selection:bg-primary/20",
            softWrap ? "whitespace-pre-wrap break-words" : "whitespace-pre overflow-auto",
          )}
          style={{ tabSize: 4 }}
        />
      )}
    </div>
  );
}

export function TextEditorFooter({
  activeTab,
  activeLineCount,
  activeCharCount,
  lang,
  onSave,
  onReload,
}: {
  activeTab: EditorTab | null;
  activeLineCount: number;
  activeCharCount: number;
  lang: string;
  onSave: (tabId: string) => void;
  onReload: (tabId: string) => void;
}) {
  return (
    <footer className="flex min-h-8 items-center justify-between border-t border-border bg-secondary/20 px-3 py-2 text-[11px] text-muted-foreground">
      <div className="flex items-center gap-3">
        {activeTab && (
          <>
            <span className="max-w-64 truncate font-mono">{activeTab.path}</span>
            <span>{getLanguageHint(activeTab.filename, lang)}</span>
            <span>{activeTab.encoding}</span>
            {activeTab.isNew && (
              <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">{localize(lang, "Новый файл", "New file")}</span>
            )}
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        {activeTab && (
          <>
            {activeTab.dirty && (
              <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">{localize(lang, "Изменён", "Modified")}</span>
            )}
            <span>{localize(lang, `${activeLineCount} строк`, `${activeLineCount} lines`)}</span>
            <span>{localize(lang, `${activeCharCount} символов`, `${activeCharCount} chars`)}</span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 gap-1 rounded-lg px-2 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
              onClick={() => onSave(activeTab.id)}
              disabled={!activeTab.dirty}
            >
              <Save className="h-3 w-3" />
              {localize(lang, "Сохранить", "Save")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 gap-1 rounded-lg px-2 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
              onClick={() => onReload(activeTab.id)}
              disabled={activeTab.isNew}
            >
              <RotateCcw className="h-3 w-3" />
              {localize(lang, "Перезагрузить", "Reload")}
            </Button>
          </>
        )}
      </div>
    </footer>
  );
}
