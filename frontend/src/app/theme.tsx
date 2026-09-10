import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
type Theme = "light" | "dark";
const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
  theme: "light",
  toggle: () => {},
});
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return localStorage.getItem("webterm-next-theme") === "dark"
        ? "dark"
        : "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("webterm-next-theme", theme);
    } catch {
      /* Storage may be unavailable in private policy. */
    }
  }, [theme]);
  return (
    <ThemeContext.Provider
      value={{
        theme,
        toggle: () => setTheme((t) => (t === "light" ? "dark" : "light")),
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}
export function useTheme() {
  return useContext(ThemeContext);
}
