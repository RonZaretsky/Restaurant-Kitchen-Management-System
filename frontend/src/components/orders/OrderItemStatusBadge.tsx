import type { ReactElement } from "react";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import LocalFireDepartmentIcon from "@mui/icons-material/LocalFireDepartment";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import Chip from "@mui/material/Chip";

import type { OrderItemStatus } from "../../types/order";

const LABELS: Record<OrderItemStatus, string> = {
  pending: "Pending",
  in_preparation: "In preparation",
  ready: "Ready",
};

const ICONS: Record<OrderItemStatus, ReactElement> = {
  pending: <RadioButtonUncheckedIcon />,
  in_preparation: <LocalFireDepartmentIcon />,
  ready: <CheckCircleIcon />,
};

const COLORS: Record<OrderItemStatus, "default" | "warning" | "success"> = {
  pending: "default",
  in_preparation: "warning",
  ready: "success",
};

/**
 * The shared Order Item status badge (UX-DR1): an MUI Chip with an icon and a spelled-out label,
 * built once so Story 3.4's edit/cancel UI and Epic 5's Kitchen Display can reuse it rather than
 * each re-implementing their own status-to-color mapping.
 *
 * Scoped to today's 3-member OrderItemStatus type. `cancelled` (AD-11) and Order-level statuses
 * (`served`/`closed`) do not belong here, either because they don't exist on the backend enum yet
 * or because they describe a different type (OrderStatus, not OrderItemStatus).
 *
 * @param status - The Order Item's current status.
 * @returns The status Chip for this Order Item.
 */
export function OrderItemStatusBadge({ status }: { status: OrderItemStatus }) {
  return <Chip size="small" icon={ICONS[status]} label={LABELS[status]} color={COLORS[status]} />;
}
