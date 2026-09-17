import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Play, TerminalSquare, Webhook } from "lucide-react";

import { executePluginTerminalAction, fetchPluginSurfaces } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";

function itemKey(item: Record<string, unknown>) {
  return `${String(item.plugin_id || "")}:${String(item.id || item.name || "")}`;
}

export function PluginExtensionSurfacesPanel() {
  const { toast } = useToast();
  const { lang } = useI18n();
  const surfacesQuery = useQuery({ queryKey: ["plugins", "surfaces", "extensions"], queryFn: fetchPluginSurfaces });
  const agentTools = surfacesQuery.data?.surfaces?.agent_tools ?? [];
  const terminalActions = surfacesQuery.data?.surfaces?.terminal_actions ?? [];
  const hooks = surfacesQuery.data?.surfaces?.hooks ?? [];
  const executeMutation = useMutation({
    mutationFn: ({ pluginId, actionId }: { pluginId: string; actionId: string }) => executePluginTerminalAction(pluginId, actionId),
    onSuccess: (result) => toast({ description: result.message || localize(lang, "Действие выполнено.", "Action completed.") }),
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  return (
    <SectionCard title={localize(lang, "Инструменты и действия", "Tools and actions")} description={localize(lang, "Функции, добавленные включёнными плагинами.", "Features added by enabled plugins.")} icon={<Bot className="h-4 w-4" />}>
      <QueryStateBlock loading={surfacesQuery.isLoading} error={surfacesQuery.error}>
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Bot className="h-4 w-4 text-primary" />
              {localize(lang, "Инструменты агентов", "Agent tools")}
            </div>
            {agentTools.length ? agentTools.map((tool) => (
              <div key={itemKey(tool)} className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-foreground">{String(tool.name || tool.id)}</span>
                  <Badge variant="outline">{String(tool.plugin_id)}</Badge>
                  <StatusBadge label={String((tool.tool_spec as Record<string, unknown> | undefined)?.risk || tool.risk_tier || "read")} tone="info" dot={false} />
                </div>
                {tool.description ? <p className="mt-2 text-xs leading-5 text-muted-foreground">{String(tool.description)}</p> : null}
              </div>
            )) : (
              <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
                {localize(lang, "Инструментов агентов нет.", "No plugin agent tools are enabled.")}
              </p>
            )}
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <TerminalSquare className="h-4 w-4 text-primary" />
              {localize(lang, "Действия терминала", "Terminal actions")}
            </div>
            {terminalActions.length ? terminalActions.map((action) => {
              const pluginId = String(action.plugin_id || "");
              const actionId = String(action.id || "");
              return (
                <div key={itemKey(action)} className="rounded-lg border border-border/70 bg-card px-4 py-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-foreground">{String(action.title || action.id)}</span>
                        <Badge variant="outline">{pluginId}</Badge>
                        <StatusBadge label={String(action.risk_tier || "read")} tone="info" dot={false} />
                      </div>
                      {action.description ? <p className="mt-2 text-xs leading-5 text-muted-foreground">{String(action.description)}</p> : null}
                    </div>
                    <Button
                      size="sm"
                      onClick={() => executeMutation.mutate({ pluginId, actionId })}
                      disabled={executeMutation.isPending || !pluginId || !actionId}
                    >
                      <Play className="h-4 w-4" />
                      {localize(lang, "Запустить", "Run")}
                    </Button>
                  </div>
                </div>
              );
            }) : (
              <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
                {localize(lang, "Действий терминала нет.", "No plugin terminal actions are enabled.")}
              </p>
            )}
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Webhook className="h-4 w-4 text-primary" />
              {localize(lang, "Обработчики событий", "Event hooks")}
            </div>
            {hooks.length ? hooks.map((hook) => (
              <div key={itemKey(hook)} className="rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-foreground">{String(hook.event || hook.id)}</span>
                  <Badge variant="outline">{String(hook.plugin_id)}</Badge>
                  <StatusBadge label={String(hook.risk_tier || "read")} tone="info" dot={false} />
                </div>
                {hook.description ? <p className="mt-2 text-xs leading-5 text-muted-foreground">{String(hook.description)}</p> : null}
              </div>
            )) : (
              <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
                {localize(lang, "Обработчиков событий нет.", "No plugin event hooks are enabled.")}
              </p>
            )}
          </div>
        </div>
      </QueryStateBlock>
    </SectionCard>
  );
}
