import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Clock,
  Copy,
  Globe,
  Loader2,
  RefreshCw,
  Search,
  Server,
  Shield,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { fetchLinuxUiSettings, type FrontendServer } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";

import { InfoCard } from "./linux-ui-settings/SettingsPrimitives";
import {
  CrontabSection,
  EnvironmentSection,
  GeneralSection,
  OverviewSection,
  SecuritySection,
  UsersSection,
} from "./linux-ui-settings/SettingsSections";
import { SettingsSearchResults } from "./linux-ui-settings/SettingsSearchResults";
import {
  buildSectionCopyContent,
  buildSettingsSearchResults,
  type SettingsSection,
} from "./linux-ui-settings/settingsModel";

interface SectionDef {
  id: SettingsSection;
  labelRu: string;
  labelEn: string;
  icon: ReactNode;
}

const SECTIONS: SectionDef[] = [
  { id: "overview", labelRu: "Обзор", labelEn: "Overview", icon: <Server className="h-4 w-4" /> },
  { id: "general", labelRu: "Система", labelEn: "General", icon: <Server className="h-4 w-4" /> },
  { id: "users", labelRu: "Пользователи", labelEn: "Users", icon: <Users className="h-4 w-4" /> },
  { id: "crontab", labelRu: "Задачи cron", labelEn: "Cron Jobs", icon: <Clock className="h-4 w-4" /> },
  { id: "environment", labelRu: "Окружение", labelEn: "Environment", icon: <Globe className="h-4 w-4" /> },
  { id: "security", labelRu: "Безопасность", labelEn: "Security", icon: <Shield className="h-4 w-4" /> },
];

function sectionLabel(section: SectionDef, lang: string) {
  return localize(lang, section.labelRu, section.labelEn);
}

export function SystemSettingsWindow({
  server,
  active,
}: {
  server: FrontendServer;
  active: boolean;
}) {
  const { toast } = useToast();
  const { lang } = useI18n();
  const [section, setSection] = useState<SettingsSection>("overview");
  const [query, setQuery] = useState("");

  const settingsQuery = useQuery({
    queryKey: ["linux-ui", server.id, "settings"],
    queryFn: () => fetchLinuxUiSettings(server.id),
    enabled: active,
    staleTime: 30_000,
  });

  const settings = settingsQuery.data?.settings;
  const hasError = settingsQuery.error instanceof Error ? settingsQuery.error.message : "Failed to load settings";
  const normalizedQuery = query.trim().toLowerCase();
  const searchResults = useMemo(
    () => buildSettingsSearchResults(settings, query, lang),
    [lang, query, settings],
  );
  const sectionContent = useMemo(
    () => buildSectionCopyContent(settings, section, lang),
    [lang, section, settings],
  );
  const activeSection = SECTIONS.find((item) => item.id === section) || SECTIONS[0];

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-card text-foreground">
      <nav className="flex w-52 shrink-0 flex-col border-r border-border bg-card">
        <div className="border-b border-border px-3 py-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-xs font-medium text-foreground">{localize(lang, "Системные настройки", "System Settings")}</div>
              <div className="text-[10px] text-muted-foreground">{server.name}</div>
            </div>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 w-8 shrink-0 rounded-xl p-0 text-muted-foreground hover:bg-secondary hover:text-foreground"
              onClick={() => void settingsQuery.refetch()}
              disabled={settingsQuery.isFetching}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", settingsQuery.isFetching && "animate-spin")} />
            </Button>
          </div>
          <div className="relative mt-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={localize(lang, "Поиск настроек...", "Search settings...")}
              className="h-9 rounded-xl border-border bg-background pl-9 text-sm"
            />
          </div>
        </div>
        <div className="border-b border-border px-3 py-3">
          <div className="grid gap-2">
            <InfoCard lang={lang} label={localize(lang, "Хост", "Host")} value={settings?.general.hostname || server.host} mono />
            <InfoCard lang={lang} label={localize(lang, "Пользователь", "User")} value={settings?.users.current_user || server.username} mono />
            <InfoCard lang={lang} label="Uptime" value={settings?.general.uptime || localize(lang, "Загрузка...", "Loading...")} />
          </div>
        </div>
        <div className="flex-1 space-y-1.5 p-2">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSection(item.id)}
              className={cn(
                "flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-xs transition-colors",
                section === item.id
                  ? "border border-primary/20 bg-primary/10 text-foreground"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              <span className="flex h-4 w-4 items-center justify-center [&>svg]:h-3.5 [&>svg]:w-3.5">{item.icon}</span>
              {sectionLabel(item, lang)}
            </button>
          ))}
        </div>
      </nav>

      <ScrollArea className="min-h-0 flex-1">
        <div className="p-4">
          <div className="mb-4 rounded-[1.2rem] border border-border bg-background p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-sm font-semibold text-foreground">{sectionLabel(activeSection, lang)}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {localize(
                    lang,
                    "Короткий системный снимок: только операционные детали, которые обычно важны в первую очередь.",
                    "Focused system snapshot with only the operational details that usually matter first.",
                  )}
                </div>
                {normalizedQuery ? (
                  <div className="mt-2 text-[11px] text-muted-foreground">
                    {localize(lang, "Фильтр поиска", "Search filter")}: <span className="font-mono text-foreground">{query}</span>
                  </div>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-xl border-border bg-card px-3 text-xs text-foreground hover:bg-secondary"
                  onClick={() => void settingsQuery.refetch()}
                  disabled={settingsQuery.isFetching}
                >
                  <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", settingsQuery.isFetching && "animate-spin")} />
                  {localize(lang, "Обновить", "Refresh")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-xl border-border bg-card px-3 text-xs text-foreground hover:bg-secondary"
                  onClick={async () => {
                    await navigator.clipboard.writeText(sectionContent);
                    toast({
                      title: localize(lang, "Скопировано", "Copied"),
                      description: localize(lang, "Детали раздела скопированы", `Copied ${section} details`),
                    });
                  }}
                  disabled={!sectionContent}
                >
                  <Copy className="mr-1.5 h-3.5 w-3.5" />
                  {localize(lang, "Копировать", "Copy")}
                </Button>
              </div>
            </div>
          </div>

          {normalizedQuery ? (
            <SettingsSearchResults
              searchResults={searchResults}
              sections={SECTIONS}
              lang={lang}
              onSelectSection={setSection}
            />
          ) : null}

          {settingsQuery.isLoading && !settings ? (
            <div className="flex h-full min-h-[220px] items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <span className="ml-2 text-sm text-muted-foreground">{localize(lang, "Загружаю системную информацию...", "Loading system info...")}</span>
            </div>
          ) : settingsQuery.isError || !settings ? (
            <div className="rounded-[1.2rem] border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              {hasError}
            </div>
          ) : (
            <>
              {section === "overview" ? <OverviewSection settings={settings} query={query} lang={lang} /> : null}
              {section === "general" ? <GeneralSection settings={settings.general} query={query} lang={lang} /> : null}
              {section === "users" ? <UsersSection settings={settings.users} query={query} lang={lang} /> : null}
              {section === "crontab" ? <CrontabSection settings={settings.crontab} query={query} lang={lang} /> : null}
              {section === "environment" ? <EnvironmentSection settings={settings.environment} query={query} lang={lang} /> : null}
              {section === "security" ? <SecuritySection settings={settings.security} query={query} lang={lang} /> : null}
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
