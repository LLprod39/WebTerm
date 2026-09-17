export const motionTokens = {
  duration: {
    instant: 0.08,
    fast: 0.12,
    standard: 0.18,
    overlay: 0.22,
    slow: 0.28,
  },
  ease: {
    standard: [0.2, 0, 0, 1] as const,
    enter: [0.16, 1, 0.3, 1] as const,
    exit: [0.4, 0, 1, 1] as const,
  },
  distance: {
    subtle: 4,
    panel: 8,
  },
} as const;
