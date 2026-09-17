export const CHAT_EASE = [0.22, 1, 0.36, 1] as const;

export const CHAT_MOTION = {
  quick: { duration: 0.12, ease: CHAT_EASE },
  status: { duration: 0.17, ease: CHAT_EASE },
  enter: { duration: 0.22, ease: CHAT_EASE },
  layout: { type: "spring", stiffness: 420, damping: 38, mass: 0.8 } as const,
} as const;

export const chatEnter = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -2 },
} as const;
