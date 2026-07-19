import { type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useLocation } from "react-router-dom";

const ease = [0.22, 1, 0.36, 1] as const;

/**
 * Subtle route enter animation for the main content area.
 * Short fade + slight rise — noticeable if you look, never loud.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  // Key by pathname only so query changes don't re-animate.
  const routeKey = location.pathname;

  if (reduceMotion) {
    return <div className="min-h-0 min-w-0 flex-1">{children}</div>;
  }

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={routeKey}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.2, ease }}
        className="min-h-0 min-w-0 flex-1"
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

/**
 * Soft panel enter for in-page tab content (servers / groups / rules…).
 * Use with a changing `panelKey` (tab id).
 */
export function PanelTransition({
  panelKey,
  children,
  className,
}: {
  panelKey: string;
  children: ReactNode;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={panelKey}
        initial={{ opacity: 0, y: 8, filter: "blur(2px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        exit={{ opacity: 0, y: -4, filter: "blur(1px)" }}
        transition={{ duration: 0.18, ease }}
        className={className}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
