import sys

file_path = 'c:/WebTrerm/ai-server-terminal-main/src/pages/StudioSkillsPage.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = lines[:902] + [
'                          {deleteFileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}\n',
'                          {tr("Удалить", "Delete")}\n',
'                        </Button>\n',
'                      </div>\n',
'                    </div>\n',
'                    \n',
'                    {(workspaceErrors.length > 0 || workspaceWarnings.length > 0) && (\n',
'                      <div className="border-b border-border/40 p-4 bg-muted/5 flex flex-col gap-3">\n',
'                        {workspaceErrors.length > 0 && (\n',
'                          <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4">\n',
'                            <p className="text-xs font-medium text-red-200">{tr("Ошибки пакета", "Package errors")}</p>\n',
'                            <div className="mt-2 space-y-1">\n',
'                              {workspaceErrors.map((item) => (\n',
'                                <p key={item} className="text-[11px] text-red-100">• {item}</p>\n',
'                              ))}\n',
'                            </div>\n',
'                          </div>\n',
'                        )}\n',
'                        {workspaceWarnings.length > 0 && (\n',
'                          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">\n',
'                            <p className="text-xs font-medium text-amber-100">{tr("Предупреждения пакета", "Package warnings")}</p>\n',
'                            <div className="mt-2 space-y-1">\n',
'                              {workspaceWarnings.map((item) => (\n',
'                                <p key={item} className="text-[11px] text-amber-50">• {item}</p>\n',
'                              ))}\n',
'                            </div>\n',
'                          </div>\n',
'                        )}\n',
'                      </div>\n',
'                    )}\n'
] + lines[924:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
