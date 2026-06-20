import { Pencil, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AgentConfig } from "@/lib/api";
import { localize } from "@/lib/i18n";

import { sudoOption, toolLabel, visibleAllowedTools } from "./agentConfigOptions";

type AgentConfigCardProps = {
  agent: AgentConfig;
  lang: "ru" | "en";
  onEdit: (agent: AgentConfig) => void;
  onDelete: (agent: AgentConfig) => void;
};

export function AgentConfigCard({ agent, lang, onEdit, onDelete }: AgentConfigCardProps) {
  const visibleTools = visibleAllowedTools(agent.allowed_tools) || [];
  const sudo = sudoOption(agent.sudo_policy);

  return (
    <div className="group overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all duration-150 hover:shadow-md">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-lg font-semibold text-primary">
              {agent.icon || "B"}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">{agent.name}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {agent.description || localize(lang, "Описание не заполнено", "No description")}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {agent.is_owner ? (
                  <Badge variant="secondary" className="text-[10px]">
                    {localize(lang, "Мой", "Mine")}
                  </Badge>
                ) : null}
                {!agent.is_owner && agent.owner_username ? (
                  <Badge variant="outline" className="text-[10px]">
                    {localize(lang, "Владелец", "Owner")}: {agent.owner_username}
                  </Badge>
                ) : null}
                {agent.is_shared ? (
                  <Badge variant="outline" className="text-[10px]">
                    {localize(lang, "Общий", "Shared")}
                  </Badge>
                ) : null}
                {agent.can_edit === false ? (
                  <Badge variant="outline" className="text-[10px]">
                    {localize(lang, "Только чтение", "Read only")}
                  </Badge>
                ) : null}
                <Badge variant="outline" className="text-[10px]">
                  sudo: {localize(lang, sudo.labelRu, sudo.labelEn)}
                </Badge>
              </div>
            </div>
          </div>
          <div className="flex shrink-0 gap-1">
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 rounded-lg"
              onClick={() => onEdit(agent)}
              aria-label={
                agent.can_edit === false
                  ? localize(lang, `Открыть агента ${agent.name}`, `View agent ${agent.name}`)
                  : localize(lang, `Изменить агента ${agent.name}`, `Edit agent ${agent.name}`)
              }
              title={agent.can_edit === false ? localize(lang, "Открыть агента", "View agent") : localize(lang, "Изменить агента", "Edit agent")}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            {agent.can_edit !== false ? (
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 rounded-lg text-destructive hover:text-destructive"
                onClick={() => onDelete(agent)}
                aria-label={localize(lang, `Удалить агента ${agent.name}`, `Delete agent ${agent.name}`)}
                title={localize(lang, "Удалить агента", "Delete agent")}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      <div className="space-y-2.5 border-t border-border/50 bg-secondary/10 px-4 py-3">
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            {agent.model}
          </span>
          <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {localize(lang, `${agent.max_iterations} итер.`, `${agent.max_iterations} iter`)}
          </span>
          {agent.mcp_servers?.length ? (
            <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {agent.mcp_servers.length} MCP
            </span>
          ) : null}
          {agent.skill_slugs?.length ? (
            <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {localize(lang, `${agent.skill_slugs.length} skills`, `${agent.skill_slugs.length} skills`)}
            </span>
          ) : null}
          {agent.server_scope?.length ? (
            <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {localize(lang, `${agent.server_scope.length} серверов`, `${agent.server_scope.length} scoped`)}
            </span>
          ) : null}
        </div>
        {visibleTools.length ? (
          <p className="text-[11px] text-muted-foreground/70">
            {visibleTools.slice(0, 4).map((item) => toolLabel(item, lang)).join(", ")}
            {visibleTools.length > 4 ? ` +${visibleTools.length - 4}` : ""}
          </p>
        ) : null}
        {agent.skill_errors?.length ? (
          <div className="rounded-lg border border-amber-500/25 bg-amber-500/8 px-2.5 py-1.5">
            {agent.skill_errors.slice(0, 1).map((error) => (
              <p key={error} className="text-[11px] text-amber-300">
                {error}
              </p>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
