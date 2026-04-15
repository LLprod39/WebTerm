import type { CheckedState } from "@radix-ui/react-checkbox";

import type { StudioSkill } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

import { t, type NodePanelLang } from "./shared";

type PolicyCardProps = {
  lang: NodePanelLang;
  skill: StudioSkill;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

export function PolicyCard({
  lang,
  skill,
  checked,
  onCheckedChange,
}: PolicyCardProps) {
  const description = skill.guardrail_summary?.length
    ? skill.guardrail_summary.slice(0, 2).join(" • ")
    : skill.description;

  const badges = [
    skill.runtime_enforced
      ? { key: "runtime", label: t(lang, "runtime", "runtime"), className: "border-sky-500/30 bg-sky-500/10 text-sky-200" }
      : null,
    skill.safety_level
      ? { key: skill.safety_level, label: skill.safety_level, className: "border-amber-500/30 bg-amber-500/10 text-amber-100" }
      : null,
    skill.service
      ? { key: skill.service, label: skill.service, className: "border-border/70 bg-muted/40 text-muted-foreground" }
      : null,
  ].filter(Boolean) as Array<{ key: string; label: string; className: string }>;

  return (
    <label
      className={cn(
        "flex cursor-pointer gap-3 rounded-2xl border px-3 py-3 transition-colors",
        checked
          ? "border-primary/50 bg-primary/10"
          : "border-border/70 bg-background/70 hover:border-primary/30 hover:bg-muted/30",
      )}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={(value: CheckedState) => onCheckedChange(Boolean(value))}
        aria-label={skill.name}
        className="mt-0.5 h-4 w-4 rounded-md"
      />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{skill.name}</span>
          {badges.map((badge) => (
            <Badge
              key={badge.key}
              variant="outline"
              className={cn("text-[10px]", badge.className)}
            >
              {badge.label}
            </Badge>
          ))}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {description || t(lang, "Описание политики пока не задано.", "Policy description is not available yet.")}
        </p>
      </div>
    </label>
  );
}
