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
 * One row of the Tables list, owning its own edit-mode state.
 *
 * The editable fields are controlled and resync from the server's value
 * whenever it changes, the same pattern Story 2.3's `RecipeLineRow` uses,
 * so a rejected save or another Admin's edit is always reflected back
 * instead of leaving stale text in the field.
 *
 * @param table - The Table this row displays and edits.
 * @returns The table row.
 */
function TableListRow({ table }: { table: RestaurantTable }) {
  const [isEditing, setIsEditing] = useState(false);
  const [draftNumber, setDraftNumber] = useState(String(table.table_number));
  const [draftCapacity, setDraftCapacity] = useState(String(table.capacity));
  const updateMutation = useUpdateTable();

  useEffect(() => {
    setDraftNumber(String(table.table_number));
    setDraftCapacity(String(table.capacity));
  }, [table.table_number, table.capacity]);

  const isAvailable = table.status === "available";

  const startEdit = () => {
    updateMutation.reset();
    setIsEditing(true);
  };

  const cancelEdit = () => {
    setDraftNumber(String(table.table_number));
    setDraftCapacity(String(table.capacity));
    setIsEditing(false);
  };

  const save = () => {
    const payload: { table_number?: number; capacity?: number } = {};
    if (Number(draftNumber) !== table.table_number) {
      payload.table_number = Number(draftNumber);
    }
    if (Number(draftCapacity) !== table.capacity) {
      payload.capacity = Number(draftCapacity);
    }
    if (Object.keys(payload).length === 0) {
      setIsEditing(false);
      return;
    }
    updateMutation.mutate(
      { tableId: table.id, payload },
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
              <Button size="small" variant="contained" onClick={save} disabled={updateMutation.isPending}>
                Save
              </Button>
              <Button size="small" onClick={cancelEdit}>
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

  const handleCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    createMutation.mutate(
      { table_number: Number(tableNumber), capacity: Number(capacity) },
      {
        onSuccess: () => {
          setTableNumber("");
          setCapacity("");
        },
      },
    );
  };

  const canSubmit = tableNumber !== "" && capacity !== "" && !createMutation.isPending;

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
          slotProps={{ htmlInput: { inputMode: "numeric" } }}
        />
        <TextField
          size="small"
          label="Capacity (seats)"
          value={capacity}
          onChange={(event) => setCapacity(event.target.value)}
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
