import { useEffect } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";

import { useRealtime } from "../../components/shell/RealtimeProvider";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { ALERTS_QUERY_KEY, useAlerts } from "../../services/inventoryService";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/**
 * Reads the human-readable message off a failed request.
 *
 * @param error - The error the query failed with.
 * @returns The message to display inline.
 */
function errorMessage(error: Error): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return GENERIC_ERROR_MESSAGE;
}

/**
 * The Alerts surface (Story 4.2, replacing Story 4.1's placeholder).
 *
 * One row per Ingredient currently in shortage (FR-14), reading exactly
 * `"Stock low: {name} ({current stock}{unit} left)"` (UX-DR10). Styled per
 * DESIGN.md's `alert-row` token: the same red as a cancelled OrderItem/
 * in-shortage Ingredient row, plus a WarningAmberIcon — previously missing
 * here (rows rendered as plain unstyled text), fixed after manual testing
 * found the row's clickability had no visible affordance at all. A
 * standing border plus a subtle shadow give the row a card-like, clearly
 * interactive look at rest (not just on hover), each tuned separately for
 * light/dark since a flat "error.light" border reads too faint on a dark
 * background. No dismiss control anywhere: a row drops off only when a
 * Stock Movement brings that Ingredient back at or above threshold, never
 * a manual action here. Clicking a row opens that Ingredient's detail page
 * to log the resolving movement. Subscribes to the live
 * `inventory.alerts_changed` push
 * (Story 4.2, Observer/Pub-Sub) so a shortage appearing or clearing updates
 * this screen without a manual refresh, independently of the same-named
 * subscription AppShell.tsx owns for the nav badge.
 *
 * @returns The Alerts page.
 */
export function AlertsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { subscribe } = useRealtime();
  const { data: alerts, isLoading, isError, error, refetch } = useAlerts();

  useEffect(() => {
    return subscribe("inventory.alerts_changed", () => {
      void queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY });
    });
  }, [subscribe, queryClient]);

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        Alerts
      </Typography>

      {isLoading && <RowsSkeleton count={5} />}

      {!isLoading && isError && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        >
          {errorMessage(error)}
        </Alert>
      )}

      {!isLoading && !isError && alerts && alerts.length === 0 && (
        <Typography>No active shortages</Typography>
      )}

      {!isLoading && !isError && alerts && alerts.length > 0 && (
        <List sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {alerts.map((ingredient) => (
            <ListItemButton
              key={ingredient.id}
              onClick={() => navigate(`/warehouse/ingredients/${ingredient.id}`)}
              sx={{
                color: "error.main",
                border: "1px solid",
                borderColor: (theme) => (theme.palette.mode === "dark" ? "rgba(244, 67, 54, 0.5)" : "error.light"),
                borderRadius: 1,
                boxShadow: (theme) =>
                  theme.palette.mode === "dark"
                    ? "0 1px 3px rgba(0, 0, 0, 0.5)"
                    : "0 1px 3px rgba(211, 47, 47, 0.15)",
                "&:hover": {
                  backgroundColor: (theme) =>
                    theme.palette.mode === "dark" ? "rgba(244, 67, 54, 0.16)" : "rgba(211, 47, 47, 0.08)",
                  borderColor: "error.main",
                },
              }}
            >
              <ListItemIcon sx={{ minWidth: 36, color: "error.main" }}>
                <WarningAmberIcon />
              </ListItemIcon>
              <ListItemText
                primary={`Stock low: ${ingredient.name} (${ingredient.current_stock}${ingredient.unit} left)`}
              />
            </ListItemButton>
          ))}
        </List>
      )}
    </Box>
  );
}
