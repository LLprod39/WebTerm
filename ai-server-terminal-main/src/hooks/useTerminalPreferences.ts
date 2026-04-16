/**
 * Hook to load, cache, and persist terminal appearance preferences.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { TerminalPrefs } from "@/api/terminal-preferences";
import {
  fetchTerminalPreferences,
  updateTerminalPreferences,
} from "@/api/terminal-preferences";

const DEFAULT_PREFS: TerminalPrefs = {
  theme_name: "one_dark",
  theme_colors: {},
  font_size: 14,
  font_family: "JetBrains Mono",
  line_height: 1.4,
  cursor_style: "block",
  cursor_blink: true,
  scrollback: 5000,
  intercept_editors: true,
};

export function useTerminalPreferences() {
  const [prefs, setPrefs] = useState<TerminalPrefs>(DEFAULT_PREFS);
  const [loading, setLoading] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchTerminalPreferences()
      .then((data) => {
        if (!cancelled) setPrefs(data);
      })
      .catch(() => {
        /* use defaults */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const update = useCallback((patch: Partial<TerminalPrefs>) => {
    setPrefs((prev) => ({ ...prev, ...patch }));
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateTerminalPreferences(patch).catch(() => {
        /* silent — prefs are best-effort */
      });
    }, 600);
  }, []);

  return { prefs, loading, update } as const;
}
