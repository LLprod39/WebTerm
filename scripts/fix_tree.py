import sys

file_path = 'c:/WebTrerm/ai-server-terminal-main/src/pages/StudioSkillsPage.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = lines[:933] + [
'                    <div className="flex flex-1 overflow-hidden" style={{ minHeight: "600px" }}>\n',
'                      <div className="w-1/4 min-w-[240px] border-r border-border/40 bg-muted/10 p-2 overflow-y-auto">\n',
'                        <FileTree\n',
'                          manifest={selectedSkill?.parsed_manifest}\n',
'                          selectedPath={selectedFilePath}\n',
'                          onSelect={setSelectedFilePath}\n',
'                        />\n',
'                      </div>\n',
'                      <div className="flex-1 flex flex-col">\n',
'                        <SkillEditor\n',
'                          selectedSkill={selectedSkill!}\n',
'                          selectedFilePath={selectedFilePath}\n',
'                          fileContent={fileContent}\n',
'                          setFileContent={setFileContent}\n',
'                          canEdit={canEditSelectedFile}\n',
'                        />\n',
'                      </div>\n',
'                    </div>\n',
'                  </TabsContent>\n',
'                </Tabs>\n'
] + lines[935:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
