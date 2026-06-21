import { localize } from "@/lib/i18n";

import type { SearchResult, SettingsSection } from "./settingsModel";

interface SectionLabelSource {
  id: SettingsSection;
  labelRu: string;
  labelEn: string;
}

export function SettingsSearchResults({
  searchResults,
  sections,
  lang,
  onSelectSection,
}: {
  searchResults: SearchResult[];
  sections: SectionLabelSource[];
  lang: string;
  onSelectSection: (section: SettingsSection) => void;
}) {
  return (
    <div className="mb-4 rounded-[1.2rem] border border-border bg-background p-4">
      <div className="text-sm font-semibold text-foreground">{localize(lang, "Результаты поиска", "Search Results")}</div>
      <div className="mt-1 text-xs text-muted-foreground">
        {searchResults.length > 0
          ? localize(lang, `${searchResults.length} совпавших разделов`, `${searchResults.length} matching settings areas`)
          : localize(lang, "Совпавших разделов нет", "No matching settings areas")}
      </div>
      {searchResults.length > 0 ? (
        <div className="mt-3 grid gap-2">
          {searchResults.map((item) => {
            const section = sections.find((sectionItem) => sectionItem.id === item.section) || sections[0];
            return (
              <button
                key={`${item.section}-${item.label}`}
                type="button"
                onClick={() => onSelectSection(item.section)}
                className="rounded-xl border border-border bg-card px-3 py-3 text-left transition-colors hover:border-primary/20 hover:bg-secondary"
              >
                <div className="flex items-center gap-2">
                  <span className="rounded-full border border-border bg-background px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                    {localize(lang, section.labelRu, section.labelEn)}
                  </span>
                  <span className="text-sm font-medium text-foreground">{item.label}</span>
                </div>
                <pre className="mt-2 whitespace-pre-wrap font-mono text-xs leading-5 text-muted-foreground">
                  {item.snippet}
                </pre>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
