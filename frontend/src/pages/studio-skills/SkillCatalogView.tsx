import { Loader2, Search, Server, Shield, WandSparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SoftHeader } from "@/components/ui/page-shell";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { StudioSkill } from "@/lib/api";

import { SkillCard } from "./SkillCards";

type TranslateFn = (ru: string, en: string) => string;

type SkillCatalogViewProps = {
  tr: TranslateFn;
  lang: "ru" | "en";
  skills: StudioSkill[];
  filteredSkills: StudioSkill[];
  services: string[];
  search: string;
  serviceFilter: string;
  isLoading: boolean;
  isValidating: boolean;
  canOpenMcp: boolean;
  onSearchChange: (value: string) => void;
  onServiceFilterChange: (value: string) => void;
  onSelectSkill: (slug: string) => void;
  onCreateSkill: () => void;
  onValidate: () => void;
  onOpenMcp: () => void;
};

export function SkillCatalogView({
  tr,
  lang,
  skills,
  filteredSkills,
  services,
  search,
  serviceFilter,
  isLoading,
  isValidating,
  canOpenMcp,
  onSearchChange,
  onServiceFilterChange,
  onSelectSkill,
  onCreateSkill,
  onValidate,
  onOpenMcp,
}: SkillCatalogViewProps) {
  return (
    <div className="flex-1 overflow-auto flex flex-col">
      <div className="shrink-0 px-4 pb-2 pt-5 md:px-6">
        <SoftHeader
          title={tr("Каталог навыков", "Skill Catalog")}
          count={skills.length > 0 ? skills.length : undefined}
          subtitle={tr(
            "Навык хранит инструкции и ограничения для агента. Выберите сервис, проверьте правила и отредактируйте файлы.",
            "A skill stores instructions and guardrails for an agent. Choose a service, review the rules, and edit its files.",
          )}
          actions={
            <>
              {canOpenMcp ? (
                <Button variant="outline" size="sm" onClick={onOpenMcp} className="h-10 gap-2 rounded-sm px-4 font-medium">
                  <Server className="h-4 w-4 text-primary/80" />
                  {tr("MCP-серверы", "MCP servers")}
                </Button>
              ) : null}
              <Button variant="outline" size="sm" onClick={onValidate} className="h-10 gap-2 rounded-sm px-4 font-medium border-border hover:bg-secondary">
                {isValidating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shield className="h-4 w-4 text-primary/80" />}
                {tr("Проверить", "Validate")}
              </Button>
              <Button size="sm" onClick={onCreateSkill} className="h-10 gap-2 rounded-sm px-4 font-medium">
                <WandSparkles className="h-4 w-4" />
                {tr("Новый навык", "New Skill")}
              </Button>
            </>
          }
        />
      </div>

      <div className="px-6 pb-8 flex-1 flex flex-col gap-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center justify-between rounded-sm border border-border bg-card p-2 pl-4 pr-3">
          <div className="flex items-center gap-4 flex-1">
            <Search className="h-4 w-4 text-muted-foreground shrink-0" />
            <Input
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder={tr("Поиск навыков по названию, сервису или тегу...", "Search skills by name, service or tag...")}
              className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0 text-sm px-0"
            />
          </div>
          <div className="flex w-full flex-wrap items-center gap-3 md:w-auto md:justify-end">
            <Select value={serviceFilter} onValueChange={onServiceFilterChange}>
              <SelectTrigger className="h-10 w-full rounded-lg border-border/50 bg-background/50 text-xs sm:w-[180px]">
                <SelectValue placeholder={tr("Все сервисы", "All services")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">{tr("Все сервисы", "All services")}</SelectItem>
                {services.map((service) => (
                  <SelectItem key={service} value={service}>{service}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="w-px h-6 bg-border/40 mx-1"></div>
            <span className="text-xs font-medium text-muted-foreground whitespace-nowrap bg-muted/40 px-2 py-1 rounded-md">
              {tr(`${filteredSkills.length} найдено`, `${filteredSkills.length} found`)}
            </span>
            <Button size="sm" variant="outline" className="h-10 gap-1.5 rounded-lg px-3" onClick={onCreateSkill}>
              <Sparkles className="h-3.5 w-3.5" />
              {tr("Создать", "Create")}
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin opacity-50" />
            {tr("Загрузка навыков...", "Loading skills...")}
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center rounded-sm border border-dashed border-border bg-muted/5 min-h-[300px]">
            <div className="h-10 w-10 rounded-sm bg-muted/30 flex items-center justify-center mb-3">
              <Search className="h-5 w-5 text-muted-foreground/60" />
            </div>
            <p className="text-sm font-medium text-foreground">{tr("Навыки не найдены", "No skills found")}</p>
            <p className="text-xs text-muted-foreground mt-1">{tr("Попробуйте изменить параметры поиска", "Try changing your search filters")}</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {filteredSkills.map((skill) => (
              <SkillCard key={skill.slug} skill={skill} isSelected={false} onSelect={() => onSelectSkill(skill.slug)} lang={lang} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
