import type { NovaContextPayload } from "../ai-types";
import { useI18n } from "@/lib/i18n";

interface NovaContextCardProps {
  context?: NovaContextPayload;
}

export function NovaContextCard({ context }: NovaContextCardProps) {
  const { t } = useI18n();
  const session = context?.session;
  const recentActivity = context?.recent_activity ?? [];

  if (!session && recentActivity.length === 0) {
    return null;
  }

  const identity = [session?.user, session?.hostname].filter(Boolean).join("@");

  return (
    <div className="space-y-2 rounded-md border border-border/50 bg-card/70 px-2.5 py-2 text-[11px] text-muted-foreground">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-foreground">{t("terminal.ai.nova.context.title")}</span>
        <span className="text-[10px]">{t("terminal.ai.nova.context.description")}</span>
      </div>

      {session ? (
        <div className="space-y-1 rounded-md border border-border/40 bg-background/40 px-2 py-1.5">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-foreground/80">
            {t("terminal.ai.nova.context.session")}
          </div>
          <div className="grid gap-1 sm:grid-cols-2">
            {session.cwd ? <div><span className="text-foreground/80">{t("terminal.ai.nova.context.cwd")}: </span>{session.cwd}</div> : null}
            {identity ? <div><span className="text-foreground/80">{t("terminal.ai.nova.context.identity")}: </span>{identity}</div> : null}
            {session.shell ? <div><span className="text-foreground/80">{t("terminal.ai.nova.context.shell")}: </span>{session.shell}</div> : null}
            {session.venv ? <div><span className="text-foreground/80">{t("terminal.ai.nova.context.venv")}: </span>{session.venv}</div> : null}
            {session.python ? <div><span className="text-foreground/80">{t("terminal.ai.nova.context.python")}: </span>{session.python}</div> : null}
            {session.source ? <div><span className="text-foreground/80">{t("terminal.ai.nova.context.source")}: </span>{session.source}</div> : null}
          </div>
          {session.env_summary?.length ? (
            <div>
              <span className="text-foreground/80">{t("terminal.ai.nova.context.env")}: </span>
              {session.env_summary.join(", ")}
            </div>
          ) : null}
        </div>
      ) : null}

      {recentActivity.length ? (
        <div className="space-y-1 rounded-md border border-border/40 bg-background/40 px-2 py-1.5">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-foreground/80">
            {t("terminal.ai.nova.context.recentActivity")}
          </div>
          <div className="space-y-1">
            {recentActivity.map((item, index) => (
              <div key={`${item.command}-${item.cwd || ""}-${index}`} className="rounded border border-border/30 bg-background/30 px-1.5 py-1">
                <div className="font-mono text-foreground/90">{item.command}</div>
                <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px]">
                  {item.cwd ? <span>{t("terminal.ai.nova.context.cwd")}: {item.cwd}</span> : null}
                  {typeof item.exit_code === "number" ? <span>{t("terminal.ai.nova.context.exit")}: {item.exit_code}</span> : null}
                  {item.source ? <span>{t("terminal.ai.nova.context.source")}: {item.source}</span> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
