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
  dismissed: boolean;
  confirmed_dish_id: number | null;
}

/** Mirrors the JSON shape of `backend/data_models/ai.py`'s `AIChatSessionResponse` (Story 6.3). */
export interface AIChatSession {
  id: number;
  user_id: number;
  dish_id: number | null;
  suggestion_id: number | null;
  title: string;
  created_at: string;
}

/** Mirrors the JSON shape of `backend/data_models/ai.py`'s `AIChatMessageResponse` (Story 6.3). */
export interface AIChatMessage {
  id: number;
  session_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}
