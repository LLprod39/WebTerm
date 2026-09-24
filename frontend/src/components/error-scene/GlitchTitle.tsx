import { useEffect, useMemo, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

const GLITCH_CHARS = "!<>-_\\/[]{}—=+*^?#________";

type GlitchTitleProps = {
  text: string;
  className?: string;
  as?: "h1" | "p" | "span";
};

function scrambleChar(seed: number): string {
  return GLITCH_CHARS[Math.abs(seed) % GLITCH_CHARS.length] ?? "#";
}

export function GlitchTitle({ text, className, as: Tag = "h1" }: GlitchTitleProps) {
  const reduceMotion = useReducedMotion();
  const chars = useMemo(() => Array.from(text), [text]);
  const [revealed, setRevealed] = useState(() => (reduceMotion ? chars.length : 0));
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (reduceMotion) {
      setRevealed(chars.length);
      return;
    }

    setRevealed(0);
    setTick(0);
    let index = 0;
    const interval = window.setInterval(() => {
      index += 1;
      setRevealed(Math.min(index, chars.length));
      setTick((value) => value + 1);
      if (index >= chars.length + 6) {
        window.clearInterval(interval);
      }
    }, 42);

    return () => window.clearInterval(interval);
  }, [chars, reduceMotion, text]);

  return (
    <Tag className={cn("font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl", className)}>
      <span className="sr-only">{text}</span>
      <span aria-hidden className="inline-flex flex-wrap">
        {chars.map((char, index) => {
          const isRevealed = index < revealed;
          const showGlitch = !reduceMotion && !isRevealed && index < revealed + 3;
          const display = isRevealed
            ? char
            : showGlitch
              ? scrambleChar(tick * 17 + index * 31)
              : "\u00A0";

          return (
            <span
              key={`${char}-${index}`}
              className={cn(
                "inline-block min-w-[0.55ch] whitespace-pre transition-opacity duration-150",
                isRevealed ? "opacity-100" : "opacity-70 text-muted-foreground",
                showGlitch && "text-primary",
              )}
            >
              {display === " " ? "\u00A0" : display}
            </span>
          );
        })}
      </span>
    </Tag>
  );
}
