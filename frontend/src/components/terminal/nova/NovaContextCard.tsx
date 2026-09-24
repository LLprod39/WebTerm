import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import type { NovaContextPayload } from "../ai-types";

interface NovaContextCardProps {
  context?: NovaContextPayload;
}

/**
 * Collapsed-by-default session strip. Full SESSION / recent activity
 * only appears on expand so the timeline stays scannable.
 */
export function NovaContextCard({ context }: NovaContextCardProps) {
  const { t, lang } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const session = context?.session;
  const recentActivity = context?.recent_activity ?? [];

  if (!session && recentActivity.length === 0) {
    return null;
  }

  const identity = [session?.user, session?.hostname].filter(Boolean).join("@");
  const summaryParts = [
    identity || null,
    session?.cwd || null,
    recentActivity.length
      ? localize(
          lang,
          `${recentActivity.length} команд`,
          `${recentActivity.length} cmds`,
        )
      : null,
  ].filter(Boolean);

  return (
    <div className="text-xs text-muted-foreground">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        className="group flex w-full min-w-0 items-center gap-1.5 rounded-sm px-1 py-0.5 text-left transition-colors hover:bg-secondary/30 hover:text-foreground"
      >
        <ChevronDown
          className={cn(
            "h-3 w-3 shrink-0 opacity-50 transition-transform",
            expanded && "rotate-180",
          )}
          aria-hidden="true"
        />
        <span className="shrink-0 font-medium text-foreground/85">
          {t("terminal.ai.nova.context.title")}
        </span>
        {summaryParts.length ? (
          <>
            <span className="shrink-0 opacity-40" aria-hidden="true">
              ·
            </span>
            <span className="min-w-0 flex-1 truncate opacity-75">
              {summaryParts.join(" · ")}
            </span>
          </>
        ) : (
          <span className="min-w-0 flex-1 truncate opacity-60">
            {t("terminal.ai.nova.context.description")}
          </span>
        )}
      </button>

      {expanded ? (
        <div className="mt-1 space-y-2 border-t border-border/40 pt-1.5 pl-4">
          {session ? (
            <div className="space-y-0.5">
              <div className="text-[11px] font-medium uppercase tracking-wide text-foreground/70">
                {t("terminal.ai.nova.context.session")}
              </div>
              <dl className="grid gap-0.5 sm:grid-cols-2">
                {session.cwd ? (
                  <div>
                    <dt className="inline text-foreground/70">{t("terminal.ai.nova.context.cwd")}: </dt>
                    <dd className="inline font-mono text-foreground/90">{session.cwd}</dd>
                  </div>
                ) : null}
                {identity ? (
                  <div>
                    <dt className="inline text-foreground/70">{t("terminal.ai.nova.context.identity")}: </dt>
                    <dd className="inline">{identity}</dd>
                  </div>
                ) : null}
                {session.shell ? (
                  <div>
                    <dt className="inline text-foreground/70">{t("terminal.ai.nova.context.shell")}: </dt>
                    <dd className="inline font-mono">{session.shell}</dd>
                  </div>
                ) : null}
                {session.venv ? (
                  <div>
                    <dt className="inline text-foreground/70">{t("terminal.ai.nova.context.venv")}: </dt>
                    <dd className="inline font-mono">{session.venv}</dd>
                  </div>
                ) : null}
                {session.python ? (
                  <div>
                    <dt className="inline text-foreground/70">{t("terminal.ai.nova.context.python")}: </dt>
                    <dd className="inline font-mono">{session.python}</dd>
                  </div>
                ) : null}
                {session.source ? (
                  <div>
                    <dt className="inline text-foreground/70">{t("terminal.ai.nova.context.source")}: </dt>
                    <dd className="inline">{session.source}</dd>
                  </div>
                ) : null}
              </dl>
              {session.env_summary?.length ? (
                <div>
                  <span className="text-foreground/70">{t("terminal.ai.nova.context.env")}: </span>
                  {session.env_summary.join(", ")}
                </div>
              ) : null}
            </div>
          ) : null}

          {recentActivity.length ? (
            <div className="space-y-0.5">
              <div className="text-[11px] font-medium uppercase tracking-wide text-foreground/70">
                {t("terminal.ai.nova.context.recentActivity")}
              </div>
              <ul className="divide-y divide-border/30">
                {recentActivity.map((item, index) => (
                  <li
                    key={`${item.command}-${item.cwd || ""}-${index}`}
                    className="py-1 first:pt-0 last:pb-0"
                  >
                    {item.summary ? (
                      <div className="text-foreground/90">{item.summary}</div>
                    ) : null}
                    <div
                      className={
                        item.summary
                          ? "mt-0.5 font-mono text-[11px] text-muted-foreground"
                          : "font-mono text-foreground/90"
                      }
                    >
                      {item.command}
                    </div>
                    {!item.summary ? (
                      <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] opacity-80">
                        {item.cwd ? (
                          <span>
                            {t("terminal.ai.nova.context.cwd")}: {item.cwd}
                          </span>
                        ) : null}
                        {typeof item.exit_code === "number" ? (
                          <span>
                            {t("terminal.ai.nova.context.exit")}: {item.exit_code}
                          </span>
                        ) : null}
                        {item.source ? (
                          <span>
                            {t("terminal.ai.nova.context.source")}: {item.source}
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
