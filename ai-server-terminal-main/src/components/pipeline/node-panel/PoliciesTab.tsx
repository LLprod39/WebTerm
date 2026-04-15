import { BookOpen } from "lucide-react";

import type { AgentConfig, StudioSkill } from "@/lib/api";
import { Button } from "@/components/ui/button";

import { PolicyCard } from "./PolicyCard";
import { t, type NodePanelLang } from "./shared";

type PoliciesTabProps = {
  lang: NodePanelLang;
  skillList: StudioSkill[];
  selectedAgent: AgentConfig | null;
  selectedSkillSlugs: string[];
  onToggleSkill: (skillSlug: string) => void;
  onBrowseCatalog: () => void;
};

export function PoliciesTab({
  lang,
  skillList,
  selectedAgent,
  selectedSkillSlugs,
  onToggleSkill,
  onBrowseCatalog,
}: PoliciesTabProps) {
  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">
            {selectedAgent
              ? t(lang, "Дополнительные политики", "Extra policies")
              : t(lang, "Skills / Policies", "Skills / Policies")}
          </h3>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {selectedAgent
              ? t(
                  lang,
                  "Node-level политики будут объединены с правилами выбранного Agent Config во время выполнения.",
                  "Node-level policies will be merged with the selected Agent Config at runtime.",
                )
              : t(
                  lang,
                  "Подключайте playbooks, guardrails и runtime-политики прямо к этой ноде.",
                  "Attach playbooks, guardrails, and runtime policies directly to this node.",
                )}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 gap-1.5 rounded-xl"
          onClick={onBrowseCatalog}
        >
          <BookOpen className="h-3.5 w-3.5" />
          {t(lang, "Каталог", "Catalog")}
        </Button>
      </div>

      {skillList.length ? (
        <div className="grid gap-3">
          {skillList.map((skill) => (
            <PolicyCard
              key={skill.slug}
              lang={lang}
              skill={skill}
              checked={selectedSkillSlugs.includes(skill.slug)}
              onCheckedChange={() => onToggleSkill(skill.slug)}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-border/70 px-4 py-6 text-center text-sm text-muted-foreground">
          {t(lang, "Каталог политик пока пуст.", "The policy catalog is empty right now.")}
        </div>
      )}
    </div>
  );
}
