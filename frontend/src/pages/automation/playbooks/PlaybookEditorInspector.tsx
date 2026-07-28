import type { PlaybookCategory, PlaybookVisibility } from "@/api/playbooks";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CATEGORIES, CATEGORY_META } from "../constants";
import type { PlaybookEditorState } from "../playbookEditorState";

interface PlaybookEditorInspectorProps {
  lang: string;
  state: PlaybookEditorState;
  yamlMode: boolean;
  metadataReadOnly: boolean;
  onChange: (patch: Partial<PlaybookEditorState>) => void;
}

export function PlaybookEditorInspector({ lang, state, yamlMode, metadataReadOnly, onChange }: PlaybookEditorInspectorProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  return (
    <div className="grid gap-4 border-t border-border pt-4 sm:grid-cols-3">
      <div className="space-y-1.5">
        <Label htmlFor="playbook-category">{tr("Категория", "Category")}</Label>
        <Select disabled={metadataReadOnly} value={state.category} onValueChange={(category) => onChange({ category: category as PlaybookCategory })}>
          <SelectTrigger id="playbook-category" aria-label={tr("Категория", "Category")}><SelectValue /></SelectTrigger>
          <SelectContent>
            {CATEGORIES.map((category) => (
              <SelectItem key={category} value={category}>{lang === "ru" ? CATEGORY_META[category].labelRu : CATEGORY_META[category].labelEn}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="playbook-visibility">{tr("Доступ", "Access")}</Label>
        <Select disabled={metadataReadOnly} value={state.visibility} onValueChange={(visibility) => onChange({ visibility: visibility as PlaybookVisibility })}>
          <SelectTrigger id="playbook-visibility" aria-label={tr("Доступ", "Access")}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="private">{tr("Только я", "Only me")}</SelectItem>
            <SelectItem value="shared">{tr("Команда", "Team")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="playbook-tags">{tr("Теги", "Tags")}</Label>
        <Input id="playbook-tags" disabled={metadataReadOnly} value={state.tagsText} onChange={(event) => onChange({ tagsText: event.target.value })} placeholder="nginx, production" />
      </div>
      <p className="text-xs text-muted-foreground sm:col-span-3">
        {tr("Формат", "Format")}: {yamlMode ? "Ansible YAML" : "WebTerm runbook"}
      </p>
    </div>
  );
}
