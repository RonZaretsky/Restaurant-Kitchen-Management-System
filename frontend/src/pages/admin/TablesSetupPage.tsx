import { useEffect, useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useCreateTable, useTables, useUpdateTable } from "../../services/tableService";
import type { Table as RestaurantTable } from "../../types/table";

/** Same wording TableInUseError carries server-side. */
const TABLE_IN_USE_MESSAGE = "Rejected, table in use";

/**
 * Reads the human-readable message off a failed request.
 *
 * @param error - The error a query or mutation failed with.
 * @returns The message to display inline.
 */
function errorMessage(error: Error): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Something went wrong. Try again.";
}

/**
 * Parses a field that must hold a positive whole number.
 *
 * Deliberately stricter than `Number()`: that coerces `""` and `" "` to 0 and
 * turns anything unparseable into `NaN`, which `JSON.stringify` then serializes
 * as `null`. A null reaches the backend as a field the caller did supply, so
 * accepting it here is how a typo in one field silently ships a partial write.
 *
 * @param raw - The raw text from the input.
 * @returns The parsed integer, or null if the text is not a positive integer.
 */
function parsePositiveInteger(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/** Shown when a number field holds something that is not a positive whole number. */
const INVALID_NUMBER_MESSAGE = "Enter a whole number greater than zero";

/**
 * One row of the Tables list, owning its own edit-mode state.
 *
 * The editable fields are controlled and resync from the server's value, but
 * only while this row is not being edited: resyncing mid-edit would silently
 * replace text the Admin is still typing whenever the list refetches (on window
 * focus, or after any sibling row's save).
 *
 * @param table - The Table this row displays and edits.
 * @returns The table row.
 */
function TableListRow({ table }: { table: RestaurantTable }) {
  const [isEditing, setIsEditing] = useState(false);
  const [draftNumber, setDraftNumber] = useState(String(table.table_number));
  const [draftCapacity, setDraftCapacity] = useState(String(table.capacity));
  const updateMutation = useUpdateTable();

  const isAvailable = table.status === "available";

  useEffect(() => {
    if (isEditing) {
      return;
    }
    setDraftNumber(String(table.table_number));
    setDraftCapacity(String(table.capacity));
  }, [table.table_number, table.capacity, isEditing]);

  // A table seated while this row is open can no longer be edited, so drop out
  // of edit mode rather than leaving a form the next Save can only 409 on.
  useEffect(() => {
    if (!isAvailable && isEditing) {
      setIsEditing(false);
    }
  }, [isAvailable, isEditing]);

  const parsedNumber = parsePositiveInteger(draftNumber);
  const parsedCapacity = parsePositiveInteger(draftCapacity);
  const hasInvalidDraft = parsedNumber === null || parsedCapacity === null;

  const startEdit = () => {
    updateMutation.reset();
    setIsEditing(true);
  };

  const cancelEdit = () => {
    updateMutation.reset();
    setDraftNumber(String(table.table_number));
    setDraftCapacity(String(table.capacity));
    setIsEditing(false);
  };

  const save = () => {
    if (parsedNumber === null || parsedCapacity === null) {
      return;
    }
    // Both fields are always sent, never diffed against the cached row. Diffing
    // makes the request depend on possibly-stale cache: if another Admin has
    // already changed this value, typing the cached one produces an empty
    // payload, so no request is sent and the row exits edit mode looking saved
    // while the server still holds the other value. Letting the server decide
    // what changed is the only version that cannot silently do nothing.
    updateMutation.mutate(
      { tableId: table.id, payload: { table_number: parsedNumber, capacity: parsedCapacity } },
      { onSuccess: () => setIsEditing(false) },
    );
  };

  return (
    <>
      <TableRow>
        <TableCell>
          {isEditing ? (
            <TextField
              size="small"
              label={`Table number for table ${table.table_number}`}
              value={draftNumber}
              onChange={(event) => setDraftNumber(event.target.value)}
              error={parsedNumber === null}
              helperText={parsedNumber === null ? INVALID_NUMBER_MESSAGE : undefined}
              slotProps={{ htmlInput: { inputMode: "numeric" } }}
            />
          ) : (
            table.table_number
          )}
        </TableCell>
        <TableCell>
          {isEditing ? (
            <TextField
              size="small"
              label={`Capacity for table ${table.table_number}`}
              value={draftCapacity}
              onChange={(event) => setDraftCapacity(event.target.value)}
              error={parsedCapacity === null}
              helperText={parsedCapacity === null ? INVALID_NUMBER_MESSAGE : undefined}
              slotProps={{ htmlInput: { inputMode: "numeric" } }}
            />
          ) : (
            table.capacity
          )}
        </TableCell>
        <TableCell>
          <Chip
            size="small"
            label={table.status}
            color={isAvailable ? "success" : "default"}
          />
        </TableCell>
        <TableCell>
          {isEditing ? (
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button
                size="small"
                variant="contained"
                onClick={save}
                disabled={updateMutation.isPending || hasInvalidDraft}
              >
                Save
              </Button>
              <Button size="small" onClick={cancelEdit} disabled={updateMutation.isPending}>
                Cancel
              </Button>
            </Box>
          ) : (
            <Tooltip title={isAvailable ? "" : TABLE_IN_USE_MESSAGE}>
              <span>
                <Button size="small" onClick={startEdit} disabled={!isAvailable}>
                  Edit
                </Button>
              </span>
            </Tooltip>
          )}
          {!isAvailable && !isEditing && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {TABLE_IN_USE_MESSAGE}
            </Typography>
          )}
        </TableCell>
      </TableRow>
      {updateMutation.isError && (
        <TableRow>
          <TableCell colSpan={4}>
            <Alert severity="error">{errorMessage(updateMutation.error)}</Alert>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/**
 * The Tables setup surface (Story 2.4).
 *
 * An "Add table" form and a dense-row list (UX-DR8) of every Restaurant
 * Table, each row editable only while `available` (AC3/AC4/AC6). No delete
 * action exists anywhere on this page or its children (AC7), Restaurant
 * Tables are only ever added and edited.
 *
 * @returns The Tables setup page.
 */
export function TablesSetupPage() {
  const [tableNumber, setTableNumber] = useState("");
  const [capacity, setCapacity] = useState("");
  const { data: tables, isLoading, isError, error, refetch } = useTables();
  const createMutation = useCreateTable();

  const parsedNumber = parsePositiveInteger(tableNumber);
  const parsedCapacity = parsePositiveInteger(capacity);

  const handleCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (parsedNumber === null || parsedCapacity === null) {
      return;
    }
    createMutation.mutate(
      { table_number: parsedNumber, capacity: parsedCapacity },
      {
        onSuccess: () => {
          setTableNumber("");
          setCapacity("");
        },
      },
    );
  };

  // Both fields must parse as positive whole numbers, not merely be non-empty:
  // Number(" ") is 0 and Number("abc") is NaN, which serializes to JSON null.
  const canSubmit = parsedNumber !== null && parsedCapacity !== null && !createMutation.isPending;

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Tables setup
      </Typography>

      <Box
        component="form"
        onSubmit={handleCreate}
        sx={{ display: "flex", flexDirection: "row", gap: 1, alignItems: "center", marginBottom: 3 }}
      >
        <TextField
          size="small"
          label="Table number"
          value={tableNumber}
          onChange={(event) => setTableNumber(event.target.value)}
          error={tableNumber !== "" && parsedNumber === null}
          helperText={tableNumber !== "" && parsedNumber === null ? INVALID_NUMBER_MESSAGE : undefined}
          slotProps={{ htmlInput: { inputMode: "numeric" } }}
        />
        <TextField
          size="small"
          label="Capacity (seats)"
          value={capacity}
          onChange={(event) => setCapacity(event.target.value)}
          error={capacity !== "" && parsedCapacity === null}
          helperText={capacity !== "" && parsedCapacity === null ? INVALID_NUMBER_MESSAGE : undefined}
          slotProps={{ htmlInput: { inputMode: "numeric" } }}
        />
        <Button type="submit" variant="contained" disabled={!canSubmit}>
          Add table
        </Button>
      </Box>

      {createMutation.isError && (
        <Alert severity="error" sx={{ marginBottom: 2 }}>
          {errorMessage(createMutation.error)}
        </Alert>
      )}

      {isLoading && <RowsSkeleton count={5} />}

      {isError && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        >
          {`Could not load the tables. ${errorMessage(error)}`}
        </Alert>
      )}

      {!isLoading && !isError && tables?.length === 0 && (
        <Typography color="text.secondary">No tables configured yet.</Typography>
      )}

      {!isLoading && !isError && tables && tables.length > 0 && (
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Table number</TableCell>
              <TableCell>Capacity</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {tables.map((table) => (
              <TableListRow key={table.id} table={table} />
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
