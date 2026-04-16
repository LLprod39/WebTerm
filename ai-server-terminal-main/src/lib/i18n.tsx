/**
 * src/lib/i18n.tsx
 *
 * Lightweight i18n context. Translations live in src/locales/{en,ru}.json.
 * API is intentionally minimal — no heavy i18n library needed.
 *
 * Public API (unchanged — no consumers need to change):
 *   I18nProvider  — wraps the app (in App.tsx)
 *   useI18n()     — returns { lang, setLang, t }
 *
 * Adding a new string:
 *   1. Add the key + English value to src/locales/en.json
 *   2. Add the Russian translation to src/locales/ru.json
 *   3. Use t("your.key") in components — no code change needed here
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import enMessages from "../locales/en.json";
import ruMessages from "../locales/ru.json";

type Lang = "en" | "ru";

const STORAGE_KEY = "weu_lang";

const translations: Record<Lang, Record<string, string>> = {
  en: enMessages as Record<string, string>,
  ru: ruMessages as Record<string, string>,
};

interface I18nContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue>({
  lang: "ru",
  setLang: () => {},
  t: (k) => k,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "ru" || stored === "en") return stored;
    return "ru";
  });

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    localStorage.setItem(STORAGE_KEY, l);
    document.documentElement.lang = l;
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const t = useCallback(
    (key: string) => translations[lang]?.[key] ?? translations.en[key] ?? key,
    [lang],
  );

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
