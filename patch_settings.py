import sys
import re

file_path = 'c:/WebTrerm/ai-server-terminal-main/src/pages/StudioSkillsPage.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

settings_content = """                  <TabsContent value="settings" className="m-0 space-y-4 outline-none">
                    <div className="rounded-xl border border-border/50 bg-background/40 backdrop-blur-md p-6 shadow-sm">
                      <div className="mb-6 flex items-center gap-3 border-b border-border/50 pb-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20 shadow-inner">
                          <Settings2 className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <h3 className="text-base font-semibold text-foreground">{tr("Настройки доступа", "Access Settings")}</h3>
                          <p className="text-[12px] text-muted-foreground">{tr("Текущее управление доступом пока не реализовано в Studio, перейдите в Access Management.", "Access control is managed in Access Management.")}</p>
                        </div>
                      </div>
                      <div className="text-[13px] text-muted-foreground">
                        {tr("В будущем здесь можно будет детально управлять настройками скилла, владельцем и привязками.", "In the future, detailed skill settings, ownership, and bindings will be manageable here.")}
                      </div>
                    </div>
                  </TabsContent>
"""

# Replace the end to include settings
content = re.sub(
    r'(\s+)</div>\s+</div>\s+</TabsContent>\s+</Tabs>',
    r'\1</div>\n\1</div>\n\1</TabsContent>\n\n' + settings_content + r'                </Tabs>',
    content
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
