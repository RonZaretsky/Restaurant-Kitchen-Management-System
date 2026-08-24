import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";

import type { AIRecipeSuggestion } from "../../types/ai";

/**
 * The read-only content shared by every Recipe Suggestion card: name, who
 * requested it and when, the ingredients it drew on, and its suggested
 * plating. Extracted from `SmartChefPage.tsx`'s original `SuggestionCard` so
 * `RecipeSuggestionsPage.tsx` (Story 6.2) can wrap the same content with its
 * own Confirm/Dismiss actions instead of duplicating this markup.
 *
 * `requested_by` is shown as a raw `User #{id}`, not a resolved name: no
 * endpoint either a Cook or this page's Admin caller can rely on resolves a
 * user id to a name here, the same precedent `StockMovement`'s own
 * "Recorded by" column already established.
 *
 * @param suggestion - The Recipe Suggestion this summary describes.
 * @returns The suggestion's read-only content.
 */
export function SuggestionSummary({ suggestion }: { suggestion: AIRecipeSuggestion }) {
  return (
    <>
      <Typography variant="h6">{suggestion.generated_recipe.name}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ marginBottom: 1 }}>
        {`Requested by User #${suggestion.requested_by} · generated ${new Date(suggestion.created_at).toLocaleString()}`}
      </Typography>

      <Typography variant="subtitle2" sx={{ marginTop: 1 }}>
        Ingredients drawn on
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, marginTop: 0.5, marginBottom: 1 }}>
        {suggestion.generated_recipe.ingredients.map((ingredient, index) => (
          <Chip
            key={`${ingredient.name}-${index}`}
            size="small"
            label={`${ingredient.name}, ${ingredient.quantity}`}
          />
        ))}
      </Box>

      <Typography variant="subtitle2">Suggested plating</Typography>
      <Typography variant="body2">{suggestion.generated_recipe.plating}</Typography>
    </>
  );
}
