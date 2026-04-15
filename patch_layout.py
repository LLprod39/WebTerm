import sys
import re

file_path = 'c:/WebTrerm/ai-server-terminal-main/src/pages/StudioSkillsPage.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Locate the exact markers
start_marker = '  return (\n    <div className="flex h-full flex-col">'
end_marker = '      <Dialog open={createOpen} onOpenChange={setCreateOpen}>'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)

if start_idx == -1 or end_idx == -1:
    print("Markers not found")
    sys.exit(1)

pre_layout = content[:start_idx]
post_layout = content[end_idx:]

# Extract the <Tabs> content block precisely!
tabs_start_marker = '<Tabs defaultValue="overview" className="flex h-full flex-col space-y-4">'
tabs_end_marker = '            </div>\n          </div>\n        </div>\n      </div>'

tabs_start_idx = content.find(tabs_start_marker, start_idx, end_idx)
tabs_end_idx = content.find(tabs_end_marker, tabs_start_idx, end_idx)

if tabs_start_idx == -1 or tabs_end_idx == -1:
    print("Tabs block not found")
    sys.exit(1)

# Now extract only the Tabs structure
# actually we want up to `</Tabs>`
tabs_true_end = content.find('                </Tabs>', tabs_start_idx) + len('                </Tabs>')
tabs_content = content[tabs_start_idx:tabs_true_end]


# We will change the className of Tabs to use max-width and center it
tabs_content_modified = tabs_content.replace(
    '<Tabs defaultValue="overview" className="flex h-full flex-col space-y-4">',
    '<Tabs defaultValue="overview" className="flex h-full flex-col w-full max-w-7xl mx-auto space-y-4">'
)


new_layout = f"""  return (
    <div className="flex h-full flex-col">
      <StudioNav />
      {{validationReport && (
        <div className="px-6 py-2">
          <ValidationSummaryCard report={{validationReport}} />
        </div>
      )}}

      {{!selectedSlug ? (
        <div className="flex-1 overflow-auto flex flex-col">
          {{/* Banner */}}
          <div className="px-6 py-6 pb-4 shrink-0">
            <section className="relative overflow-hidden rounded-2xl border border-border/50 bg-gradient-to-b from-primary/5 via-background/40 to-background/20 px-6 py-8 shadow-sm backdrop-blur-xl">
              <div className="absolute top-0 left-0 h-[1px] w-full bg-gradient-to-r from-transparent via-primary/30 to-transparent" />
              <div className="relative z-10 flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
                <div className="max-w-3xl space-y-4">
                  <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" className="h-10 w-10 shrink-0 rounded-full bg-background/50 backdrop-blur-md hover:bg-background/80" onClick={{() => navigate("/studio")}}>
                      <ArrowLeft className="h-5 w-5 text-muted-foreground" />
                    </Button>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="inline-flex h-6 items-center rounded-full bg-primary/10 px-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-primary ring-1 ring-primary/20">{{tr("Studio library", "Studio library")}}</span>
                      </div>
                      <h1 className="mt-2 flex items-center gap-2.5 text-3xl font-bold tracking-tight text-foreground">
                        <BookOpen className="h-7 w-7 text-primary" />
                        {{tr("Каталог скиллов", "Skill Catalog")}}
                      </h1>
                    </div>
                  </div>
                  <p className="max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
                    {{tr(
                      "Скилл здесь это рабочий плейбук. Выберите сервис, проверьте guardrails и runtime policy, а затем правьте сам workspace прямо из Studio.",
                      "A skill here is an operating playbook. Pick the service, review guardrails and runtime policy, then edit the workspace directly from Studio.",
                    )}}
                  </p>
                  <div className="flex flex-wrap items-center gap-3 text-xs font-medium text-muted-foreground">
                    <div className="flex items-center gap-1.5 rounded-full bg-background/40 px-3 py-1 ring-1 ring-border/50"><BookOpen className="h-3.5 w-3.5"/><span>{{tr(`${{skills.length}} скиллов`, `${{skills.length}} skills`)}}</span></div>
                    <div className="flex items-center gap-1.5 rounded-full bg-background/40 px-3 py-1 ring-1 ring-border/50"><ShieldCheck className="h-3.5 w-3.5 text-amber-500/80"/><span>{{tr(`${{runtimeEnforcedCount}} enforced`, `${{runtimeEnforcedCount}} enforced`)}}</span></div>
                    <div className="flex items-center gap-1.5 rounded-full bg-background/40 px-3 py-1 ring-1 ring-border/50"><Server className="h-3.5 w-3.5"/><span>{{tr(`${{serviceCount}} сервисов`, `${{serviceCount}} services`)}}</span></div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 pt-2 xl:justify-end">
                  {{canOpenMcp ? (
                    <Button variant="outline" size="sm" onClick={{() => navigate("/studio/mcp")}} className="h-10 gap-2 rounded-full px-4 font-medium shadow-sm border-border/50 hover:bg-background/80">
                      <Server className="h-4 w-4 text-primary/80" />
                      {{tr("MCP Реестр", "MCP Registry")}}
                    </Button>
                  ) : null}}
                  <Button variant="outline" size="sm" onClick={{() => validateMutation.mutate()}} className="h-10 gap-2 rounded-full px-4 font-medium shadow-sm border-border/50 hover:bg-background/80">
                    {{validateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shield className="h-4 w-4 text-primary/80" />}}
                    {{tr("Проверить", "Validate")}}
                  </Button>
                  <Button size="sm" onClick={{() => openCreateDialog()}} className="h-10 gap-2 rounded-full bg-primary px-5 font-medium text-primary-foreground shadow-sm shadow-primary/20 transition-all hover:bg-primary/90 hover:shadow-md">
                    <WandSparkles className="h-4 w-4" />
                    {{tr("Новый скилл", "New Skill")}}
                  </Button>
                  {{canOpenAgents ? (
                    <Button size="sm" variant="outline" onClick={{() => navigate("/studio/agents")}} className="h-10 gap-2 rounded-full px-4 font-medium shadow-sm border-border/50 hover:bg-background/80">
                      <Bot className="h-4 w-4 text-primary/80" />
                      {{tr("Агенты", "Agents")}}
                    </Button>
                  ) : null}}
                </div>
              </div>
            </section>
          </div>

          {{/* Grid section */}}
          <div className="px-6 pb-8 flex-1 flex flex-col gap-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-center justify-between rounded-2xl border border-border/70 bg-background/30 p-2 pl-4 pr-3 backdrop-blur-md">
              <div className="flex items-center gap-4 flex-1">
                <Search className="h-4 w-4 text-muted-foreground shrink-0" />
                <Input
                  value={{search}}
                  onChange={{(e) => setSearch(e.target.value)}}
                  placeholder={{tr("Поиск скиллов по названию, сервису или тегу...", "Search skills by name, service or tag...")}}
                  className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0 text-sm px-0"
                />
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <Select value={{serviceFilter}} onValueChange={{setServiceFilter}}>
                  <SelectTrigger className="h-9 w-[180px] text-xs bg-background/50 border-border/50 rounded-lg">
                    <SelectValue placeholder={{tr("Все сервисы", "All services")}} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">{{tr("Все сервисы", "All services")}}</SelectItem>
                    {{services.map((s) => (
                      <SelectItem key={{s}} value={{s}}>{{s}}</SelectItem>
                    ))}}
                  </SelectContent>
                </Select>
                <div className="w-px h-6 bg-border/40 mx-1"></div>
                <span className="text-[11px] font-medium text-muted-foreground whitespace-nowrap bg-muted/40 px-2 py-1 rounded-md">
                  {{tr(`${{filteredSkills.length}} найдено`, `${{filteredSkills.length}} found`)}}
                </span>
                <Button size="sm" variant="outline" className="h-9 gap-1.5 rounded-lg px-3" onClick={{() => openCreateDialog()}}>
                  <Sparkles className="h-3.5 w-3.5" />
                  {{tr("Создать", "Create")}}
                </Button>
              </div>
            </div>

            {{isLoading ? (
              <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-5 w-5 animate-spin opacity-50" />
                {{tr("Загрузка скиллов...", "Loading skills...")}}
              </div>
            ) : filteredSkills.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/5 min-h-[300px]">
                <div className="h-12 w-12 rounded-full bg-muted/20 flex items-center justify-center mb-3">
                  <Search className="h-5 w-5 text-muted-foreground/60" />
                </div>
                <p className="text-sm font-medium text-foreground">{{tr("Скиллы не найдены", "No skills found")}}</p>
                <p className="text-xs text-muted-foreground mt-1">{{tr("Попробуйте изменить параметры поиска", "Try changing your search filters")}}</p>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
                {{filteredSkills.map((skill) => (
                  <SkillCard key={{skill.slug}} skill={{skill}} isSelected={{false}} onSelect={{() => setSelectedSlug(skill.slug)}} lang={{lang}} />
                ))}}
              </div>
            )}}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col overflow-hidden bg-muted/10 relative">
          {{/* MASTER BACK BAR */}}
          <div className="px-6 py-3 flex items-center justify-between border-b border-border/40 bg-background/60 backdrop-blur-md sticky top-0 z-20 shrink-0 shadow-sm">
            <Button variant="ghost" size="sm" onClick={{() => setSelectedSlug("")}} className="h-8 gap-2 rounded-lg text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-4 w-4" />
              {{tr("Назад в каталог", "Back to catalog")}}
            </Button>
            
            <div className="flex items-center gap-2">
              {{selectedSkill && <Badge variant="outline" className="font-mono text-[10px] bg-background/50">{{selectedSkill.slug}}</Badge>}}
            </div>
          </div>

          {{/* WORKSPACE AND TABS AREA */}}
          <div className="flex-1 overflow-auto px-6 lg:px-10 py-8 pb-16">
            {{isFetchingSkill && !selectedSkill ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                {{tr("Загрузка рабочего пространства...", "Loading workspace...")}}
              </div>
            ) : selectedSkill ? (
              {tabs_content_modified}
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-red-500/80">
                {{tr("Ошибка загрузки скилла.", "Error loading skill.")}}
              </div>
            )}}
          </div>
        </div>
      )}}
\n"""

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(pre_layout + new_layout + post_layout)

print("Patch applied")
