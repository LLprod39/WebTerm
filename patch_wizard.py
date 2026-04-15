import sys

file_path = 'c:/WebTrerm/ai-server-terminal-main/src/pages/StudioSkillsPage.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '<Dialog open={createOpen} onOpenChange={setCreateOpen}>'
end_marker = '      <Dialog open={createFileOpen} onOpenChange={setCreateFileOpen}>'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)

replacement = """      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-auto p-0 rounded-xl border-border bg-background shadow-2xl">
          <div className="bg-muted/30 px-6 py-5 border-b border-border/40">
            <DialogHeader>
              <DialogTitle className="text-xl font-semibold flex items-center gap-2">
                <WandSparkles className="h-5 w-5 text-primary" />
                {tr("Создание скилла", "Create Skill")}
              </DialogTitle>
              <DialogDescription className="text-[13px] mt-1.5">
                {tr("Скилл — это рабочий плейбук агента. Заполните основные поля, а сложную конфигурацию мы спрятали в продвинутых настройках.", "A skill is an operational playbook. Fill out the basics, and we'll leave the complex configuration in advanced settings.")}
              </DialogDescription>
            </DialogHeader>
          </div>

          <div className="px-6 py-6 space-y-8">
            {/* 1. Base Info */}
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">1</div>
                <h3 className="text-sm font-medium">{tr("Основная информация", "Basic Information")}</h3>
              </div>
              
              <div className="space-y-4 pl-8">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Если есть готовый концепт, выберите шаблон", "If you have a concept, pick a template")}</Label>
                  <Select
                    value={selectedTemplateSlug}
                    onValueChange={(value) => {
                      setSelectedTemplateSlug(value);
                      const template = templates.find((item) => item.slug === value) || null;
                      setWizard(createWizardState(template));
                      setSlugTouched(false);
                    }}
                  >
                    <SelectTrigger className="h-10">
                      <SelectValue placeholder={tr("Начать с чистого листа", "Start from a blank slate")} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">{tr("С чистого листа (пустой скилл)", "Blank slate")}</SelectItem>
                      {templates.map((template) => (
                        <SelectItem key={template.slug} value={template.slug}>{template.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Название (Что делает?)", "Name (What it does)")}</Label>
                    <Input
                      className="h-10"
                      value={wizard.name}
                      onChange={(e) => {
                        const value = e.target.value;
                        setWizard((prev) => ({ ...prev, name: value, slug: slugTouched ? prev.slug : slugifySkillName(value) }));
                      }}
                      placeholder={tr("Управление токенами", "Token Management")}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Сервис (Где делает?)", "Service (Where)")}</Label>
                    <Input className="h-10" value={wizard.service} onChange={(e) => setWizard((prev) => ({ ...prev, service: e.target.value }))} placeholder={tr("github, keycloak...", "github, keycloak...")} />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Описание для агентов", "Description for agents")}</Label>
                  <Textarea rows={2} className="resize-none" value={wizard.description} onChange={(e) => setWizard((prev) => ({ ...prev, description: e.target.value }))} placeholder={tr("Когда и зачем агент должен применять этот плейбук.", "When and why the agent should apply this playbook.")} />
                </div>
              </div>
            </div>

            {/* 2. Architecture */}
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">2</div>
                <h3 className="text-sm font-medium">{tr("Структура и безопасность", "Structure & Security")}</h3>
              </div>

              <div className="pl-8 grid gap-6 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{tr("Уровень безопасности", "Safety Level")}</Label>
                  <Select value={wizard.safety_level} onValueChange={(value) => setWizard((prev) => ({ ...prev, safety_level: value }))}>
                    <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SAFETY_LEVELS.map((level) => (<SelectItem key={level} value={level}>{level}</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-3 pt-1">
                  <div className="flex items-center justify-between gap-2">
                    <Label className="cursor-pointer text-xs font-normal" htmlFor="tog-ref">{tr("Добавить папку references/", "Include references/ folder")}</Label>
                    <Switch id="tog-ref" checked={wizard.with_references} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_references: Boolean(checked) }))} />
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <Label className="cursor-pointer text-xs font-normal" htmlFor="tog-scr">{tr("Добавить папку scripts/", "Include scripts/ folder")}</Label>
                    <Switch id="tog-scr" checked={wizard.with_scripts} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_scripts: Boolean(checked) }))} />
                  </div>
                </div>
              </div>
            </div>

            {/* 3. Advanced Tools */}
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="advanced" className="border-border/40">
                <AccordionTrigger className="text-sm px-2 hover:bg-muted/30 rounded-md transition-colors">{tr("Продвинутые настройки (Опционально)", "Advanced Settings (Optional)")}</AccordionTrigger>
                <AccordionContent className="pt-4 px-2 space-y-5">
                  
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Slug (Уникальный ID)", "Slug (Unique ID)")}</Label>
                      <Input className="h-9 font-mono text-xs" value={wizard.slug} onChange={(e) => { setSlugTouched(true); setWizard((prev) => ({ ...prev, slug: e.target.value })); }} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Категория", "Category")}</Label>
                      <Input className="h-9 text-xs" value={wizard.category} onChange={(e) => setWizard((prev) => ({ ...prev, category: e.target.value }))} placeholder="IAM, DevOps..." />
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("UI-подсказка", "UI Hint")}</Label>
                      <Input className="h-9 text-xs" value={wizard.ui_hint} onChange={(e) => setWizard((prev) => ({ ...prev, ui_hint: e.target.value }))} placeholder={tr("Инструкция для списка", "Hint for list view")} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Теги (CSV)", "Tags (CSV)")}</Label>
                      <Input className="h-9 text-xs" value={wizard.tags_text} onChange={(e) => setWizard((prev) => ({ ...prev, tags_text: e.target.value }))} placeholder="tag1, tag2" />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Рекомендуемые MCP инструменты (CSV)", "Recommended MCP tools (CSV)")}</Label>
                    <Input className="h-9 text-xs" value={wizard.recommended_tools_text} onChange={(e) => setWizard((prev) => ({ ...prev, recommended_tools_text: e.target.value }))} placeholder="github_search, ask_user" />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Guardrail Правила", "Guardrail Rules")}</Label>
                    <Textarea rows={2} className="text-xs" value={wizard.guardrail_summary_text} onChange={(e) => setWizard((prev) => ({ ...prev, guardrail_summary_text: e.target.value }))} placeholder={tr("Описание жестких ограничений.", "Description of hard constraints.")} />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Runtime Policy (Конфиг среды)", "Runtime Policy (Env config)")}</Label>
                    <Textarea rows={6} value={wizard.runtime_policy_text} onChange={(e) => setWizard((prev) => ({ ...prev, runtime_policy_text: e.target.value }))} className="font-mono text-[11px] bg-muted/20" />
                  </div>

                  <div className="flex items-center space-x-2 pt-2">
                    <Switch id="force-overwrite" checked={wizard.force} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, force: Boolean(checked) }))} />
                    <Label htmlFor="force-overwrite" className="text-xs text-destructive">{tr("Перезаписать скилл с таким же slug", "Overwrite skill with same slug")}</Label>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>

          <div className="bg-muted/20 px-6 py-4 flex items-center justify-between border-t border-border/40">
            <Button variant="ghost" className="text-muted-foreground" onClick={() => setCreateOpen(false)}>{tr("Отмена", "Cancel")}</Button>
            <Button onClick={submitWizard} disabled={!wizard.name.trim() || !wizard.description.trim() || scaffoldMutation.isPending} className="gap-2 px-6">
              {scaffoldMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <WandSparkles className="h-4 w-4" />}
              {tr("Создать", "Create")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
"""

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + replacement + '\n' + content[end_idx:]
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Success")
else:
    print("Failed to find boundaries.")
