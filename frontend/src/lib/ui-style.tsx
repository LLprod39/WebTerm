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
  | "enterprise-light"
  | "enterprise-dark"
  | "catalog"
  | "classic"
  | "pulse"
  | "signal"
  | "folio"
  | "folio-dark"
  | "flow"
  | "flow-dark"
  | "ashita";

/** Map of userKey → style */
export const UI_STYLE_BY_USER_KEY = "webterm.ui-style.by-user";
/** Last applied style (FOUC) */
export const UI_STYLE_ACTIVE_KEY = "webterm.ui-style.active";
/** Legacy single-key (migrated once) */
export const UI_STYLE_LEGACY_KEY = "webterm.ui-style";

/** Product default skin for every account without a saved preference. */
export const DEFAULT_UI_STYLE: UiStyleId = "flow-dark";
export const GUEST_USER_KEY = "guest";

/** Skins that force light color-scheme (native inputs, scrollbars, form controls). */
export const LIGHT_UI_STYLES = new Set<UiStyleId>(["enterprise-light", "folio", "flow"]);
const EXPERIMENTAL_UI_STYLES = new Set<UiStyleId>([
  "catalog",
  "classic",
  "pulse",
  "signal",
  "folio",
  "folio-dark",
  "ashita",
]);
const EXPERIMENTAL_THEME_FONT_LINK_ID = "webterm-experimental-theme-fonts";
let experimentalThemePromise: Promise<typeof import("./experimental-theme-tokens")> | null = null;
let appliedExperimentalTokenNames = new Set<string>();

/** Folio light + dark share the same editorial paper design language. */
export function isFolioStyle(value: unknown): value is "folio" | "folio-dark" {
  return value === "folio" || value === "folio-dark";
}

/** Flow — AI-native SaaS skin family with its own shell (topbar, floating sheet). */
export function isFlowStyle(value: unknown): value is "flow" | "flow-dark" {
  return value === "flow" || value === "flow-dark";
}

const UI_STYLE_ID_SET = new Set<UiStyleId>([
  "enterprise-light",
  "enterprise-dark",
  "catalog",
  "classic",
  "pulse",
  "signal",
  "folio",
  "folio-dark",
  "flow",
  "flow-dark",
  "ashita",
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
    id: "enterprise-light",
    labelRu: "Новый интерфейс · светлый",
    labelEn: "New interface · Light",
    blurbRu: "Светлая рабочая среда с новой навигацией, сеткой страниц, таблицами и формами.",
    blurbEn: "A light workspace with redesigned navigation, page layouts, tables, and forms.",
    swatches: ["#f3f6f8", "#15324b", "#1d63d5", "#17845b"],
  },
  {
    id: "enterprise-dark",
    labelRu: "Новый интерфейс · тёмный",
    labelEn: "New interface · Dark",
    blurbRu: "Глубокие графитовые поверхности, спокойный контраст и тот же новый рабочий интерфейс.",
    blurbEn: "Deep graphite surfaces, calm contrast, and the same redesigned workspace.",
    swatches: ["#0b1118", "#152536", "#62a4ff", "#3cc68a"],
  },
  {
    id: "catalog",
    labelRu: "Каталог",
    labelEn: "Catalog",
    blurbRu: "Контрастная тема с лаймовым акцентом, моноширинным шрифтом и резкими тенями.",
    blurbEn: "A high-contrast theme with lime accents, monospace type, and sharp shadows.",
    swatches: ["#09090b", "#c8f542", "#f4f1ea", "#7ec8ff"],
  },
  {
    id: "classic",
    labelRu: "Классика",
    labelEn: "Classic",
    blurbRu: "Классическая тёмная тема с бирюзовым акцентом и мягкими тенями.",
    blurbEn: "A classic dark theme with teal accents and soft shadows.",
    swatches: ["#08111f", "#22c5b0", "#e8f0f6", "#9b87f5"],
  },
  {
    id: "pulse",
    labelRu: "Пульс",
    labelEn: "Pulse",
    blurbRu: "Тёмная фиолетовая тема с полупрозрачными поверхностями и мягким свечением.",
    blurbEn: "A dark violet theme with translucent surfaces and a soft glow.",
    swatches: ["#0c0614", "#c084fc", "#f5f0ff", "#22d3ee"],
  },
  {
    id: "signal",
    labelRu: "Сигнал",
    labelEn: "Signal",
    blurbRu: "Строгая чёрная тема с янтарными акцентами и прямыми углами.",
    blurbEn: "A stark black theme with amber accents and square corners.",
    swatches: ["#050505", "#ff7a12", "#f2f2f0", "#ff2d55"],
  },
  {
    id: "folio",
    labelRu: "Фолио · светлая",
    labelEn: "Folio · Light",
    blurbRu: "Спокойная светлая тема в тёплых серых тонах.",
    blurbEn: "A calm light theme in warm gray tones.",
    swatches: ["#8a8680", "#9a4a24", "#1f1c1a", "#1f5f58"],
  },
  {
    id: "folio-dark",
    labelRu: "Фолио · тёмная",
    labelEn: "Folio · Dark",
    blurbRu: "Тёмная тема в тёплых серых тонах с терракотовым акцентом.",
    blurbEn: "A dark warm-gray theme with terracotta accents.",
    swatches: ["#161310", "#e07a3d", "#f3ebe2", "#2dd4bf"],
  },
  {
    id: "flow",
    labelRu: "Флоу · светлая",
    labelEn: "Flow · Light",
    blurbRu: "Чистая светлая тема с белыми карточками и зелёными статусами.",
    blurbEn: "A clean light theme with white cards and green status accents.",
    swatches: ["#f5f4f1", "#17181c", "#22a55e", "#3b7cf6"],
  },
  {
    id: "flow-dark",
    labelRu: "Флоу · тёмная",
    labelEn: "Flow · Dark",
    blurbRu: "Основная тёмная тема с графитовыми поверхностями и светлыми кнопками.",
    blurbEn: "The primary dark theme with graphite surfaces and light buttons.",
    swatches: ["#101013", "#f7f7f8", "#3ec777", "#5b8ef7"],
  },
  {
    id: "ashita",
    labelRu: "ASHITA",
    labelEn: "ASHITA",
    blurbRu: "Тёмная тема с розовыми и бирюзовыми неоновыми акцентами.",
    blurbEn: "A dark theme with pink and teal neon accents.",
    swatches: ["#080A10", "#D66AB5", "#49D4D1", "#E14B5F"],
  },
];

export function isUiStyleId(value: unknown): value is UiStyleId {
  return typeof value === "string" && UI_STYLE_ID_SET.has(value as UiStyleId);
}

/** Enterprise v1 is an opt-in structural redesign, not a palette alias. */
export function isEnterpriseStyle(value: unknown): value is "enterprise-light" | "enterprise-dark" {
  return value === "enterprise-light" || value === "enterprise-dark";
}

/** Chat intentionally stays on the current pilot UI while Enterprise is refined. */
export function resolveDocumentUiStyle(style: UiStyleId, pathname: string): UiStyleId {
  if (isEnterpriseStyle(style) && /^\/chat(?:\/|$)/.test(pathname)) {
    return "flow-dark";
  }
  return style;
}

const LEGACY_THEME_FONT_LINK_ID = "webterm-supported-theme-fonts";
const LEGACY_THEME_FONT_URL =
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Manrope:wght@400;500;600;700;800&display=swap";

function ensureStylesheetLink(id: string, href: string) {
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = href;
  document.head.append(link);
}

function syncThemeFontLinks(style: UiStyleId) {
  const experimentalFontLink = document.getElementById(EXPERIMENTAL_THEME_FONT_LINK_ID);
  if (isEnterpriseStyle(style)) {
    document.getElementById(LEGACY_THEME_FONT_LINK_ID)?.remove();
    experimentalFontLink?.remove();
    return;
  }

  ensureStylesheetLink(LEGACY_THEME_FONT_LINK_ID, LEGACY_THEME_FONT_URL);
  if (!EXPERIMENTAL_UI_STYLES.has(style)) {
    experimentalFontLink?.remove();
  }
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

function clearExperimentalThemeTokens() {
  for (const tokenName of appliedExperimentalTokenNames) {
    document.documentElement.style.removeProperty(tokenName);
  }
  appliedExperimentalTokenNames = new Set();
}

function loadExperimentalTheme(style: UiStyleId) {
  if (!EXPERIMENTAL_UI_STYLES.has(style)) return;
  experimentalThemePromise ??= import("./experimental-theme-tokens");
  void experimentalThemePromise.then((themeModule) => {
    if (document.documentElement.getAttribute("data-ui-style") !== style) return;

    ensureStylesheetLink(EXPERIMENTAL_THEME_FONT_LINK_ID, themeModule.EXPERIMENTAL_THEME_FONT_URL);

    const tokenTheme = style as keyof typeof themeModule.EXPERIMENTAL_THEME_TOKENS;
    const tokens = themeModule.EXPERIMENTAL_THEME_TOKENS[tokenTheme];
    if (!tokens) return;
    for (const [tokenName, value] of Object.entries(tokens)) {
      document.documentElement.style.setProperty(tokenName, value);
      appliedExperimentalTokenNames.add(tokenName);
    }
  }).catch(() => {
    // Experimental styles may fall back to the base palette if their optional
    // chunk cannot be loaded. The supported flow-dark pilot theme is inline.
  });
}

export function applyUiStyleToDocument(
  style: UiStyleId,
  pathname = typeof window === "undefined" ? "/" : window.location.pathname,
) {
  if (typeof document === "undefined") return;
  const effectiveStyle = resolveDocumentUiStyle(style, pathname);
  clearExperimentalThemeTokens();
  document.documentElement.setAttribute("data-ui-preference", style);
  document.documentElement.setAttribute("data-ui-style", effectiveStyle);
  document.documentElement.style.colorScheme = LIGHT_UI_STYLES.has(effectiveStyle) ? "light" : "dark";
  syncThemeFontLinks(effectiveStyle);
  loadExperimentalTheme(effectiveStyle);

  const themeColor = UI_STYLE_OPTIONS.find((option) => option.id === effectiveStyle)?.swatches[0];
  if (themeColor) {
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute("content", themeColor);
  }
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
