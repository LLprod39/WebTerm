import { localize, useI18n } from "@/lib/i18n";

export type WebSource = { title?: string; url?: string };

export function WebSourcesCard({ sources }: { sources: WebSource[] }) {
  const { lang } = useI18n();
  if (!sources.length) return null;

  return (
    <div className="max-w-[min(640px,100%)] rounded-sm border border-border/50 bg-muted/15 px-3 py-2">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {localize(lang, "Источники", "Sources")}
      </div>
      <div className="space-y-1">
        {sources.map((source, index) => (
          <a
            key={`${source.url || "source"}-${index}`}
            href={source.url}
            target="_blank"
            rel="noreferrer noopener"
            className="block truncate text-[11px] text-primary underline-offset-2 hover:underline"
          >
            {index + 1}. {source.title || source.url}
          </a>
        ))}
      </div>
    </div>
  );
}
