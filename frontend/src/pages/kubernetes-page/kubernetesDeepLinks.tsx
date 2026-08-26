import { ExternalLink } from "lucide-react";

import type { KubernetesDeepLinkPayload } from "@/api";
import { Button } from "@/components/ui/button";
import { localize } from "@/lib/i18n";

export type OnOpenDeepLink = (payload: KubernetesDeepLinkPayload) => void;

const linkLabels: Record<string, { ru: string; en: string }> = {
  home: { ru: "Открыть", en: "Open" },
  rancher: { ru: "Rancher", en: "Rancher" },
  rancher_fleet: { ru: "Fleet", en: "Fleet" },
  devtron_app: { ru: "Devtron", en: "Devtron" },
  logs: { ru: "Логи", en: "Logs" },
  history: { ru: "История", en: "History" },
  values: { ru: "Параметры", en: "Values" },
};

function deepLinkEntries(links: Record<string, unknown> | undefined, limit = 3) {
  if (!links || typeof links !== "object") return [];
  return Object.entries(links)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string" && /^https?:\/\//.test(entry[1]))
    .slice(0, limit);
}

export function DeepLinkButtons({
  links,
  lang,
  target,
  onOpenLink,
  limit = 3,
}: {
  links: Record<string, unknown> | undefined;
  lang: string;
  target: Omit<KubernetesDeepLinkPayload, "link_key" | "url">;
  onOpenLink?: OnOpenDeepLink;
  limit?: number;
}) {
  const entries = deepLinkEntries(links, limit);
  if (!entries.length) return null;
  return (
    <>
      {entries.map(([key, url]) => {
        const label = linkLabels[key] || { ru: key, en: key };
        return (
          <Button key={`${target.target_type}-${target.target_id || target.target_name}-${key}`} asChild size="xs" variant="outline">
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              onClick={() => onOpenLink?.({ ...target, link_key: key, url })}
              aria-label={localize(lang, `Открыть ${label.ru}`, `Open ${label.en}`)}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              {localize(lang, label.ru, label.en)}
            </a>
          </Button>
        );
      })}
    </>
  );
}
