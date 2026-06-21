import { FileCode2, RefreshCw, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { formatRuCount } from "./sftpFormat";

export function SftpTextEditorSection({
  editorContent,
  editorEncoding,
  editorError,
  editorFilename,
  editorPath,
  editorSizeLabel,
  isEditorDirty,
  isEditorLoading,
  isEditorSaving,
  onClose,
  onContentChange,
  onReload,
  onSave,
}: {
  editorContent: string;
  editorEncoding: string;
  editorError: string;
  editorFilename: string;
  editorPath: string;
  editorSizeLabel: string;
  isEditorDirty: boolean;
  isEditorLoading: boolean;
  isEditorSaving: boolean;
  onClose: () => void;
  onContentChange: (content: string) => void;
  onReload: () => void;
  onSave: () => void;
}) {
  return (
    <section className="flex max-h-[45%] min-h-[14rem] flex-col border-t border-border bg-card">
      <div className="flex flex-col gap-2 border-b border-border px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <FileCode2 className="h-4 w-4 text-primary" />
            <div className="truncate text-sm font-semibold text-foreground">{editorFilename || editorPath}</div>
            {isEditorDirty ? <span className="rounded-md bg-primary/10 px-2 py-0.5 text-xs text-primary">Изменён</span> : null}
          </div>
          <div className="mt-1 truncate font-mono text-xs text-muted-foreground">{editorPath}</div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button type="button" size="sm" variant="outline" className="h-8 border-border bg-background px-3 text-xs" onClick={onReload} disabled={isEditorLoading || isEditorSaving}>
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", isEditorLoading && "animate-spin")} />
            Перезагрузить
          </Button>
          <Button type="button" size="sm" className="h-8 px-3 text-xs" onClick={onSave} disabled={!isEditorDirty || isEditorSaving}>
            <Save className="mr-1.5 h-3.5 w-3.5" />
            Сохранить
          </Button>
          <Button type="button" size="sm" variant="ghost" className="h-8 px-3 text-xs text-muted-foreground" onClick={onClose}>
            Закрыть
          </Button>
        </div>
      </div>
      {editorError ? <div className="border-b border-destructive/20 bg-destructive/10 px-4 py-2 text-xs text-destructive">{editorError}</div> : null}
      <Textarea
        value={editorContent}
        onChange={(event) => onContentChange(event.target.value)}
        spellCheck={false}
        className="min-h-0 flex-1 resize-none rounded-none border-0 bg-background/60 p-4 font-mono text-xs leading-5 shadow-none focus-visible:ring-0"
        disabled={isEditorLoading}
        aria-label="Содержимое файла"
      />
      <footer className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted-foreground">
        <span>{editorEncoding}</span>
        <span>{formatRuCount(editorContent.split("\n").length, "строка", "строки", "строк")} • {editorSizeLabel}</span>
      </footer>
    </section>
  );
}
