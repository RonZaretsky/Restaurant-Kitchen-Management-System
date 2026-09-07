import type { ReactElement } from "react";
import BlockIcon from "@mui/icons-material/Block";
import CancelIcon from "@mui/icons-material/Cancel";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import LocalFireDepartmentIcon from "@mui/icons-material/LocalFireDepartment";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import Chip from "@mui/material/Chip";

import type { OrderItemStatus } from "../../types/order";

const LABELS: Record<OrderItemStatus, string> = {
  pending: "Pending",
  in_preparation: "In preparation",
  ready: "Ready",
  cancelled: "Cancelled",
  rejected: "Rejected",
};

const ICONS: Record<OrderItemStatus, ReactElement> = {
  pending: <RadioButtonUncheckedIcon />,
  in_preparation: <LocalFireDepartmentIcon />,
  ready: <CheckCircleIcon />,
  cancelled: <CancelIcon />,
  rejected: <BlockIcon />,
};

const COLORS: Record<OrderItemStatus, "default" | "warning" | "success" | "error"> = {
  pending: "default",
  in_preparation: "warning",
  ready: "success",
  cancelled: "error",
  rejected: "error",
};

/**
 * The shared Order Item status badge: an MUI Chip with an icon and a spelled-out label,
 * built once so the Waiter's edit/cancel UI and the Kitchen Display can reuse it rather than
 * each re-implementing their own status-to-color mapping.
 *
 * Covers all 5 OrderItemStatus members, `cancelled` and `rejected` (this
 * batch) included. Order-level
 * statuses (`served`/`closed`) still do not belong here, they describe a different type
 * (OrderStatus, not OrderItemStatus).
 *
 * @param status - The Order Item's current status.
 * @returns The status Chip for this Order Item.
 */
export function OrderItemStatusBadge({ status }: { status: OrderItemStatus }) {
  return <Chip size="small" icon={ICONS[status]} label={LABELS[status]} color={COLORS[status]} />;
}
