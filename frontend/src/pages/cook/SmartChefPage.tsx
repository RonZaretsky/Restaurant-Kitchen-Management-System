import { useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useGenerateSuggestion, useSuggestions } from "../../services/smartChefService";
import type { AIRecipeSuggestion } from "../../types/ai";

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
 * One Recipe Suggestion card (Story 6.1, AC6).
 *
 * Shows the suggestion's content only — name, the ingredients it drew on, and its plating
 * description. No Confirm/Dismiss actions and no chat panel render here: both are explicitly
 * out of this story's scope (Confirm/Dismiss is Story 6.2's Admin-only action; the chat panel is
 * Story 6.3's), even though the shared UX mockup shows all three on one screen.
 *
 * `requested_by` is shown as a raw `User #{id}`, not a resolved name: no endpoint a Cook can call
 * resolves a user id to a name (the same precedent `StockMovement`'s own "Recorded by" column
 * already established), and `GET /api/admin/users` is Admin-only.
 *
 * @param suggestion - The Recipe Suggestion this card describes.
 * @returns The suggestion card.
 */
function SuggestionCard({ suggestion }: { suggestion: AIRecipeSuggestion }) {
  return (
    <Card variant="outlined" sx={{ padding: 2, marginBottom: 2 }}>
      <Typography variant="h6">{suggestion.generated_recipe.name}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ marginBottom: 1 }}>
        {`Requested by User #${suggestion.requested_by} · generated ${new Date(suggestion.created_at).toLocaleString()}`}
      </Typography>

      <Typography variant="subtitle2" sx={{ marginTop: 1 }}>
        Ingredients drawn on
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, marginTop: 0.5, marginBottom: 1 }}>
        {suggestion.generated_recipe.ingredients.map((ingredient) => (
          <Chip key={ingredient.name} size="small" label={`${ingredient.name}, ${ingredient.quantity}`} />
        ))}
      </Box>

      <Typography variant="subtitle2">Suggested plating</Typography>
      <Typography variant="body2">{suggestion.generated_recipe.plating}</Typography>
    </Card>
  );
}

/**
 * The Cook's Smart Chef surface (Story 6.1).
 *
 * A request bar (optional free-text direction + "Request suggestion") and a list of the Cook's
 * persisted Recipe Suggestions, newest first (`useSuggestions`'s own `id.desc()` order),
 * matching the mockup's own "N recipe suggestions" subtitle and the `EXPERIENCE.md`-specified
 * empty/generating/error states (AC1-AC4, AC6).
 *
 * @returns The Smart Chef page.
 */
export function SmartChefPage() {
  const [direction, setDirection] = useState("");
  const { data: suggestions, isLoading, isError, error } = useSuggestions();
  const generateMutation = useGenerateSuggestion();

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (generateMutation.isPending) {
      // Re-checks the pending state directly rather than trusting the disabled button alone —
      // Enter submits a form regardless of a disabled submit button (AC3's primary UX
      // mechanism; the backend's 409 is the defense-in-depth backstop, not relied on here).
      return;
    }
    const trimmedDirection = direction.trim();
    generateMutation.mutate(
      { direction: trimmedDirection === "" ? undefined : trimmedDirection },
      { onSuccess: () => setDirection("") },
    );
  };

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Smart Chef
      </Typography>

      <Box
        component="form"
        onSubmit={handleSubmit}
        sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "flex-start", marginBottom: 3 }}
      >
        <TextField
          size="small"
          label="Direction (optional)"
          placeholder='e.g. "something for dessert", "want it spicy"'
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
          sx={{ minWidth: 320 }}
        />
        <Button type="submit" variant="contained" disabled={generateMutation.isPending}>
          Request suggestion
        </Button>
        {generateMutation.isPending && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              Generating suggestion...
            </Typography>
          </Box>
        )}
      </Box>

      {generateMutation.isError && (
        <Alert severity="error" sx={{ marginBottom: 2 }}>
          {errorMessage(generateMutation.error)}
        </Alert>
      )}

      {isLoading && <RowsSkeleton count={3} />}

      {isError && <Alert severity="error">{`Could not load suggestions. ${errorMessage(error)}`}</Alert>}

      {!isLoading && !isError && suggestions?.length === 0 && (
        <Typography color="text.secondary">No recipe suggestions yet.</Typography>
      )}

      {!isLoading &&
        !isError &&
        suggestions?.map((suggestion) => <SuggestionCard key={suggestion.id} suggestion={suggestion} />)}
    </>
  );
}
