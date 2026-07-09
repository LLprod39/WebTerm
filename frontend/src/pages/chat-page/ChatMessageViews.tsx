import { Link } from "react-router-dom";
import { AlertTriangle, Bot, ExternalLink, Loader2, ShieldCheck, User, XCircle } from "lucide-react";

import type { AssistantAction, AssistantChatMessage } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  ActionIcon,
  ActionInputPreview,
  ActionResultPreview,
  actionRiskLabel,
  actionStatusLabel,
  actionTone,
  formatDateTime,
  statusTone,
} from "./chatHelpers";


function ActionCard({
  action,
  isWorking,
  onConfirm,
  onCancel,
}: {
  action: AssistantAction;
  isWorking: boolean;
  onConfirm: (actionId: number) => void;
  onCancel: (actionId: number) => void;
}) {
  const { lang } = useI18n();
  const canConfirm = action.status === "requires_confirmation";
  const canCancel = action.status === "requires_confirmation" || action.status === "proposed";

  return (
    <div className={cn("rounded-lg border bg-card/55 shadow-sm", actionTone(action))}>
      <div className="flex min-w-0 items-start gap-3 px-3 py-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-background/65">
          <ActionIcon action={action} />
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <h3 className="truncate text-sm font-semibold text-foreground">{action.title || action.action_type}</h3>
                <span className="truncate rounded-md border border-border/60 bg-background/45 px-2 py-0.5 font-mono text-2xs text-muted-foreground">
                  {action.action_type}
                </span>
              </div>
              {action.description ? (
                <p className="mt-1 text-sm leading-5 text-muted-foreground">{action.description}</p>
              ) : null}
            </div>
            <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
              <Badge variant="outline" className={cn("rounded-md px-2 py-0.5", statusTone(action.status))}>
                {actionStatusLabel(action.status, lang)}
              </Badge>
              <Badge variant="secondary" className="rounded-md px-2 py-0.5">
                {actionRiskLabel(action.risk, lang)}
              </Badge>
            </div>
          </div>

          {canConfirm ? (
            <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
              {localize(lang, "Перед выполнением нужно подтверждение оператора.", "Operator confirmation is required before execution.")}
            </div>
          ) : null}

          <ActionInputPreview action={action} />

          {action.status === "completed" ? <ActionResultPreview action={action} /> : null}

          {action.error ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0 break-words">{action.error}</span>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            {canConfirm ? (
              <Button size="sm" onClick={() => onConfirm(action.id)} disabled={isWorking}>
                {isWorking ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                {localize(lang, "Подтвердить", "Confirm")}
              </Button>
            ) : null}
            {canCancel ? (
              <Button size="sm" variant="outline" onClick={() => onCancel(action.id)} disabled={isWorking}>
                <XCircle className="h-4 w-4" />
                {localize(lang, "Отменить", "Cancel")}
              </Button>
            ) : null}
            {action.target_url && action.status === "completed" ? (
              <Button size="sm" variant="secondary" asChild>
                <Link to={action.target_url}>
                  <ExternalLink className="h-4 w-4" />
                  {localize(lang, "Открыть", "Open")}
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export function MessageBubble({
  message,
  actionWorkingId,
  onConfirmAction,
  onCancelAction,
}: {
  message: AssistantChatMessage;
  actionWorkingId: number | null;
  onConfirmAction: (actionId: number) => void;
  onCancelAction: (actionId: number) => void;
}) {
  const { lang } = useI18n();
  const isUser = message.role === "user";
  const actions = message.metadata.actions || [];
  const Icon = isUser ? User : Bot;

  if (isUser) {
    return (
      <div className="flex justify-end gap-3">
        <div className="min-w-0 max-w-[min(720px,88%)]">
          <div className="rounded-lg bg-primary px-4 py-3 text-sm font-medium leading-6 text-primary-foreground shadow-sm">
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
          <div className="mt-1 text-right text-2xs text-muted-foreground">{formatDateTime(message.created_at, lang)}</div>
        </div>
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/75 bg-card/80 text-muted-foreground">
          <Icon className="h-4 w-4" />
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-2xs text-muted-foreground">
          <span className="font-semibold text-foreground">WebTermAI</span>
          <span>{formatDateTime(message.created_at, lang)}</span>
          {actions.length ? (
            <span className="rounded-md border border-border/60 bg-secondary/45 px-1.5 py-0.5">
              {actions.length} {localize(lang, "действ.", "actions")}
            </span>
          ) : null}
        </div>
        {message.content ? (
          <div className="max-w-[min(920px,100%)] rounded-lg border border-border/80 bg-card/75 px-4 py-3 text-sm leading-6 text-foreground shadow-sm">
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
        ) : null}
        {actions.length ? (
          <div className="max-w-[min(920px,100%)] space-y-2">
            {actions.map((action) => (
              <ActionCard
                key={action.id}
                action={action}
                isWorking={actionWorkingId === action.id}
                onConfirm={onConfirmAction}
                onCancel={onCancelAction}
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

