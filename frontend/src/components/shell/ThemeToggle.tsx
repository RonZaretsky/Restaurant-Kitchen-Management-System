import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import IconButton from "@mui/material/IconButton";

import { useThemeMode } from "./ThemeModeProvider";

/**
 * App bar control that flips the light/dark theme mode.
 *
 * Stock MUI IconButton, no visual override, per DESIGN.md's
 * {components.theme-toggle}.
 *
 * @returns The toggle button, labelled with the mode it will switch to.
 */
export function ThemeToggle() {
  const { mode, toggleMode } = useThemeMode();

  return (
    <IconButton
      color="inherit"
      onClick={toggleMode}
      aria-label={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
    >
      {mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
    </IconButton>
  );
}
