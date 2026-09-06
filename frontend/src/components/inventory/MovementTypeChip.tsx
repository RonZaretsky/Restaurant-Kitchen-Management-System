import Chip from "@mui/material/Chip";

import type { MovementType } from "../../types/inventory";

const LABELS: Record<MovementType, string> = {
  purchase: "Purchase",
  consumption: "Consumption",
  waste: "Waste",
  adjustment: "Adjustment",
};

// Deliberately none of "success"/"warning"/"error": those three are
// OrderItemStatusBadge's traffic-light trio (ready/in_preparation/cancelled).
// A movement type is a category, not an urgency signal, so this
// reuses MUI's three remaining semantic Chip colors plus "default" instead —
// keeping the chip theme-aware in dark mode, which raw hex swatches would not be.
const COLORS: Record<MovementType, "primary" | "info" | "default" | "secondary"> = {
  purchase: "primary",
  consumption: "info",
  waste: "default",
  adjustment: "secondary",
};

/**
 * The Stock Movement type chip: a neutral-palette MUI Chip, deliberately
 * distinct from OrderItemStatusBadge's traffic-light convention, since a movement's type is a
 * category, not an urgency signal.
 *
 * @param type - The Stock Movement's type.
 * @returns The type Chip.
 */
export function MovementTypeChip({ type }: { type: MovementType }) {
  return <Chip size="small" label={LABELS[type]} color={COLORS[type]} />;
}
