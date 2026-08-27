import { useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { RowsSkeleton } from "../shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useChatMessages, useSendChatMessage } from "../../services/smartChefService";
import type { AIChatMessage } from "../../types/ai";

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
 * One Chat Message bubble, styled distinctly per role.
 *
 * Translates the mockup's `.msg.user`/`.msg.assistant` inline styles (`key-smart-chef.html`,
 * `DESIGN.md` has no formal `{components.chat-*}` token for this) to MUI primitives rather than
 * inventing a new design-system entry: a right-aligned tinted bubble for the Cook's own turn, a
 * left-aligned neutral one for the assistant's reply, each labeled with who sent it.
 *
 * @param message - The Chat Message to render.
 * @returns The message bubble.
 */
function ChatMessageBubble({ message }: { message: AIChatMessage }) {
  const isUser = message.role === "user";
  return (
    <Box
      sx={{
        alignSelf: isUser ? "flex-end" : "flex-start",
        backgroundColor: isUser ? "primary.50" : "action.hover",
        border: "1px solid",
        borderColor: isUser ? "primary.100" : "divider",
        borderRadius: 1,
        padding: 1,
        maxWidth: "80%",
      }}
    >
      <Typography variant="caption" color="text.secondary" component="div">
        {isUser ? "You" : "Smart Chef"}
      </Typography>
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
        {message.content}
      </Typography>
    </Box>
  );
}

/**
 * A self-contained Chat Session panel (Story 6.3, AC1, AC2, AC4, AC5).
 *
 * Renders the session's full message history (oldest first, `useChatMessages`'s own AC5
 * ordering), a text input + Send button wired to `useSendChatMessage`, an in-flight indicator
 * while a reply is generating (matching `SmartChefPage.tsx`'s own `CircularProgress` + text
 * "generating" precedent rather than a new spinner shape), and an inline error Alert on a failed
 * send (AC4 — a failed send must render a clear failure state, not a silently-stuck "sending").
 *
 * An empty message list (a freshly created session with zero messages yet) renders no special
 * copy — no AC names an empty-messages state distinct from "No chat sessions yet" (AC6, which is
 * about the sessions list, not one open session's own history).
 *
 * @param sessionId - The Chat Session this panel renders and sends into.
 * @returns The chat panel.
 */
export function ChatPanel({ sessionId }: { sessionId: number }) {
  const [content, setContent] = useState("");
  const { data: messages, isLoading, isError, error } = useChatMessages(sessionId);
  const sendMutation = useSendChatMessage();

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (sendMutation.isPending) {
      // Re-checks the pending state directly rather than trusting the disabled button alone —
      // Enter submits a form regardless of a disabled submit button, matching SmartChefPage's
      // own request-bar precedent.
      return;
    }
    const trimmed = content.trim();
    if (trimmed === "") {
      return;
    }
    sendMutation.mutate({ sessionId, content: trimmed }, { onSuccess: () => setContent("") });
  };

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        padding: 2,
      }}
    >
      {isLoading && <RowsSkeleton count={2} />}

      {isError && <Alert severity="error">{`Could not load messages. ${errorMessage(error)}`}</Alert>}

      {!isLoading && !isError && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1, maxHeight: 320, overflowY: "auto" }}>
          {messages?.map((message) => (
            <ChatMessageBubble key={message.id} message={message} />
          ))}
        </Box>
      )}

      <Box
        component="form"
        onSubmit={handleSubmit}
        sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}
      >
        <TextField
          size="small"
          fullWidth
          label="Ask a follow-up"
          value={content}
          onChange={(event) => setContent(event.target.value)}
        />
        <Button type="submit" variant="contained" disabled={sendMutation.isPending}>
          Send
        </Button>
      </Box>

      {sendMutation.isPending && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <CircularProgress size={18} />
          <Typography variant="body2" color="text.secondary">
            Generating reply...
          </Typography>
        </Box>
      )}

      {sendMutation.isError && <Alert severity="error">{errorMessage(sendMutation.error)}</Alert>}
    </Box>
  );
}
