/** Mirrors the JSON shape of `backend/data_models/ai.py`'s `AIRecipeSuggestionResponse`. */
export interface AIRecipeSuggestion {
  id: number;
  requested_by: number;
  prompt_used: string;
  generated_recipe: {
    name: string;
    ingredients: { name: string; quantity: string }[];
    plating: string;
  };
  ingredients_snapshot: { name: string; unit: string; current_stock: string }[];
  created_at: string;
}
