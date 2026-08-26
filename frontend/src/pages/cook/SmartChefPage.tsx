import { useMemo, useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { ChatPanel } from "../../components/ai/ChatPanel";
import { SuggestionSummary } from "../../components/ai/SuggestionSummary";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useCurrentUser } from "../../services/authService";
import {
  useChatSessions,
  useCreateChatSession,
  useGenerateSuggestion,
  useSuggestions,
} from "../../services/smartChefService";
import type { AIChatSession, AIRecipeSuggestion } from "../../types/ai";

/** Which Chat Session (if any) is currently open, and which surface opened it. */
type ActiveDiscussion =
  | { source: "suggestion"; suggestionId: number; sessionId: number }
  | { source: "session"; sessionId: number }
  | null;

/**
 * Puts the current Cook's own items first, preserving each group's own relative order (AC3,
 * AD-10's sort-not-filter personalization). A plain client-side sort over an already-fetched
 * list, never a second server-side query parameter (AD-9).
 *
 * @param items - The already-fetched list, in its original (server) order.
 * @param currentUserId - The signed-in Cook's own id, or undefined while still loading.
 * @param ownerId - Resolves the owning user id off one item.
 * @returns The same items, the current Cook's own first.
 */
function sortCurrentUserFirst<T>(items: T[], currentUserId: number | undefined, ownerId: (item: T) => number): T[] {
  if (currentUserId === undefined) {
    return items;
  }
  const own = items.filter((item) => ownerId(item) === currentUserId);
  const others = items.filter((item) => ownerId(item) !== currentUserId);
  return [...own, ...others];
}

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
 * One Recipe Suggestion card (Story 6.1, AC6; "Discuss via chat" added Story 6.3, AC1).
 *
 * Shows the suggestion's content, plus a "Discuss via chat" action that always starts a new
 * Chat Session tied to this suggestion (Scope note: never find-or-resumes an existing one — the
 * Chat Sessions list below is what reopens one). No Confirm/Dismiss actions render here: that
 * stays Story 6.2's Admin-only action, out of scope for this Cook-facing page.
 *
 * `requested_by` is shown as a raw `User #{id}`, not a resolved name: no endpoint a Cook can call
 * resolves a user id to a name (the same precedent `StockMovement`'s own "Recorded by" column
 * already established), and `GET /api/admin/users` is Admin-only.
 *
 * @param suggestion - The Recipe Suggestion this card describes.
 * @param activeSessionId - The Chat Session to render inline below this card, or null if none
 *   is currently open for this suggestion.
 * @param onOpenChat - Called once a new Chat Session is created for this suggestion.
 * @returns The suggestion card.
 */
function SuggestionCard({
  suggestion,
  activeSessionId,
  onOpenChat,
}: {
  suggestion: AIRecipeSuggestion;
  activeSessionId: number | null;
  onOpenChat: (suggestionId: number, sessionId: number) => void;
}) {
  const createSessionMutation = useCreateChatSession();

  const handleDiscuss = () => {
    if (createSessionMutation.isPending) {
      return;
    }
    createSessionMutation.mutate(
      { suggestion_id: suggestion.id },
      { onSuccess: (session) => onOpenChat(suggestion.id, session.id) },
    );
  };

  return (
    <Card variant="outlined" sx={{ padding: 2, marginBottom: 2 }}>
      <SuggestionSummary suggestion={suggestion} />

      <Box sx={{ marginTop: 1, display: "flex", alignItems: "center", gap: 1 }}>
        <Button size="small" variant="outlined" onClick={handleDiscuss} disabled={createSessionMutation.isPending}>
          Discuss via chat
        </Button>
        {createSessionMutation.isPending && <CircularProgress size={16} />}
      </Box>

      {createSessionMutation.isError && (
        <Alert severity="error" sx={{ marginTop: 1 }}>
          {errorMessage(createSessionMutation.error)}
        </Alert>
      )}

      {activeSessionId !== null && (
        <Box sx={{ marginTop: 2 }}>
          <ChatPanel sessionId={activeSessionId} />
        </Box>
      )}
    </Card>
  );
}

/**
 * One row in the Chat Sessions list (Story 6.3, AC3, AC6).
 *
 * Clicking the row opens that exact session's history inline below it — the one place a
 * different Cook's session (or the current Cook's own, from an earlier visit) becomes reachable
 * again, satisfying AC3 concretely.
 *
 * @param session - The Chat Session this row describes.
 * @param isActive - Whether this session's panel is the one currently open.
 * @param onSelect - Called when this row is clicked.
 * @returns The session row, and its chat panel when active.
 */
function ChatSessionRow({
  session,
  isActive,
  onSelect,
}: {
  session: AIChatSession;
  isActive: boolean;
  onSelect: (sessionId: number) => void;
}) {
  return (
    <Box sx={{ marginBottom: 1.5 }}>
      <Card variant="outlined">
        <CardActionArea onClick={() => onSelect(session.id)} sx={{ padding: 2 }}>
          <Typography variant="subtitle1">{session.title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {new Date(session.created_at).toLocaleString()}
          </Typography>
        </CardActionArea>
      </Card>
      {isActive && (
        <Box sx={{ marginTop: 1 }}>
          <ChatPanel sessionId={session.id} />
        </Box>
      )}
    </Box>
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
  const { data: currentUser } = useCurrentUser();
  const {
    data: chatSessions,
    isLoading: sessionsIsLoading,
    isError: sessionsIsError,
    error: sessionsError,
  } = useChatSessions();
  const [activeDiscussion, setActiveDiscussion] = useState<ActiveDiscussion>(null);

  const sortedSuggestions = useMemo(
    () => (suggestions ? sortCurrentUserFirst(suggestions, currentUser?.id, (s) => s.requested_by) : suggestions),
    [suggestions, currentUser?.id],
  );
  const sortedSessions = useMemo(
    () => (chatSessions ? sortCurrentUserFirst(chatSessions, currentUser?.id, (s) => s.user_id) : chatSessions),
    [chatSessions, currentUser?.id],
  );

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

      {!isLoading && !isError && sortedSuggestions?.length === 0 && (
        <Typography color="text.secondary">No recipe suggestions yet.</Typography>
      )}

      {!isLoading &&
        !isError &&
        sortedSuggestions?.map((suggestion) => (
          <SuggestionCard
            key={suggestion.id}
            suggestion={suggestion}
            activeSessionId={
              activeDiscussion?.source === "suggestion" && activeDiscussion.suggestionId === suggestion.id
                ? activeDiscussion.sessionId
                : null
            }
            onOpenChat={(suggestionId, sessionId) =>
              setActiveDiscussion({ source: "suggestion", suggestionId, sessionId })
            }
          />
        ))}

      <Typography variant="h5" component="h2" gutterBottom sx={{ marginTop: 4 }}>
        Chat Sessions
      </Typography>

      {sessionsIsLoading && <RowsSkeleton count={2} />}

      {sessionsIsError && (
        <Alert severity="error">{`Could not load chat sessions. ${errorMessage(sessionsError)}`}</Alert>
      )}

      {!sessionsIsLoading && !sessionsIsError && sortedSessions?.length === 0 && (
        <Typography color="text.secondary">No chat sessions yet.</Typography>
      )}

      {!sessionsIsLoading &&
        !sessionsIsError &&
        sortedSessions?.map((session) => (
          <ChatSessionRow
            key={session.id}
            session={session}
            isActive={activeDiscussion?.source === "session" && activeDiscussion.sessionId === session.id}
            onSelect={(sessionId) => setActiveDiscussion({ source: "session", sessionId })}
          />
        ))}
    </>
  );
}
