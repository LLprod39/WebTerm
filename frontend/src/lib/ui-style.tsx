import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchAuthSession } from "@/api/auth";

/** Visual product skins. Stored per user in this browser. */
export type UiStyleId = "catalog" | "classic";

/** Map of userKey → style */
export const UI_STYLE_BY_USER_KEY = "webterm.ui-style.by-user";
/** Last applied style (FOUC) */
export const UI_STYLE_ACTIVE_KEY = "webterm.ui-style.active";
/** Legacy single-key (migrated once) */
export const UI_STYLE_LEGACY_KEY = "webterm.ui-style";

export const DEFAULT_UI_STYLE: UiStyleId = "catalog";
export const GUEST_USER_KEY = "guest";

export const UI_STYLE_OPTIONS: Array<{
  id: UiStyleId;
  labelRu: string;
  labelEn: string;
  blurbRu: string;
  blurbEn: string;
  swatches: string[];
}> = [
  {
    id: "catalog",
    labelRu: "Каталог",
    labelEn: "Catalog",
    blurbRu: "Acid lime, mono UI, острые углы, hard shadows.",
    blurbEn: "Acid lime, mono UI, sharp edges, hard shadows.",
    swatches: ["#09090b", "#c8f542", "#f4f1ea", "#7ec8ff"],
  },
  {
    id: "classic",
    labelRu: "Классика",
    labelEn: "Classic",
    blurbRu: "Teal console, Inter, мягкие тени — прежний вид.",
    blurbEn: "Teal console, Inter, soft elevation — previous look.",
    swatches: ["#08111f", "#22c5b0", "#e8f0f6", "#9b87f5"],
  },
];

export function isUiStyleId(value: unknown): value is UiStyleId {
  return value === "catalog" || value === "classic";
}

function readByUserMap(): Record<string, UiStyleId> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(UI_STYLE_BY_USER_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const out: Record<string, UiStyleId> = {};
    for (const [k, v] of Object.entries(parsed)) {
      if (isUiStyleId(v)) out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}

function writeByUserMap(map: Record<string, UiStyleId>) {
  try {
    window.localStorage.setItem(UI_STYLE_BY_USER_KEY, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

function migrateLegacyIfNeeded() {
  if (typeof window === "undefined") return;
  try {
    const legacy = window.localStorage.getItem(UI_STYLE_LEGACY_KEY);
    if (!isUiStyleId(legacy)) return;
    const map = readByUserMap();
    if (!map[GUEST_USER_KEY]) {
      map[GUEST_USER_KEY] = legacy;
      writeByUserMap(map);
    }
    window.localStorage.removeItem(UI_STYLE_LEGACY_KEY);
  } catch {
    /* ignore */
  }
}

export function applyUiStyleToDocument(style: UiStyleId) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-ui-style", style);
  document.documentElement.style.colorScheme = "dark";
}

export function readActiveUiStyle(): UiStyleId {
  if (typeof window === "undefined") return DEFAULT_UI_STYLE;
  try {
    const active = window.localStorage.getItem(UI_STYLE_ACTIVE_KEY);
    if (isUiStyleId(active)) return active;
  } catch {
    /* ignore */
  }
  migrateLegacyIfNeeded();
  return DEFAULT_UI_STYLE;
}

function readStyleForUserKey(userKey: string): UiStyleId {
  migrateLegacyIfNeeded();
  const map = readByUserMap();
  if (isUiStyleId(map[userKey])) return map[userKey];
  // New account: default — do not inherit another user's style
  if (userKey !== GUEST_USER_KEY) return DEFAULT_UI_STYLE;
  return readActiveUiStyle();
}

function persistStyleForUserKey(userKey: string, style: UiStyleId) {
  const map = readByUserMap();
  map[userKey] = style;
  writeByUserMap(map);
  try {
    window.localStorage.setItem(UI_STYLE_ACTIVE_KEY, style);
  } catch {
    /* ignore */
  }
  applyUiStyleToDocument(style);
}

type UiStyleContextValue = {
  style: UiStyleId;
  /** Storage key for the bound account (user id or guest). */
  userKey: string;
  setStyle: (next: UiStyleId) => void;
};

const UiStyleContext = createContext<UiStyleContextValue | null>(null);

/**
 * Binds UI style to the authenticated user.
 * Preference is per-user (localStorage map); other accounts keep their own choice.
 * Must be rendered inside QueryClientProvider.
 */
export function UiStyleProvider({ children }: { children: ReactNode }) {
  const { data: session } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  const userKey = useMemo(() => {
    if (!session?.authenticated || !session.user) return GUEST_USER_KEY;
    if (session.user.id != null) return `id:${session.user.id}`;
    if (session.user.username) return `name:${session.user.username}`;
    return GUEST_USER_KEY;
  }, [session?.authenticated, session?.user]);

  const [style, setStyleState] = useState<UiStyleId>(() => {
    const initial = readActiveUiStyle();
    applyUiStyleToDocument(initial);
    return initial;
  });
  const [boundKey, setBoundKey] = useState<string>(GUEST_USER_KEY);

  useEffect(() => {
    const resolved = readStyleForUserKey(userKey);
    setBoundKey(userKey);
    setStyleState(resolved);
    applyUiStyleToDocument(resolved);
    try {
      window.localStorage.setItem(UI_STYLE_ACTIVE_KEY, resolved);
    } catch {
      /* ignore */
    }
  }, [userKey]);

  useEffect(() => {
    applyUiStyleToDocument(style);
  }, [style]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== UI_STYLE_BY_USER_KEY && event.key !== UI_STYLE_ACTIVE_KEY) return;
      const next = readStyleForUserKey(boundKey);
      setStyleState(next);
      applyUiStyleToDocument(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [boundKey]);

  const setStyle = useCallback(
    (next: UiStyleId) => {
      setStyleState(next);
      persistStyleForUserKey(boundKey, next);
    },
    [boundKey],
  );

  const value = useMemo(
    () => ({ style, userKey: boundKey, setStyle }),
    [style, boundKey, setStyle],
  );

  return <UiStyleContext.Provider value={value}>{children}</UiStyleContext.Provider>;
}

export function useUiStyle(): UiStyleContextValue {
  const ctx = useContext(UiStyleContext);
  if (!ctx) {
    throw new Error("useUiStyle must be used within UiStyleProvider");
  }
  return ctx;
}
