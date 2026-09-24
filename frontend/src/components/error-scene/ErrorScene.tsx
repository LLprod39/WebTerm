import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { GlitchTitle } from "./GlitchTitle";
import { TerminalMascot, type TerminalMood } from "./TerminalMascot";

type ErrorSceneProps = {
  code: string;
  title: string;
  description: string;
  mood: TerminalMood;
  actions?: ReactNode;
  meta?: ReactNode;
  kicker?: string;
  fullBleed?: boolean;
  role?: "alert" | undefined;
  className?: string;
};

export function ErrorScene({
  code,
  title,
  description,
  mood,
  actions,
  meta,
  kicker,
  fullBleed = true,
  role,
  className,
}: ErrorSceneProps) {
  const Wrapper = fullBleed ? "main" : "div";

  return (
    <Wrapper
      role={role}
      data-ui-slot="error-scene"
      data-page-kind={fullBleed ? "utility" : "in-shell"}
      className={cn(
        "flex items-center justify-center bg-background px-6",
        fullBleed ? "min-h-screen py-16" : "min-h-full py-12",
        className,
      )}
    >
      <div
        data-ui-slot="error-scene-content"
        className="flex w-full max-w-3xl flex-col items-center gap-8 sm:flex-row sm:items-center sm:gap-12"
      >
        <TerminalMascot mood={mood} className="shrink-0" />

        <div className="w-full min-w-0 text-center sm:text-left">
          {kicker ? (
            <>
              <p className="type-label text-primary">{kicker}</p>
              <p className="mt-2 font-mono text-sm tabular-nums text-muted-foreground">{code}</p>
            </>
          ) : (
            <p className="font-mono text-5xl font-semibold tabular-nums leading-none text-foreground sm:text-6xl">
              {code}
            </p>
          )}

          <GlitchTitle text={title} className="mt-3" />

          <p className="mx-auto mt-3 max-w-md type-body text-muted-foreground sm:mx-0">{description}</p>

          {meta ? <div className="mt-4 flex justify-center sm:justify-start">{meta}</div> : null}

          {actions ? (
            <div className="mt-8 flex flex-wrap items-center justify-center gap-2 sm:justify-start">{actions}</div>
          ) : null}
        </div>
      </div>
    </Wrapper>
  );
}
