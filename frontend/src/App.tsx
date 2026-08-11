import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router";

import { ConnectionStatusProvider } from "./components/shell/ConnectionStatusContext";
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
 * @returns The whole application, wrapped in its providers.
 */
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConnectionStatusProvider>
        <ThemeModeProvider>
          <RouterProvider router={router} />
        </ThemeModeProvider>
      </ConnectionStatusProvider>
    </QueryClientProvider>
  );
}

export default App;
