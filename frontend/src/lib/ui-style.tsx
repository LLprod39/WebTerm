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
export type UiStyleId =
  | "catalog"
  | "classic"
  | "pulse"
  | "signal"
  | "folio"
  | "folio-dark";

/** Map of userKey → style */
export const UI_STYLE_BY_USER_KEY = "webterm.ui-style.by-user";
/** Last applied style (FOUC) */
export const UI_STYLE_ACTIVE_KEY = "webterm.ui-style.active";
/** Legacy single-key (migrated once) */
export const UI_STYLE_LEGACY_KEY = "webterm.ui-style";

/** Product default skin for every account without a saved preference. */
export const DEFAULT_UI_STYLE: UiStyleId = "folio-dark";
export const GUEST_USER_KEY = "guest";

/** Skins that force light color-scheme (native inputs, scrollbars, form controls). */
export const LIGHT_UI_STYLES = new Set<UiStyleId>(["folio"]);

/** Folio light + dark share the same editorial paper design language. */
export function isFolioStyle(value: unknown): value is "folio" | "folio-dark" {
  return value === "folio" || value === "folio-dark";
}

const UI_STYLE_ID_SET = new Set<UiStyleId>([
  "catalog",
  "classic",
  "pulse",
  "signal",
  "folio",
  "folio-dark",
]);

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
  {
    id: "pulse",
    labelRu: "Пульс",
    labelEn: "Pulse",
    blurbRu: "Violet night ops: мягкий glass, aurora glow, Outfit + DM Sans.",
    blurbEn: "Violet night ops: soft glass, aurora glow, Outfit + DM Sans.",
    swatches: ["#0c0614", "#c084fc", "#f5f0ff", "#22d3ee"],
  },
  {
    id: "signal",
    labelRu: "Сигнал",
    labelEn: "Signal",
    blurbRu: "Жёсткий brutal ops: carbon black, amber alarm, zero radius, mono.",
    blurbEn: "Hard brutal ops: carbon black, amber alarm, zero radius, mono.",
    swatches: ["#050505", "#ff7a12", "#f2f2f0", "#ff2d55"],
  },
  {
    id: "folio",
    labelRu: "Фолио · светлая",
    labelEn: "Folio · Light",
    blurbRu: "Средне-серый desk, Inter, без белого.",
    blurbEn: "Mid-stone gray desk, Inter, no bright white.",
    swatches: ["#8a8680", "#9a4a24", "#1f1c1a", "#1f5f58"],
  },
  {
    id: "folio-dark",
    labelRu: "Фолио · тёмная",
    labelEn: "Folio · Dark",
    blurbRu: "Тёмный Folio desk, Inter + terracotta.",
    blurbEn: "Dark Folio desk, Inter + terracotta.",
    swatches: ["#161310", "#e07a3d", "#f3ebe2", "#2dd4bf"],
  },
];

export function isUiStyleId(value: unknown): value is UiStyleId {
  return typeof value === "string" && UI_STYLE_ID_SET.has(value as UiStyleId);
}

/** Map removed experimental ids to a safe current style. */
function normalizeStyleId(value: unknown): UiStyleId | null {
  if (isUiStyleId(value)) return value;
  // Removed experiments → Folio dark default
  if (value === "nocturne" || value === "haze") return "folio-dark";
  return null;
}

function readByUserMap(): Record<string, UiStyleId> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(UI_STYLE_BY_USER_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const out: Record<string, UiStyleId> = {};
    for (const [k, v] of Object.entries(parsed)) {
      const normalized = normalizeStyleId(v);
      if (normalized) out[k] = normalized;
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
    const normalized = normalizeStyleId(legacy);
    if (!normalized) return;
    const map = readByUserMap();
    if (!map[GUEST_USER_KEY]) {
      map[GUEST_USER_KEY] = normalized;
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
  // Only light Folio uses light color-scheme; Folio dark and all other skins stay dark.
  document.documentElement.style.colorScheme = LIGHT_UI_STYLES.has(style) ? "light" : "dark";
}

export function readActiveUiStyle(): UiStyleId {
  if (typeof window === "undefined") return DEFAULT_UI_STYLE;
  try {
    const active = normalizeStyleId(window.localStorage.getItem(UI_STYLE_ACTIVE_KEY));
    if (active) return active;
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
