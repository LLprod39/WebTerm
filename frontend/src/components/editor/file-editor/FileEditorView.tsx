import {
  AlertTriangle,
  Copy,
  FileCode2,
  FolderOpen,
  Loader2,
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  RefreshCw,
  Save,
  Shield,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { CodeEditor } from "../CodeEditor";
import { getLanguageLabel } from "../codeEditorLanguage";

import { FileEditorSudoDialog, FileEditorUnsavedDialog } from "./FileEditorDialogs";
import type { FileEditorController } from "./useFileEditorController";

export function FileEditorView(ctrl: FileEditorController) {
  const {
    t,
    tabs,
    activeTabId,
    setActiveTabId,
    openPath,
    setOpenPath,
    showOpen,
    setShowOpen,
    mode,
    setMode,
    rect,
    windowRef,
    activeTab,
    lineCount,
    charCount,
    tabCountLabel,
    onDragStart,
    onResizeStart,
    openFile,
    saveFile,
    reloadFile,
    closeTab,
    updateContent,
    copyPath,
    handleClose,
    handleKeyDown,
    toggleMaximize,
  } = ctrl;

  const sudoDialog = <FileEditorSudoDialog {...ctrl} />;
  const unsavedCloseDialog = <FileEditorUnsavedDialog {...ctrl} />;

  /* ---- minimized bar ---- */
  if (mode === "minimized") {
    return (
      <>
        <div className="fixed bottom-4 left-4 z-[60] flex h-10 items-center gap-2 rounded-lg border border-white/10 bg-[#161b22] px-3 shadow-xl cursor-pointer select-none">
          <button
            type="button"
            className="flex min-w-0 items-center gap-2 text-left"
            onClick={() => setMode("normal")}
            aria-label={t("editor.restoreWindow")}
            title={t("editor.restoreWindow")}
          >
            <FileCode2 className="h-4 w-4 text-blue-400" />
            <span className="text-xs font-medium text-zinc-300">{t("editor.title")}</span>
            {tabs.some((tb) => tb.dirty) && <span className="h-2 w-2 rounded-full bg-blue-500" />}
            <span className="text-xs text-zinc-500">{tabCountLabel}</span>
          </button>
          <button
            type="button"
            onClick={handleClose}
            className="ml-1 rounded p-0.5 text-zinc-500 hover:text-zinc-200 hover:bg-white/10"
            aria-label={t("editor.closeWindow")}
            title={t("editor.closeWindow")}
          >
            <X className="h-3 w-3" />
          </button>
        </div>
        {unsavedCloseDialog}
        {sudoDialog}
      </>
    );
  }

  const isMax = mode === "maximized";
  const style: React.CSSProperties = isMax
    ? { position: "fixed", inset: 0, width: "100%", height: "100%" }
    : { position: "fixed", left: rect.x, top: rect.y, width: rect.w, height: rect.h };

  return (
    <>
      <div
        ref={windowRef}
        role="dialog"
        aria-modal="true"
        aria-label={t("editor.title")}
        className={cn(
          "z-[60] flex flex-col bg-[#0d1117] shadow-2xl border border-white/10",
          isMax ? "rounded-none" : "rounded-lg",
        )}
        style={style}
        onKeyDown={handleKeyDown}
      >
        {/* ---- title bar (draggable) ---- */}
        <div
          className={cn(
            "flex items-center gap-2 border-b border-white/10 bg-[#161b22] px-3 py-1.5 select-none",
            isMax ? "" : "cursor-move rounded-t-lg",
          )}
          onMouseDown={onDragStart}
          onDoubleClick={toggleMaximize}
        >
          <FileCode2 className="h-3.5 w-3.5 text-blue-400 shrink-0" />
          <span className="text-xs font-semibold text-zinc-200 truncate">{t("editor.title")}</span>
          {activeTab && (
            <span className="text-xs text-zinc-500 truncate hidden sm:inline">— {activeTab.path}</span>
          )}
          {activeTab?.elevated && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">
              <Shield className="h-3 w-3" />
              {t("editor.elevatedBadge")}
            </span>
          )}

          <div className="ml-auto flex items-center gap-0.5 shrink-0" data-no-drag>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={() => setShowOpen(true)}
              title={t("editor.open")}
              aria-label={t("editor.open")}
            >
              <FolderOpen className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={() => activeTabId && void saveFile(activeTabId)}
              disabled={!activeTab?.dirty}
              title={t("editor.save")}
              aria-label={t("editor.save")}
            >
              <Save className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={() => activeTabId && void reloadFile(activeTabId)}
              disabled={!activeTab || activeTab.isNew}
              title={t("editor.reload")}
              aria-label={t("editor.reload")}
            >
              <RefreshCw className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={copyPath}
              disabled={!activeTab}
              title={t("editor.copyPath")}
              aria-label={t("editor.copyPath")}
            >
              <Copy className="h-3 w-3" />
            </Button>
            <div className="mx-1 h-4 w-px bg-white/10" />
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-yellow-400"
              onClick={() => setMode("minimized")}
              title={t("editor.minimize")}
              aria-label={t("editor.minimize")}
            >
              <Minus className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={toggleMaximize}
              title={isMax ? t("editor.restoreWindow") : t("editor.maximize")}
              aria-label={isMax ? t("editor.restoreWindow") : t("editor.maximize")}
            >
              {isMax ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-red-400"
              onClick={handleClose}
              title={t("editor.closeWindow")}
              aria-label={t("editor.closeWindow")}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* ---- tab bar ---- */}
        <div className="flex items-center gap-0.5 border-b border-white/5 bg-[#0d1117] px-2 py-0.5 overflow-x-auto">
          {tabs.map((tab) => (
            <div
              key={tab.id}
              className={cn(
                "group flex items-center gap-1.5 rounded px-2 py-0.5 text-xs transition-colors shrink-0",
                activeTabId === tab.id
                  ? "bg-[#161b22] text-zinc-200"
                  : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300",
              )}
            >
              <button
                type="button"
                onClick={() => {
                  setActiveTabId(tab.id);
                  setShowOpen(false);
                }}
                className="flex min-w-0 items-center gap-1.5 text-left"
                aria-label={
                  tab.dirty
                    ? `${t("editor.openTab")} ${tab.filename}, ${t("editor.modified")}`
                    : `${t("editor.openTab")} ${tab.filename}`
                }
                title={tab.path}
              >
                <FileCode2 className="h-3 w-3 shrink-0" />
                <span className="max-w-28 truncate">{tab.filename}</span>
                {tab.elevated && <Shield className="h-3 w-3 text-amber-400 shrink-0" />}
                {tab.dirty && <span className="h-1.5 w-1.5 rounded-full bg-blue-500 shrink-0" />}
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  closeTab(tab.id);
                }}
                className="ml-0.5 flex h-3.5 w-3.5 items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-white/10"
                aria-label={`${t("editor.closeTab")} ${tab.filename}`}
                title={t("editor.closeTab")}
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setShowOpen(true)}
            className="ml-1 flex h-5 w-5 items-center justify-center rounded text-zinc-500 hover:bg-white/5 hover:text-zinc-300 shrink-0"
            aria-label={t("editor.open")}
            title={t("editor.open")}
          >
            <Plus className="h-3 w-3" />
          </button>
        </div>

        {/* ---- open dialog ---- */}
        {showOpen && (
          <div className="border-b border-white/5 bg-[#161b22] px-3 py-2">
            <div className="flex items-center gap-2">
              <FolderOpen className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
              <Input
                value={openPath}
                onChange={(e) => setOpenPath(e.target.value)}
                placeholder={t("editor.pathPlaceholder")}
                aria-label={t("editor.pathInput")}
                className="h-7 flex-1 border-zinc-700 bg-[#0d1117] font-mono text-xs text-zinc-200 placeholder:text-zinc-600"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && openPath.trim()) {
                    e.preventDefault();
                    void openFile(openPath.trim());
                  }
                }}
                autoFocus
              />
              <Button
                size="sm"
                className="h-7 text-xs"
                disabled={!openPath.trim()}
                onClick={() => void openFile(openPath.trim())}
              >
                {t("editor.openBtn")}
              </Button>
              {tabs.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs text-zinc-500"
                  onClick={() => setShowOpen(false)}
                >
                  {t("editor.cancel")}
                </Button>
              )}
            </div>
          </div>
        )}

        {/* ---- editor area ---- */}
        <div className="min-h-0 flex-1 overflow-hidden">
          {!activeTab ? (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <FileCode2 className="mx-auto mb-2 h-8 w-8 text-zinc-700" />
                <div className="text-xs text-zinc-500">{t("editor.emptyHint")}</div>
              </div>
            </div>
          ) : activeTab.loading ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
              <span className="ml-2 text-xs text-zinc-500">
                {t("editor.loading")} {activeTab.filename}…
              </span>
            </div>
          ) : activeTab.error ? (
            <div className="flex h-full items-center justify-center p-4">
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-center">
                <AlertTriangle className="mx-auto h-5 w-5 text-red-400" />
                <div className="mt-1 text-xs text-red-300">{activeTab.error}</div>
                <div className="mt-2 flex items-center justify-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs"
                    onClick={() => void openFile(activeTab.path, { preferElevated: true })}
                  >
                    <Shield className="mr-1 h-3 w-3" />
                    {t("editor.sudoRetryStored")}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs"
                    onClick={() => {
                      closeTab(activeTab.id);
                      setShowOpen(true);
                    }}
                  >
                    {t("editor.tryAnother")}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <CodeEditor
              content={activeTab.content}
              filename={activeTab.filename}
              onChange={(value) => updateContent(activeTab.id, value)}
              onSave={() => void saveFile(activeTab.id)}
            />
          )}
        </div>

        {/* ---- status bar ---- */}
        <div
          className={cn(
            "flex h-6 items-center justify-between border-t border-white/5 bg-[#161b22] px-3 text-xs text-zinc-500",
            !isMax && "rounded-b-lg",
          )}
        >
          <div className="flex items-center gap-2">
            {activeTab && (
              <>
                <span className="max-w-48 truncate font-mono">{activeTab.path}</span>
                <span>{getLanguageLabel(activeTab.filename)}</span>
                <span>{activeTab.encoding}</span>
                {activeTab.isNew && (
                  <span className="rounded bg-zinc-800 px-1 py-0.5 text-xs">{t("editor.newFile")}</span>
                )}
                {activeTab.elevated && (
                  <span className="rounded bg-amber-500/10 px-1 py-0.5 text-xs text-amber-300">
                    {t("editor.elevatedBadge")}
                  </span>
                )}
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            {activeTab?.dirty && (
              <span className="rounded bg-blue-500/10 px-1 py-0.5 text-xs text-blue-400">
                {t("editor.modified")}
              </span>
            )}
            {activeTab && (
              <>
                <span>
                  {lineCount} {t("editor.lines")}
                </span>
                <span>
                  {charCount} {t("editor.chars")}
                </span>
              </>
            )}
          </div>
        </div>

        {/* ---- resize handle ---- */}
        {!isMax && (
          <div
            className="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize"
            onMouseDown={onResizeStart}
            style={{
              background: "linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.15) 50%)",
              borderRadius: "0 0 0.5rem 0",
            }}
          />
        )}
      </div>
      {unsavedCloseDialog}
      {sudoDialog}
    </>
  );
}
