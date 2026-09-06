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
 * Storage access can throw outright where site data is blocked, and this runs
 * inside a useState initializer in the provider that wraps the whole app, so
 * an unguarded read would stop the app mounting at all rather than costing a
 * theme preference.
 *
 * @returns The stored mode, or null if nothing valid is stored or storage
 *   cannot be read.
 */
function readStoredMode(): ThemeMode | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

/**
 * Persists the chosen theme mode, ignoring a storage failure.
 *
 * The mode still applies for the rest of the session when this fails, it just
 * will not survive a reload.
 *
 * @param mode - The mode to remember for this browser.
 */
function writeStoredMode(mode: ThemeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // A blocked or full store costs persistence, never the toggle itself.
  }
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
 * (Kitchen Display's home surface) and light for every other Role.
 * Once a preference is stored, it wins regardless of Role. Before the
 * current User's Role is known (still loading, or on the pre-auth Login
 * screen), the default is light, matching every non-Cook Role.
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
    writeStoredMode(next);
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
