import { useEffect, useRef, useState } from "react";

/** Animated count-up toward `target`; snaps instantly under reduced motion. */
export function useCountUp(target: number, durationMs = 900): number {
  const [value, setValue] = useState(0);
  const previous = useRef(0);

  useEffect(() => {
    const from = previous.current;
    previous.current = target;
    if (from === target) {
      setValue(target);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (timestamp: number) => {
      const progress = Math.min(1, (timestamp - start) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(from + (target - from) * eased));
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    };
    raf = requestAnimationFrame(tick);
    // rAF is frozen in background tabs — always land on the target value.
    const snap = window.setTimeout(() => setValue(target), durationMs + 150);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(snap);
    };
  }, [target, durationMs]);

  return value;
}
