import { useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

export type TerminalMood = "lost" | "offline" | "locked";

type TerminalMascotProps = {
  mood: TerminalMood;
  className?: string;
};

const TEARS = ["0", "1", "~", "#", "x"] as const;

export function TerminalMascot({ mood, className }: TerminalMascotProps) {
  const reduceMotion = useReducedMotion();
  const accent =
    mood === "offline" ? "text-warning" : mood === "locked" ? "text-destructive" : "text-primary";

  return (
    <div
      aria-hidden
      data-ui-slot="error-mascot"
      data-mood={mood}
      className={cn("relative select-none", className)}
    >
      <div
        className={cn(
          "relative flex h-36 w-36 flex-col overflow-hidden rounded-sm border-2 border-border bg-card shadow-sm sm:h-44 sm:w-44",
          mood === "offline" && "border-warning/50",
          mood === "locked" && "border-destructive/40",
        )}
      >
        <div className="flex h-6 items-center gap-1.5 border-b border-border bg-muted/40 px-2">
          <span className="h-1.5 w-1.5 rounded-full bg-destructive/80" />
          <span className="h-1.5 w-1.5 rounded-full bg-warning/80" />
          <span className="h-1.5 w-1.5 rounded-full bg-primary/80" />
          <span className="ml-auto font-mono text-[9px] tabular-nums text-muted-foreground">tty</span>
        </div>

        <div className="relative flex flex-1 flex-col items-center justify-center gap-3 bg-background px-3">
          {mood === "offline" ? (
            <div className="pointer-events-none absolute inset-0 opacity-30">
              {Array.from({ length: 8 }).map((_, row) => (
                <div
                  key={row}
                  className={cn("h-[12.5%] w-full border-b border-warning/20", !reduceMotion && "animate-pulse")}
                  style={{ animationDelay: `${row * 80}ms` }}
                />
              ))}
            </div>
          ) : null}

          <div className="relative z-[1] flex items-end gap-6">
            {mood === "locked" ? (
              <>
                <span className={cn("font-mono text-2xl font-bold leading-none", accent)}>x</span>
                <span className={cn("font-mono text-2xl font-bold leading-none", accent)}>x</span>
              </>
            ) : (
              <>
                <span
                  className={cn(
                    "block h-2.5 w-5 rounded-full border-2 border-foreground/80",
                    mood === "lost" && "rotate-[-12deg] rounded-b-none border-b-0",
                    mood === "offline" && "border-warning/80 opacity-70",
                  )}
                />
                <span
                  className={cn(
                    "block h-2.5 w-5 rounded-full border-2 border-foreground/80",
                    mood === "lost" && "rotate-[12deg] rounded-b-none border-b-0",
                    mood === "offline" && "border-warning/80 opacity-70",
                  )}
                />
              </>
            )}
          </div>

          <div className="relative z-[1] flex items-center gap-0.5 font-mono text-lg leading-none">
            {mood === "locked" ? (
              <span className={cn("font-semibold tracking-tight", accent)}>[#]</span>
            ) : mood === "offline" ? (
              <span className={cn("font-semibold", accent)}>{"~/_"}</span>
            ) : (
              <>
                <span className="text-foreground/90">&gt;</span>
                <span className={cn("inline-block h-4 w-2.5 bg-foreground/90", !reduceMotion && "animate-pulse")} />
              </>
            )}
          </div>

          {!reduceMotion && mood !== "locked" ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-2 flex justify-center gap-8">
              {TEARS.slice(0, mood === "offline" ? 4 : 3).map((glyph, index) => (
                <span
                  key={`${glyph}-${index}`}
                  className={cn("error-tear font-mono text-[10px]", accent)}
                  style={{ animationDelay: `${index * 0.45}s` }}
                >
                  {glyph}
                </span>
              ))}
            </div>
          ) : null}

          {mood === "locked" ? (
            <span className="relative z-[1] font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              denied
            </span>
          ) : null}
        </div>

        {!reduceMotion ? <div className="error-scan pointer-events-none absolute inset-x-0 top-6 h-px bg-foreground/10" /> : null}
      </div>
    </div>
  );
}
