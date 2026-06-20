import { CheckCircle2, GitBranch, Loader2, Route, ShieldCheck, Wand2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PipelineDraftReview } from "@/components/studio/PipelineDraftReview";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type {
  StudioPipelineAssistantResponse,
  StudioPipelineTemplateRecommendation,
} from "@/lib/studioPipelineDraftsApi";

import type { StudioDraftMobilePane } from "./studioDraftsModel";

export function StudioDraftReviewPanel({
  lang,
  mobilePane,
  activeResponse,
  activeGraphCounts,
  hasOpenQuestions,
  activeCanApply,
  applyPending,
  activeCanValidate,
  validatePending,
  useTemplatePending,
  activeCanSwitchTemplate,
  selectedSkeletonSlug,
  activeTemplateRecommendations,
  onApply,
  onValidate,
  onUseTemplate,
  onSelectedSkeletonSlugChange,
}: {
  lang: string;
  mobilePane: StudioDraftMobilePane;
  activeResponse: StudioPipelineAssistantResponse | null;
  activeGraphCounts: { nodes: number; edges: number };
  hasOpenQuestions: boolean;
  activeCanApply: boolean;
  applyPending: boolean;
  activeCanValidate: boolean;
  validatePending: boolean;
  useTemplatePending: boolean;
  activeCanSwitchTemplate: boolean;
  selectedSkeletonSlug: string;
  activeTemplateRecommendations: StudioPipelineTemplateRecommendation[];
  onApply: (openEditor: boolean) => void;
  onValidate: () => void;
  onUseTemplate: () => void;
  onSelectedSkeletonSlugChange: (slug: string) => void;
}) {
  return (
    <ScrollArea className={cn("min-h-0 flex-1 p-4 xl:block", mobilePane === "compose" ? "hidden" : "block")}>
      {activeResponse ? (
        <PipelineDraftReview
          response={activeResponse}
          lang={lang}
          graphCounts={activeGraphCounts}
          hideQuestions={hasOpenQuestions}
          actions={
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <Button type="button" className="h-10 gap-1.5" disabled={!activeCanApply || applyPending} onClick={() => onApply(false)}>
                {applyPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                {localize(lang, "Создать пайплайн", "Create pipeline")}
              </Button>
              <Button type="button" variant="outline" className="h-10 gap-1.5" disabled={!activeCanApply || applyPending} onClick={() => onApply(true)}>
                <Route className="h-3.5 w-3.5" />
                {localize(lang, "Открыть редактор", "Open editor")}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-10 gap-1.5"
                disabled={!activeCanValidate || validatePending || applyPending || useTemplatePending}
                onClick={onValidate}
              >
                {validatePending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                {localize(lang, "Проверить dry-run", "Validate dry-run")}
              </Button>
              {activeTemplateRecommendations.length ? (
                <div className="rounded-lg border border-border/70 bg-background/45 p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        {localize(lang, "Пилотный шаблон", "Pilot template")}
                      </div>
                      <div className="mt-0.5 truncate text-[11px] text-muted-foreground/80">
                        {activeResponse.selected_template?.name || localize(lang, "Рекомендованный шаблон", "Recommended template")}
                      </div>
                    </div>
                    {activeResponse.selected_template?.slug ? (
                      <Badge variant="outline" className="shrink-0 border-primary/25 bg-primary/10 text-[10px] text-primary">
                        {activeResponse.selected_template.slug}
                      </Badge>
                    ) : null}
                  </div>
                  <div className="grid gap-2">
                    <Select value={selectedSkeletonSlug} onValueChange={onSelectedSkeletonSlugChange} disabled={!activeCanSwitchTemplate || useTemplatePending}>
                      <SelectTrigger className="h-9 bg-card/70 text-xs" aria-label={localize(lang, "Пилотный шаблон", "Pilot template")}>
                        <SelectValue placeholder={localize(lang, "Выберите шаблон", "Select template")} />
                      </SelectTrigger>
                      <SelectContent>
                        {activeTemplateRecommendations.map((item) => (
                          <SelectItem key={item.slug} value={item.slug}>
                            {item.name || item.slug}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-9 gap-1.5"
                      disabled={!activeCanSwitchTemplate || !selectedSkeletonSlug || useTemplatePending || applyPending}
                      onClick={onUseTemplate}
                    >
                      {useTemplatePending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitBranch className="h-3.5 w-3.5" />}
                      {localize(lang, "Использовать шаблон", "Use template")}
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          }
        />
      ) : (
        <div className="rounded-xl border border-dashed border-border/80 bg-background/45 p-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
            <Wand2 className="h-5 w-5 text-primary" />
          </div>
          <h2 className="mt-4 text-sm font-semibold text-foreground">
            {localize(lang, "Нет выбранного черновика", "No draft selected")}
          </h2>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {localize(
              lang,
              "Создайте или выберите черновик, чтобы увидеть требования, ресурсы, риски и действия.",
              "Create or select a draft to inspect requirements, resources, risks, and actions.",
            )}
          </p>
        </div>
      )}
    </ScrollArea>
  );
}
