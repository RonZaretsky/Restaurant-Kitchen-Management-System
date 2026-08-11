import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router";

import { ThemeModeProvider } from "./components/shell/ThemeModeProvider";
import { router } from "./router";

const queryClient = new QueryClient();

/**
 * The app's provider composition root.
 *
 * QueryClientProvider wraps everything else, ThemeModeProvider reads the
 * current User through the query cache to pick its role-based default
 * (AC4), so it must sit inside QueryClientProvider.
 *
 * No ConnectionStatusProvider here: RealtimeProvider (mounted inside
 * RequireAuth, once a User is known) renders it internally with the real
 * WebSocket status, rather than this level providing a static default that
 * nothing could ever update.
 *
 * @returns The whole application, wrapped in its providers.
 */
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeModeProvider>
        <RouterProvider router={router} />
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

export default App;
