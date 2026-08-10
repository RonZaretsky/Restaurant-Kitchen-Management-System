import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";

import { DENSE_ROW_HEIGHT } from "../../config/theme";

/**
 * A reusable cold-load placeholder: a stack of dense-row-height Skeleton
 * bars.
 *
 * The shared pattern every later story reuses for its own cold-load state
 * (UX-DR15). This story uses it for the one real loading state it has,
 * `useCurrentUser` resolving on first app load; later stories reuse it for
 * their own data fetches.
 *
 * @param count - How many skeleton rows to render.
 * @returns A stack of Skeleton rows.
 */
export function RowsSkeleton({ count }: { count: number }) {
  return (
    <Stack spacing={1} role="status" aria-label="Loading">
      {Array.from({ length: count }, (_, index) => (
        <Skeleton key={index} variant="rectangular" height={DENSE_ROW_HEIGHT} />
      ))}
    </Stack>
  );
}
