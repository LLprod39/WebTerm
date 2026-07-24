import { useCallback, useEffect, useMemo, useState, type ComponentType } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Bot,
  Globe,
  LayoutDashboard,
  Moon,
  Palette,
  Server,
  Settings,
  Sparkles,
  Terminal,
  Workflow,
  MessageSquare,
  Activity,
  BookOpen,
  Box,
  History,
} from "lucide-react";

import { fetchAgents, fetchFrontendBootstrap } from "@/lib/api";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { getRecentRuns, getRecentServers, pushRecentServer } from "@/lib/recent-entities";
import { localize, useI18n } from "@/lib/i18n";
import { isFlowStyle, useUiStyle } from "@/lib/ui-style";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenAssistant?: () => void;
};

type NavItem = {
  id: string;
  labelRu: string;
  labelEn: string;
  path: string;
  icon: ComponentType<{ className?: string }>;
  keywords?: string;
};

const NAV: NavItem[] = [
  { id: "dashboard", labelRu: "Дашборд", labelEn: "Dashboard", path: "/dashboard", icon: LayoutDashboard, keywords: "home main" },
  { id: "servers", labelRu: "Серверы", labelEn: "Servers", path: "/servers", icon: Server, keywords: "ssh fleet hosts" },
  { id: "playbooks", labelRu: "Плейбуки", labelEn: "Playbooks", path: "/automation", icon: BookOpen, keywords: "ansible yaml automation runbook" },
  { id: "agents", labelRu: "Агенты", labelEn: "Agents", path: "/agents", icon: Bot, keywords: "runs automation" },
  { id: "chat", labelRu: "Операторский чат", labelEn: "Operator chat", path: "/chat", icon: MessageSquare, keywords: "ai assistant" },
  { id: "studio", labelRu: "Studio", labelEn: "Studio", path: "/studio", icon: Workflow, keywords: "pipeline" },
  { id: "monitoring", labelRu: "Insights", labelEn: "Insights", path: "/monitoring", icon: Activity, keywords: "forecast alerts" },
  { id: "k8s", labelRu: "Kubernetes", labelEn: "Kubernetes", path: "/kubernetes", icon: Box, keywords: "cluster pods" },
  { id: "settings", labelRu: "Настройки", labelEn: "Settings", path: "/settings", icon: Settings, keywords: "config" },
];

export function CommandPalette({ open, onOpenChange, onOpenAssistant }: Props) {
  const navigate = useNavigate();
  const { lang, setLang } = useI18n();
  const { style, setStyle } = useUiStyle();
  const [recentServers, setRecentServers] = useState(() => getRecentServers());
  const [recentRuns, setRecentRuns] = useState(() => getRecentRuns());

  const serversQuery = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 30_000,
    enabled: open,
  });

  const agentsQuery = useQuery({
    queryKey: ["agents", "list"],
    queryFn: () => fetchAgents(),
    staleTime: 20_000,
    enabled: open,
  });

  useEffect(() => {
    if (open) {
      setRecentServers(getRecentServers());
      setRecentRuns(getRecentRuns());
    }
  }, [open]);

  const servers = serversQuery.data?.servers ?? [];
  const agents = agentsQuery.data?.agents ?? [];

  const run = useCallback(
    (fn: () => void) => {
      onOpenChange(false);
      // Let dialog close animation start before navigation.
      window.setTimeout(fn, 10);
    },
    [onOpenChange],
  );

  const go = useCallback(
    (path: string) => {
      run(() => navigate(path));
    },
    [navigate, run],
  );

  const toggleTheme = useCallback(() => {
    run(() => {
      if (isFlowStyle(style)) {
        setStyle(style === "flow-dark" ? "flow" : "flow-dark");
        return;
      }
      // Non-flow skins: flip between light/dark folio pair when possible
      if (style === "folio") setStyle("folio-dark");
      else if (style === "folio-dark") setStyle("folio");
      else setStyle("flow");
    });
  }, [run, setStyle, style]);

  const toggleLang = useCallback(() => {
    run(() => setLang(lang === "ru" ? "en" : "ru"));
  }, [lang, run, setLang]);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        placeholder={localize(lang, "Поиск страниц, серверов, агентов…", "Search pages, servers, agents…")}
      />
      <CommandList>
        <CommandEmpty>{localize(lang, "Ничего не найдено", "No results")}</CommandEmpty>

        {(recentServers.length > 0 || recentRuns.length > 0) && (
          <CommandGroup heading={localize(lang, "Недавнее", "Recent")}>
            {recentServers.map((server) => (
              <CommandItem
                key={`recent-srv-${server.id}`}
                value={`recent server ${server.name} ${server.host ?? ""}`}
                onSelect={() => {
                  pushRecentServer(server);
                  go(`/servers/${server.id}/terminal`);
                }}
              >
                <History className="mr-2 h-4 w-4 text-muted-foreground" />
                <span className="truncate">{server.name}</span>
                <CommandShortcut>{localize(lang, "Терминал", "Terminal")}</CommandShortcut>
              </CommandItem>
            ))}
            {recentRuns.map((item) => (
              <CommandItem
                key={`recent-run-${item.id}`}
                value={`recent run ${item.agentName} ${item.id}`}
                onSelect={() => go(`/agents/run/${item.id}`)}
              >
                <History className="mr-2 h-4 w-4 text-muted-foreground" />
                <span className="truncate">{item.agentName}</span>
                <CommandShortcut>#{item.id}</CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandGroup heading={localize(lang, "Навигация", "Navigation")}>
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <CommandItem
                key={item.id}
                value={`${item.labelRu} ${item.labelEn} ${item.keywords ?? ""}`}
                onSelect={() => go(item.path)}
              >
                <Icon className="mr-2 h-4 w-4" />
                {localize(lang, item.labelRu, item.labelEn)}
              </CommandItem>
            );
          })}
        </CommandGroup>

        {servers.length > 0 && (
          <CommandGroup heading={localize(lang, "Серверы", "Servers")}>
            {servers.slice(0, 40).map((server) => (
              <CommandItem
                key={`srv-${server.id}`}
                value={`server ${server.name} ${server.host} ${server.group_name}`}
                onSelect={() => {
                  pushRecentServer({ id: server.id, name: server.name, host: server.host });
                  go(`/servers/${server.id}/terminal`);
                }}
              >
                <Terminal className="mr-2 h-4 w-4 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">
                  {server.name}
                  <span className="ml-2 font-mono text-xs text-muted-foreground">{server.host}</span>
                </span>
                <CommandShortcut>{localize(lang, "Подключить", "Connect")}</CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {agents.length > 0 && (
          <CommandGroup heading={localize(lang, "Агенты", "Agents")}>
            {agents.slice(0, 40).map((agent) => (
              <CommandItem
                key={`ag-${agent.id}`}
                value={`agent ${agent.name} ${agent.goal ?? ""} ${agent.mode}`}
                onSelect={() => go(`/agents?edit=${agent.id}`)}
              >
                <Bot className="mr-2 h-4 w-4 text-muted-foreground" />
                <span className="truncate">{agent.name}</span>
                <CommandShortcut>{agent.mode}</CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandSeparator />

        <CommandGroup heading={localize(lang, "Действия", "Actions")}>
          <CommandItem
            value="assistant ask ai chat drawer"
            onSelect={() =>
              run(() => {
                onOpenAssistant?.();
              })
            }
          >
            <Sparkles className="mr-2 h-4 w-4" />
            {localize(lang, "Спросить ассистента", "Ask assistant")}
            <CommandShortcut>⌘.</CommandShortcut>
          </CommandItem>
          <CommandItem value="theme toggle dark light flow" onSelect={toggleTheme}>
            <Moon className="mr-2 h-4 w-4" />
            {localize(lang, "Переключить тему", "Toggle theme")}
          </CommandItem>
          <CommandItem value="language lang ru en" onSelect={toggleLang}>
            <Globe className="mr-2 h-4 w-4" />
            {localize(lang, "Сменить язык", "Switch language")}
            <CommandShortcut>{lang === "ru" ? "EN" : "RU"}</CommandShortcut>
          </CommandItem>
          {isFlowStyle(style) ? null : (
            <CommandItem
              value="style flow skin"
              onSelect={() => run(() => setStyle("flow"))}
            >
              <Palette className="mr-2 h-4 w-4" />
              {localize(lang, "Тема Flow", "Flow skin")}
            </CommandItem>
          )}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
