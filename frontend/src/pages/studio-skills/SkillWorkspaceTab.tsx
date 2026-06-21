import { FileCode2, FolderPlus, Loader2, Save, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type {
  StudioSkillWorkspace,
  StudioSkillWorkspaceFile,
  StudioSkillWorkspaceFileDetail,
} from "@/lib/api";

import { fileKindLabel, formatFileSize } from "./skillScaffold";

type TranslateFn = (ru: string, en: string) => string;

type SkillWorkspaceTabProps = {
  tr: TranslateFn;
  lang: "ru" | "en";
  workspace?: StudioSkillWorkspace;
  selectedFilePath: string;
  selectedWorkspaceFile: StudioSkillWorkspaceFile | null;
  selectedFileDetail?: StudioSkillWorkspaceFileDetail;
  editorValue: string;
  workspaceErrors: string[];
  workspaceWarnings: string[];
  isEditorDirty: boolean;
  isFetchingWorkspace: boolean;
  isFetchingFile: boolean;
  isSavingFile: boolean;
  isDeletingFile: boolean;
  canEditSkill: boolean;
  canEditSelectedFile: boolean;
  onCreateFile: () => void;
  onSaveFile: () => void;
  onRemoveFile: () => void;
  onSelectFile: (path: string) => void;
  onEditorValueChange: (value: string) => void;
};

export function SkillWorkspaceTab({
  tr,
  lang,
  workspace,
  selectedFilePath,
  selectedWorkspaceFile,
  selectedFileDetail,
  editorValue,
  workspaceErrors,
  workspaceWarnings,
  isEditorDirty,
  isFetchingWorkspace,
  isFetchingFile,
  isSavingFile,
  isDeletingFile,
  canEditSkill,
  canEditSelectedFile,
  onCreateFile,
  onSaveFile,
  onRemoveFile,
  onSelectFile,
  onEditorValueChange,
}: SkillWorkspaceTabProps) {
  return (
    <TabsContent value="workspace" className="m-0 flex flex-col gap-4 outline-none min-h-[650px] h-[calc(100vh-240px)]">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-4 shadow-sm shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
            <FileCode2 className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">{tr("Редактор файлов", "Workspace Editor")}</h3>
            <p className="text-xs text-muted-foreground">
              {tr("Правьте SKILL.md и текстовые файлы в references/, scripts/ и assets/.", "Edit SKILL.md and text files under references/, scripts/, and assets/.")}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" className="h-9 gap-1.5 rounded-md px-3 text-xs" onClick={onCreateFile} disabled={!canEditSkill}>
            <FolderPlus className="h-3.5 w-3.5" />
            {tr("Новый файл", "New File")}
          </Button>
          <Button size="sm" className="h-9 gap-1.5 rounded-md px-3 text-xs shadow-sm bg-primary hover:bg-primary/90 text-primary-foreground transition-all" onClick={onSaveFile} disabled={!selectedFilePath || !isEditorDirty || isSavingFile || !canEditSelectedFile}>
            {isSavingFile ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            {tr("Сохранить", "Save")}
          </Button>

          <div className="w-px h-5 bg-border/80 mx-1"></div>

          <Button variant="ghost" size="sm" className="h-9 gap-1.5 rounded-md px-3 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive transition-colors" onClick={onRemoveFile} disabled={!selectedFilePath || selectedFilePath === "SKILL.md" || isDeletingFile || !canEditSelectedFile}>
            {isDeletingFile ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            {tr("Удалить", "Delete")}
          </Button>
        </div>
      </div>

      {(workspaceErrors.length > 0 || workspaceWarnings.length > 0) && (
        <div className="border-b border-border/40 p-4 bg-muted/5 flex flex-col gap-3">
          {workspaceErrors.length > 0 && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
              <p className="text-xs font-medium text-red-200">{tr("Ошибки пакета", "Package errors")}</p>
              <div className="mt-2 space-y-1">
                {workspaceErrors.map((item) => (
                  <p key={item} className="text-xs text-red-100">• {item}</p>
                ))}
              </div>
            </div>
          )}
          {workspaceWarnings.length > 0 && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
              <p className="text-xs font-medium text-amber-100">{tr("Предупреждения пакета", "Package warnings")}</p>
              <div className="mt-2 space-y-1">
                {workspaceWarnings.map((item) => (
                  <p key={item} className="text-xs text-amber-50">• {item}</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden gap-4" style={{ minHeight: "600px" }}>
        <div className="w-[300px] lg:w-[340px] shrink-0 flex flex-col gap-2 rounded-xl border border-border/40 bg-muted/10 p-4 overflow-y-auto">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-foreground">{tr("Файлы пакета", "Package Files")}</p>
              <p className="text-xs text-muted-foreground">{tr("SKILL.md, references/, scripts/, assets/", "SKILL.md, references/, scripts/, assets/")}</p>
            </div>
            {isFetchingWorkspace ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : null}
          </div>
          {!workspace?.files.length ? (
            <div className="rounded-xl border border-dashed border-border/70 px-3 py-6 text-center text-xs text-muted-foreground">
              {tr("Файлы ещё не найдены.", "No files found yet.")}
            </div>
          ) : (
            <div className="space-y-2">
              {workspace.files.map((file) => (
                <button
                  key={file.path}
                  type="button"
                  onClick={() => onSelectFile(file.path)}
                  className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                    selectedFilePath === file.path ? "border-primary/50 bg-primary/10 ring-1 ring-primary/20" : "border-border/70 bg-background/40 hover:bg-background/60"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-foreground">{file.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{formatFileSize(file.size)}</span>
                  </div>
                  <div className="mt-1 truncate font-mono text-xs text-muted-foreground">{file.path}</div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge variant="outline" className="text-xs">{fileKindLabel(file.kind, lang)}</Badge>
                    <Badge variant="secondary" className="text-xs">{file.language}</Badge>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex-1 flex flex-col rounded-xl border border-border/40 bg-muted/5 overflow-hidden">
          {!selectedWorkspaceFile ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/30">
                <FileCode2 className="h-5 w-5 text-muted-foreground/70" />
              </div>
              <p className="text-sm font-medium text-foreground">{tr("Выберите файл слева", "Select a file on the left")}</p>
              <p className="text-xs text-muted-foreground max-w-sm">{tr("Откройте SKILL.md, references/, scripts/ или assets/, чтобы править плейбук прямо здесь.", "Open SKILL.md or any file under references/, scripts/, assets/ to edit the playbook here.")}</p>
            </div>
          ) : isFetchingFile && !selectedFileDetail ? (
            <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {tr("Загрузка файла...", "Loading file...")}
            </div>
          ) : (
            <div className="flex flex-col h-full">
              <div className="border-b border-border/40 px-5 py-4 bg-background/50 shrink-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <FileCode2 className="h-4 w-4 text-primary/70" />
                      <div className="text-sm font-semibold text-foreground">{selectedWorkspaceFile.name}</div>
                      {isEditorDirty && <Badge variant="outline" className="text-xs border-amber-500/50 text-amber-600 dark:text-amber-400">{tr("не сохранено", "unsaved")}</Badge>}
                    </div>
                    <div className="mt-1 break-all font-mono text-xs text-muted-foreground">{selectedWorkspaceFile.path}</div>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="outline" className="text-xs">{fileKindLabel(selectedWorkspaceFile.kind, lang)}</Badge>
                    <Badge variant="secondary" className="text-xs">{selectedWorkspaceFile.language}</Badge>
                    <Badge variant="outline" className="text-xs">{formatFileSize(selectedWorkspaceFile.size)}</Badge>
                  </div>
                </div>
              </div>

              <div className="p-4 flex-1 flex flex-col min-h-0 bg-background/20">
                <Textarea
                  value={editorValue}
                  onChange={(event) => onEditorValueChange(event.target.value)}
                  className="flex-1 font-mono text-[13px] leading-6 resize-none shadow-inner border-border/50 bg-background/60 focus-visible:ring-1 focus-visible:ring-primary/30"
                  style={{ tabSize: 2 }}
                  spellCheck={false}
                  readOnly={!canEditSelectedFile}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </TabsContent>
  );
}
