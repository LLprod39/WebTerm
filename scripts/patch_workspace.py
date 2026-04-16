import sys
import re

file_path = 'c:/WebTrerm/ai-server-terminal-main/src/pages/StudioSkillsPage.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# We want to replace everything from `<div className="flex flex-1 overflow-hidden" style={{ minHeight: "600px" }}>`
# up to `                  </TabsContent>`

replacement = """                    <div className="flex flex-1 overflow-hidden gap-4" style={{ minHeight: "600px" }}>
                      <div className="w-1/4 min-w-[240px] flex flex-col gap-2 rounded-xl border border-border/40 bg-muted/10 p-3 overflow-y-auto">
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <div>
                            <p className="text-xs font-medium text-foreground">{tr("Файлы пакета", "Package Files")}</p>
                            <p className="text-[10px] text-muted-foreground">{tr("SKILL.md, references/, scripts/, assets/", "SKILL.md, references/, scripts/, assets/")}</p>
                          </div>
                          {isFetchingWorkspace ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : null}
                        </div>
                        {!workspace?.files.length ? (
                          <div className="rounded-xl border border-dashed border-border/70 px-3 py-6 text-center text-[11px] text-muted-foreground">
                            {tr("Файлы ещё не найдены.", "No files found yet.")}
                          </div>
                        ) : (
                          <div className="space-y-2">
                            {workspace.files.map((file) => (
                              <button
                                key={file.path}
                                type="button"
                                onClick={() => setSelectedFilePath(file.path)}
                                className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                                  selectedFilePath === file.path ? "border-primary/40 bg-primary/5" : "border-border/70 bg-background/24 hover:bg-background/40"
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="truncate text-[11px] font-medium text-foreground">{file.name}</span>
                                  <span className="text-[10px] text-muted-foreground">{formatFileSize(file.size)}</span>
                                </div>
                                <div className="mt-1 truncate font-mono text-[10px] text-muted-foreground">{file.path}</div>
                                <div className="mt-2 flex flex-wrap gap-1">
                                  <Badge variant="outline" className="text-[9px]">{fileKindLabel(file.kind, lang)}</Badge>
                                  <Badge variant="secondary" className="text-[9px]">{file.language}</Badge>
                                </div>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="flex-1 flex flex-col rounded-xl border border-border/40 bg-muted/5">
                        {!selectedWorkspaceFile ? (
                          <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted-foreground">
                            {tr("Выберите файл слева, чтобы открыть редактор.", "Select a file on the left to open the editor.")}
                          </div>
                        ) : isFetchingFile && !selectedFileDetail ? (
                          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            {tr("Загрузка файла...", "Loading file...")}
                          </div>
                        ) : (
                          <div className="flex flex-col h-full">
                            <div className="border-b border-border/40 px-4 py-4 bg-background/50 shrink-0">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <div className="text-sm font-medium text-foreground">{selectedWorkspaceFile.name}</div>
                                  <div className="mt-1 break-all font-mono text-[10px] text-muted-foreground">{selectedWorkspaceFile.path}</div>
                                </div>
                                <div className="flex flex-wrap gap-1">
                                  <Badge variant="outline" className="text-[9px]">{fileKindLabel(selectedWorkspaceFile.kind, lang)}</Badge>
                                  <Badge variant="secondary" className="text-[9px]">{selectedWorkspaceFile.language}</Badge>
                                  <Badge variant="outline" className="text-[9px]">{formatFileSize(selectedWorkspaceFile.size)}</Badge>
                                </div>
                              </div>
                            </div>
                            
                            <div className="p-4 flex-1 flex flex-col min-h-0 bg-background/20">
                              <Textarea 
                                value={editorValue} 
                                onChange={(event) => setEditorValue(event.target.value)} 
                                className="flex-1 font-mono text-[12px] leading-relaxed resize-none shadow-inner border-border/50" 
                                readOnly={!canEditSelectedFile} 
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    </div>"""

# Find the start and end indices securely
start_idx = content.find('<div className="flex flex-1 overflow-hidden" style={{ minHeight: "600px" }}>')
end_idx = content.find('</TabsContent>', start_idx)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + replacement + '\n                  ' + content[end_idx:]
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Success")
else:
    print("Could not find boundaries")
