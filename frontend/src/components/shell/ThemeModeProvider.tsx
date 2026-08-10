import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { CssBaseline, ThemeProvider } from "@mui/material";

import { darkTheme, lightTheme } from "../../config/theme";
import { useCurrentUser } from "../../services/authService";

type ThemeMode = "light" | "dark";

const STORAGE_KEY = "rkms-theme-mode";

interface ThemeModeContextValue {
  mode: ThemeMode;
  toggleMode: () => void;
}

const ThemeModeContext = createContext<ThemeModeContextValue | undefined>(undefined);

/**
 * Reads and validates the browser's stored theme preference.
 *
 * @returns The stored mode, or null if nothing valid is stored yet.
 */
function readStoredMode(): ThemeMode | null {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : null;
}

/**
 * Reads the current theme mode and the function to flip it.
 *
 * @returns The active mode and a toggle function.
 * @throws Error if called outside a ThemeModeProvider.
 */
export function useThemeMode(): ThemeModeContextValue {
  const context = useContext(ThemeModeContext);
  if (!context) {
    throw new Error("useThemeMode must be used within a ThemeModeProvider");
  }
  return context;
}

/**
 * Provides the app's MUI theme and its light/dark mode.
 *
 * Persists the mode per browser/terminal (not per user account) in
 * localStorage. With no stored preference yet, defaults to dark for a Cook
 * (Kitchen Display's home surface) and light for every other Role, per AC4.
 * Once a preference is stored, it wins regardless of Role. Before the
 * current User's Role is known (still loading, or on the pre-auth Login
 * screen), the default is light, matching every non-Cook Role and the Login
 * mockup itself.
 *
 * @param children - The subtree to theme.
 * @returns The themed subtree, wrapped with CssBaseline.
 */
export function ThemeModeProvider({ children }: { children: ReactNode }) {
  const { data: user } = useCurrentUser();
  const [storedMode, setStoredMode] = useState<ThemeMode | null>(readStoredMode);

  const mode: ThemeMode = storedMode ?? (user?.role === "cook" ? "dark" : "light");

  const toggleMode = () => {
    const next: ThemeMode = mode === "light" ? "dark" : "light";
    localStorage.setItem(STORAGE_KEY, next);
    setStoredMode(next);
  };

  const theme = useMemo(() => (mode === "dark" ? darkTheme : lightTheme), [mode]);

  return (
    <ThemeModeContext.Provider value={{ mode, toggleMode }}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ThemeModeContext.Provider>
  );
}
