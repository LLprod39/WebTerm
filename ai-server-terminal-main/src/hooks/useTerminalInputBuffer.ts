/**
 * Hook tracking the current terminal input line for autocomplete overlay.
 *
 * Intercepts Tab / arrow keys to navigate suggestions.
 * Returns `interceptInput` which wraps onData — it returns `true` when
 * the keystroke was consumed by the overlay (so it must NOT be forwarded
 * to the pty), or `false` when the keystroke is normal terminal input.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchCommandSuggestions } from "@/api/terminal-preferences";

interface UseBufOpts {
  serverId: number | null;
  enabled: boolean;
}

export interface InputBufResult {
  buffer: string;
  suggestions: string[];
  selectedIdx: number;
  /** Call this BEFORE sending data to pty. Returns the text to type if
   *  the key was consumed (Tab accept), or null for normal pass-through. */
  interceptInput: (data: string) => string | null;
  dismiss: () => void;
}

export function useTerminalInputBuffer({ serverId, enabled }: UseBufOpts): InputBufResult {
  const [buffer, setBuffer] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bufRef = useRef(buffer);
  const sugRef = useRef(suggestions);
  const idxRef = useRef(selectedIdx);
  bufRef.current = buffer;
  sugRef.current = suggestions;
  idxRef.current = selectedIdx;

  const dismiss = useCallback(() => {
    setBuffer("");
    setSuggestions([]);
    setSelectedIdx(0);
  }, []);

  const interceptInput = useCallback(
    (data: string): string | null => {
      if (!enabled) return null;

      // Tab → accept selected suggestion
      if (data === "\t") {
        const sug = sugRef.current;
        if (sug.length > 0) {
          const cmd = sug[idxRef.current] ?? sug[0];
          const cur = bufRef.current;
          const suffix = cmd.startsWith(cur) ? cmd.slice(cur.length) : cmd;
          dismiss();
          return suffix;
        }
        return null; // no suggestions, let Tab go to pty
      }

      // Arrow up / down when overlay is visible
      if (data === "\x1b[A" && sugRef.current.length > 0) {
        setSelectedIdx((i) => (i <= 0 ? sugRef.current.length - 1 : i - 1));
        return ""; // consumed, don't send to pty
      }
      if (data === "\x1b[B" && sugRef.current.length > 0) {
        setSelectedIdx((i) => (i >= sugRef.current.length - 1 ? 0 : i + 1));
        return ""; // consumed
      }

      // Escape → dismiss overlay
      if (data === "\x1b" && sugRef.current.length > 0) {
        dismiss();
        return ""; // consumed
      }

      // Enter or Ctrl-C → reset
      if (data === "\r" || data === "\x03") {
        dismiss();
        return null; // pass through
      }

      // Backspace
      if (data === "\x7f" || data === "\b") {
        setBuffer((b) => b.slice(0, -1));
        return null;
      }

      // Ignore multi-byte escape sequences (except arrows handled above)
      if (data.length > 1 && data[0] === "\x1b") return null;
      // Ignore control chars
      if (data.charCodeAt(0) < 32) return null;

      // Normal printable character
      setBuffer((b) => b + data);
      return null;
    },
    [enabled, dismiss],
  );

  // Fetch suggestions when buffer changes
  useEffect(() => {
    if (!enabled || !serverId || buffer.length < 2) {
      setSuggestions([]);
      return;
    }
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      fetchCommandSuggestions(serverId, buffer)
        .then((items) => {
          setSuggestions(items);
          setSelectedIdx(0);
        })
        .catch(() => setSuggestions([]));
    }, 200);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [buffer, serverId, enabled]);

  return { buffer, suggestions, selectedIdx, interceptInput, dismiss };
}
