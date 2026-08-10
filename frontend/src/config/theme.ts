import { createTheme, type Theme } from "@mui/material/styles";

/**
 * The shared dense-row height (px) for tables/lists across the app.
 *
 * The theme's `size="small"` component defaults get most of the way there;
 * this constant is for row containers that need the exact figure, e.g.
 * `<TableRow sx={{ height: DENSE_ROW_HEIGHT }}>`.
 */
export const DENSE_ROW_HEIGHT = 36;

const sharedComponents = {
  MuiTable: { defaultProps: { size: "small" as const } },
  MuiList: { defaultProps: { dense: true } },
};

/**
 * Light theme. MUI defaults everywhere except the accent color, which
 * overrides the `primary` slot per DESIGN.md's Colors/Components section.
 */
export const lightTheme: Theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0B6E8F", contrastText: "#FFFFFF" },
  },
  components: sharedComponents,
});

/**
 * Dark theme. Same delta as lightTheme, using the dark-mode accent pair.
 */
export const darkTheme: Theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#4FC3D9", contrastText: "#08171B" },
  },
  components: sharedComponents,
});
