import type { Dispatch, SetStateAction } from "react";
import { BookMarked, Code2, FolderPlus, Loader2, Shield } from "lucide-react";
import { StudioNavIcons } from "@/lib/app-icons";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { StudioSkillTemplate, StudioSkillValidationResponse } from "@/lib/api";

import { ValidationSummaryCard } from "./SkillCards";
import {
  createWizardState,
  SAFETY_LEVELS,
  safetyLevelLabel,
  slugifySkillName,
  type SkillWizardState,
} from "./skillScaffold";

type TranslateFn = (ru: string, en: string) => string;

type CreateSkillDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tr: TranslateFn;
  lang: "ru" | "en";
  templates: StudioSkillTemplate[];
  selectedTemplate: StudioSkillTemplate | null;
  selectedTemplateSlug: string;
  wizard: SkillWizardState;
  slugTouched: boolean;
  canSubmitWizard: boolean;
  starterFilesCount: number;
  isPending: boolean;
  setSelectedTemplateSlug: (slug: string) => void;
  setWizard: Dispatch<SetStateAction<SkillWizardState>>;
  setSlugTouched: (touched: boolean) => void;
  onSubmit: () => void;
};

export function CreateSkillDialog({
  open,
  onOpenChange,
  tr,
  lang,
  templates,
  selectedTemplate,
  selectedTemplateSlug,
  wizard,
  slugTouched,
  canSubmitWizard,
  starterFilesCount,
  isPending,
  setSelectedTemplateSlug,
  setWizard,
  setSlugTouched,
  onSubmit,
}: CreateSkillDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={tr("Закрыть", "Close")} className="grid max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-3xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-xl border-border bg-background p-0 shadow-2xl">
        <div className="border-b border-border/50 bg-card/70 px-5 py-5 sm:px-6">
          <DialogHeader className="border-0 p-0">
            <DialogTitle className="flex items-center gap-3 text-xl font-semibold">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
                <StudioNavIcons.skills className="h-4 w-4 text-primary" strokeWidth={1.5} />
              </span>
              {tr("Создать скилл", "Create skill")}
            </DialogTitle>
            <DialogDescription className="mt-2 max-w-2xl text-[13px] leading-5">
              {tr("Заполните только то, что агенту нужно понять: как называется скилл и когда его применять. Инструкции и скрипты можно добавить сейчас или позже во вкладке файлов.", "Fill only what the agent needs to understand: the skill name and when to use it. Instructions and scripts can be added now or later in the file workspace.")}
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="min-h-0 overflow-y-auto px-5 py-5 sm:px-6">
          <div className="space-y-5">
            <section className="space-y-4">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">1</span>
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{tr("Назначение", "Purpose")}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">{tr("Это попадёт в SKILL.md и поможет агенту выбрать скилл в нужный момент.", "This goes into SKILL.md and helps the agent choose the skill at the right time.")}</p>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{tr("Шаблон", "Template")}</Label>
                <Select
                  value={selectedTemplateSlug}
                  onValueChange={(value) => {
                    setSelectedTemplateSlug(value);
                    const template = templates.find((item) => item.slug === value) || null;
                    setWizard(createWizardState(template, lang));
                    setSlugTouched(false);
                  }}
                >
                  <SelectTrigger className="h-10">
                    <SelectValue placeholder={tr("С чистого листа", "Blank slate")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">{tr("С чистого листа", "Blank slate")}</SelectItem>
                    {templates.map((template) => (
                      <SelectItem key={template.slug} value={template.slug}>{template.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedTemplate?.summary ? <p className="text-xs leading-4 text-muted-foreground">{selectedTemplate.summary}</p> : null}
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{tr("Название скилла", "Skill name")}</Label>
                <Input
                  className="h-10"
                  value={wizard.name}
                  onChange={(event) => {
                    const value = event.target.value;
                    setWizard((prev) => ({ ...prev, name: value, slug: slugTouched ? prev.slug : slugifySkillName(value) }));
                  }}
                  placeholder={tr("Например: Docker health-check", "Example: Docker health-check")}
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{tr("Когда применять этот скилл", "When to use this skill")}</Label>
                <Textarea
                  rows={4}
                  className="resize-none text-sm leading-6"
                  value={wizard.description}
                  onChange={(event) => setWizard((prev) => ({ ...prev, description: event.target.value }))}
                  placeholder={tr("Опишите обычным языком: для каких задач, на каких серверах/сервисах и какой результат должен получить агент.", "Describe in plain language: tasks, target servers/services, and the result the agent should produce.")}
                />
              </div>
            </section>

            <section className="space-y-3">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">2</span>
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{tr("Материалы к скиллу", "Skill materials")}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">{tr("Необязательно. Добавьте инструкцию или готовый скрипт, если они уже есть.", "Optional. Attach a runbook or ready automation script if you already have them.")}</p>
                </div>
              </div>

              <div className={`rounded-lg border p-4 transition-colors ${wizard.starter_reference_enabled ? "border-primary/30 bg-primary/5" : "border-border/70 bg-card/35"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-1 gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background/70 text-primary ring-1 ring-border/60">
                      <BookMarked className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="text-sm font-semibold text-foreground">{tr("Рабочая инструкция", "Working runbook")}</div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{tr("Markdown-файл с правилами, примерами, входными данными и порядком действий.", "Markdown file with rules, examples, inputs, and workflow steps.")}</p>
                    </div>
                  </div>
                  <div className="ml-auto flex shrink-0 items-center gap-2">
                    <Label htmlFor="starter-reference" className="text-xs text-muted-foreground">{wizard.starter_reference_enabled ? tr("Добавлена", "Added") : tr("Добавить", "Add")}</Label>
                    <Switch
                      id="starter-reference"
                      checked={wizard.starter_reference_enabled}
                      onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, starter_reference_enabled: Boolean(checked), with_references: checked ? true : prev.with_references }))}
                    />
                  </div>
                </div>
                {wizard.starter_reference_enabled ? (
                  <div className="mt-4 space-y-2">
                    <Label className="text-xs text-muted-foreground">{tr("Текст инструкции", "Runbook content")}</Label>
                    <Textarea
                      rows={7}
                      className="font-mono text-xs leading-5"
                      value={wizard.starter_reference_content}
                      onChange={(event) => setWizard((prev) => ({ ...prev, starter_reference_content: event.target.value }))}
                      spellCheck={false}
                    />
                  </div>
                ) : null}
              </div>

              <div className={`rounded-lg border p-4 transition-colors ${wizard.starter_script_enabled ? "border-primary/30 bg-primary/5" : "border-border/70 bg-card/35"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-1 gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background/70 text-primary ring-1 ring-border/60">
                      <Code2 className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="text-sm font-semibold text-foreground">{tr("Скрипт автоматизации", "Automation script")}</div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{tr("Готовый shell/Python/JS-скрипт, который агент сможет открыть, проверить и использовать.", "A ready shell/Python/JS script the agent can open, inspect, and use.")}</p>
                    </div>
                  </div>
                  <div className="ml-auto flex shrink-0 items-center gap-2">
                    <Label htmlFor="starter-script" className="text-xs text-muted-foreground">{wizard.starter_script_enabled ? tr("Добавлен", "Added") : tr("Добавить", "Add")}</Label>
                    <Switch
                      id="starter-script"
                      checked={wizard.starter_script_enabled}
                      onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, starter_script_enabled: Boolean(checked), with_scripts: checked ? true : prev.with_scripts }))}
                    />
                  </div>
                </div>
                {wizard.starter_script_enabled ? (
                  <div className="mt-4 space-y-2">
                    <Label className="text-xs text-muted-foreground">{tr("Текст скрипта", "Script content")}</Label>
                    <Textarea
                      rows={7}
                      className="font-mono text-xs leading-5"
                      value={wizard.starter_script_content}
                      onChange={(event) => setWizard((prev) => ({ ...prev, starter_script_content: event.target.value }))}
                      spellCheck={false}
                    />
                  </div>
                ) : null}
              </div>
            </section>

            <Accordion type="single" collapsible className="rounded-lg border border-border/70 bg-background/35 px-3">
              <AccordionItem value="advanced" className="border-0">
                <AccordionTrigger className="py-4 text-sm font-semibold hover:no-underline">{tr("Дополнительно", "Advanced")}</AccordionTrigger>
                <AccordionContent className="space-y-4 pb-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Slug</Label>
                      <Input
                        className="h-9 font-mono text-xs"
                        value={wizard.slug}
                        onChange={(event) => {
                          setSlugTouched(true);
                          setWizard((prev) => ({ ...prev, slug: event.target.value }));
                        }}
                        placeholder="docker-health-check"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Уровень риска", "Safety level")}</Label>
                      <Select value={wizard.safety_level} onValueChange={(value) => setWizard((prev) => ({ ...prev, safety_level: value }))}>
                        <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {SAFETY_LEVELS.map((level) => (<SelectItem key={level} value={level}>{safetyLevelLabel(level, lang)}</SelectItem>))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Сервис", "Service")}</Label>
                      <Input className="h-9" value={wizard.service} onChange={(event) => setWizard((prev) => ({ ...prev, service: event.target.value }))} placeholder="docker, github" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Категория", "Category")}</Label>
                      <Input className="h-9" value={wizard.category} onChange={(event) => setWizard((prev) => ({ ...prev, category: event.target.value }))} placeholder="Ops, IAM" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Теги", "Tags")}</Label>
                      <Input className="h-9" value={wizard.tags_text} onChange={(event) => setWizard((prev) => ({ ...prev, tags_text: event.target.value }))} placeholder="docker, health" />
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Краткие ограничения", "Guardrail summary")}</Label>
                      <Textarea rows={3} className="text-xs leading-5" value={wizard.guardrail_summary_text} onChange={(event) => setWizard((prev) => ({ ...prev, guardrail_summary_text: event.target.value }))} placeholder={tr("Например: только read-only проверки без подтверждения.", "Example: read-only checks only without confirmation.")} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{tr("Рекомендуемые инструменты", "Recommended tools")}</Label>
                      <Textarea rows={3} className="text-xs leading-5" value={wizard.recommended_tools_text} onChange={(event) => setWizard((prev) => ({ ...prev, recommended_tools_text: event.target.value }))} placeholder="report, ask_user, analyze_output" />
                    </div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-card/35 px-3 py-2">
                      <div>
                        <span className="text-xs font-medium text-foreground">{tr("Создать папку assets/", "Create assets/ folder")}</span>
                        <p className="mt-0.5 text-xs text-muted-foreground">{tr("Для CSV, шаблонов и примеров данных.", "For CSV, templates, and sample data.")}</p>
                      </div>
                      <Switch checked={wizard.with_assets} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, with_assets: Boolean(checked) }))} />
                    </div>
                    <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
                      <div>
                        <span className="text-xs font-medium text-destructive">{tr("Перезаписать существующий slug", "Overwrite existing slug")}</span>
                        <p className="mt-0.5 text-xs text-muted-foreground">{tr("Только если обновляете свой скилл.", "Only when updating your own skill.")}</p>
                      </div>
                      <Switch checked={wizard.force} onCheckedChange={(checked) => setWizard((prev) => ({ ...prev, force: Boolean(checked) }))} />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{tr("Политика выполнения JSON", "Runtime policy JSON")}</Label>
                    <Textarea rows={6} value={wizard.runtime_policy_text} onChange={(event) => setWizard((prev) => ({ ...prev, runtime_policy_text: event.target.value }))} className="font-mono text-xs leading-5" spellCheck={false} />
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-border/50 bg-card/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="text-xs leading-5 text-muted-foreground">
            {canSubmitWizard
              ? tr(`Будет создан SKILL.md${starterFilesCount ? ` и файлов: ${starterFilesCount}` : ""}.`, `Will create SKILL.md${starterFilesCount ? ` and ${starterFilesCount} file(s)` : ""}.`)
              : tr("Для создания заполните название и когда применять скилл.", "Add a name and when to use the skill to continue.")}
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" className="text-muted-foreground" onClick={() => onOpenChange(false)}>{tr("Отмена", "Cancel")}</Button>
            <Button onClick={onSubmit} disabled={!canSubmitWizard || isPending} className="h-10 gap-2 px-5">
              {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <StudioNavIcons.skills className="h-4 w-4" strokeWidth={1.5} />}
              {tr("Создать", "Create")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

type CreateFileDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tr: TranslateFn;
  path: string;
  content: string;
  canEditSkill: boolean;
  isPending: boolean;
  onPathChange: (path: string) => void;
  onContentChange: (content: string) => void;
  onCreate: (path: string, content: string) => void;
};

export function CreateFileDialog({
  open,
  onOpenChange,
  tr,
  path,
  content,
  canEditSkill,
  isPending,
  onPathChange,
  onContentChange,
  onCreate,
}: CreateFileDialogProps) {
  const trimmedPath = path.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={tr("Закрыть", "Close")} className="grid max-h-[calc(100dvh-2rem)] max-w-3xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-md border-border bg-background/95">
        <DialogHeader>
          <DialogTitle>{tr("Новый файл рабочей папки", "New workspace file")}</DialogTitle>
          <DialogDescription>{tr("Создайте текстовый файл внутри references/, scripts/ или assets/. Для нового материала плейбука обычно начинайте с references/guide.md.", "Create a text file inside references/, scripts/, or assets/. For new playbook material, start with references/guide.md.")}</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 space-y-4 overflow-y-auto py-2">
          <div className="space-y-1.5">
            <Label className="text-xs">{tr("Путь", "Path")}</Label>
            <Input value={path} onChange={(event) => onPathChange(event.target.value)} placeholder="references/guide.md" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{tr("Содержимое", "Content")}</Label>
            <Textarea rows={16} value={content} onChange={(event) => onContentChange(event.target.value)} className="font-mono text-[12px] leading-5" />
          </div>
          <div className="rounded-xl border border-border/70 bg-background/24 px-4 py-4 text-xs leading-5 text-muted-foreground">
            {tr("Разрешены только относительные пути и текстовые расширения. Абсолютные пути, скрытые файлы и выход за пределы папки скилла backend отклоняет.", "Only relative paths and text extensions are allowed. Absolute paths, hidden files, and escaping the skill directory are rejected by the backend.")}
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>{tr("Отмена", "Cancel")}</Button>
          <Button onClick={() => onCreate(trimmedPath, content)} disabled={!trimmedPath || isPending || !canEditSkill} className="gap-1.5">
            {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderPlus className="h-3.5 w-3.5" />}
            {tr("Создать файл", "Create file")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

type SkillValidationDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tr: TranslateFn;
  strictValidation: boolean;
  isPending: boolean;
  report: StudioSkillValidationResponse | null;
  onStrictValidationChange: (value: boolean) => void;
  onValidate: () => void;
};

export function SkillValidationDialog({
  open,
  onOpenChange,
  tr,
  strictValidation,
  isPending,
  report,
  onStrictValidationChange,
  onValidate,
}: SkillValidationDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={tr("Закрыть", "Close")} className="max-h-[85vh] max-w-4xl overflow-auto rounded-md border-border bg-background/95">
        <DialogHeader>
          <DialogTitle>{tr("Валидация библиотеки скиллов", "Skill Library Validation")}</DialogTitle>
          <DialogDescription>{tr("Проверьте структурные и policy-проблемы в текущей библиотеке скиллов Studio.", "Review structural and policy issues across the current Studio skill library.")}</DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/20 p-4">
          <div>
            <p className="text-sm font-medium">{tr("Режим валидации", "Validation mode")}</p>
            <p className="text-xs text-muted-foreground">{tr("В строгом режиме предупреждения считаются блокерами деплоя.", "Strict mode treats warnings as deployment blockers.")}</p>
          </div>
          <div className="flex items-center gap-2">
            <Label className="text-xs">{tr("Строгий", "Strict")}</Label>
            <Switch checked={strictValidation} onCheckedChange={(checked) => onStrictValidationChange(Boolean(checked))} />
            <Button variant="outline" size="sm" onClick={onValidate} className="gap-1.5">
              {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Shield className="h-3 w-3" />}
              {tr("Повторить", "Re-run")}
            </Button>
          </div>
        </div>

        {report ? (
          <div className="space-y-3">
            <ValidationSummaryCard report={report} />
            {report.results.map((result) => (
              <Card key={result.slug} className={result.errors.length ? "border-red-500/30" : result.warnings.length ? "border-amber-500/30" : "border-green-500/20"}>
                <CardHeader className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-sm">{result.slug}</CardTitle>
                    {result.errors.length === 0 && result.warnings.length === 0 && <Badge variant="secondary" className="text-xs">ok</Badge>}
                    {result.errors.length > 0 && <Badge variant="destructive" className="text-xs">{result.errors.length} {tr("ошибок", "errors")}</Badge>}
                    {result.warnings.length > 0 && <Badge variant="outline" className="text-xs">{result.warnings.length} {tr("предупреждений", "warnings")}</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground">{result.path}</p>
                </CardHeader>
                <CardContent className="space-y-2">
                  {result.errors.length > 0 && (
                    <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
                      <p className="text-xs font-medium text-red-200">{tr("Ошибки", "Errors")}</p>
                      <div className="mt-1 space-y-1">
                        {result.errors.map((item) => (
                          <p key={item} className="text-xs text-red-100">• {item}</p>
                        ))}
                      </div>
                    </div>
                  )}
                  {result.warnings.length > 0 && (
                    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                      <p className="text-xs font-medium text-amber-100">{tr("Предупреждения", "Warnings")}</p>
                      <div className="mt-1 space-y-1">
                        {result.warnings.map((item) => (
                          <p key={item} className="text-xs text-amber-50">• {item}</p>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            {tr("Валидация ещё не запускалась.", "Validation has not been run yet.")}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
