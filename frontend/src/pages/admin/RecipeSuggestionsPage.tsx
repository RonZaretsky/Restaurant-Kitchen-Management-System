import { useNavigate } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Typography from "@mui/material/Typography";

import { SuggestionSummary } from "../../components/ai/SuggestionSummary";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useDismissSuggestion, useSuggestions } from "../../services/smartChefService";
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
 * One "awaiting review" Recipe Suggestion card (Story 6.2, AC4-AC6).
 *
 * Wraps `SuggestionSummary`'s read-only content with the two actions this
 * story adds. Confirm hands off to the existing Menu Management create-Dish
 * form via navigation state (AC1) rather than building a second, parallel
 * Dish-creation UI — AI-generated ingredients are free-text and still need
 * an Admin to map them to real Ingredient records with real quantities/units.
 * Dismiss fires immediately, no confirm step: the row is retained for audit
 * (AC4), so dismissing is not a data-loss action.
 *
 * @param suggestion - The Recipe Suggestion this card describes.
 * @returns The suggestion card with its Confirm/Dismiss actions.
 */
function ReviewableSuggestionCard({ suggestion }: { suggestion: AIRecipeSuggestion }) {
  const navigate = useNavigate();
  const dismissMutation = useDismissSuggestion();

  const handleConfirm = () => {
    navigate("/admin/menu", {
      state: {
        prefillName: suggestion.generated_recipe.name,
        prefillDescription: suggestion.generated_recipe.plating,
        sourceSuggestionId: suggestion.id,
      },
    });
  };

  return (
    <Card variant="outlined" sx={{ padding: 2, marginBottom: 2 }}>
      <SuggestionSummary suggestion={suggestion} />

      {dismissMutation.isError && (
        <Alert severity="error" sx={{ marginTop: 1 }}>
          {errorMessage(dismissMutation.error)}
        </Alert>
      )}

      <Box sx={{ display: "flex", gap: 1, marginTop: 2 }}>
        <Button variant="contained" size="small" onClick={handleConfirm}>
          Confirm into Dish
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={dismissMutation.isPending}
          onClick={() => dismissMutation.mutate(suggestion.id)}
        >
          Dismiss
        </Button>
      </Box>
    </Card>
  );
}

/**
 * The Admin's Recipe Suggestions review surface (Story 6.2).
 *
 * Fetches every Recipe Suggestion (Story 6.1's `useSuggestions`, already
 * Admin-accessible) and filters client-side to those "awaiting review" —
 * `!dismissed && confirmed_dish_id === null` — matching AD-9's client-side
 * filtering convention rather than adding a new backend query param. A
 * suggestion that is dismissed or already confirmed into a Dish drops off
 * this list even though the raw response still includes it.
 *
 * @returns The Recipe Suggestions review page.
 */
export function RecipeSuggestionsPage() {
  const { data: suggestions, isLoading, isError, error } = useSuggestions();

  const awaitingReview = suggestions?.filter(
    (suggestion) => !suggestion.dismissed && suggestion.confirmed_dish_id === null,
  );

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Recipe Suggestions
      </Typography>

      {isLoading && <RowsSkeleton count={3} />}

      {isError && <Alert severity="error">{`Could not load suggestions. ${errorMessage(error)}`}</Alert>}

      {!isLoading && !isError && awaitingReview?.length === 0 && (
        <Typography color="text.secondary">No suggestions awaiting review.</Typography>
      )}

      {!isLoading &&
        !isError &&
        awaitingReview?.map((suggestion) => (
          <ReviewableSuggestionCard key={suggestion.id} suggestion={suggestion} />
        ))}
    </>
  );
}
