import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { RequireAuth } from "./components/shell/RequireAuth";
import { MenuManagementPage } from "./pages/admin/MenuManagementPage";
import { RecipeSuggestionsPage } from "./pages/admin/RecipeSuggestionsPage";
import { TablesSetupPage } from "./pages/admin/TablesSetupPage";
import { UsersPage } from "./pages/admin/UsersPage";
import { DishesPage } from "./pages/cook/DishesPage";
import { KitchenDisplayPage } from "./pages/cook/KitchenDisplayPage";
import { SmartChefPage } from "./pages/cook/SmartChefPage";
import { LoginPage } from "./pages/login/LoginPage";
import { TableOrderDetailPage } from "./pages/waiter/TableOrderDetailPage";
import { TablesPage } from "./pages/waiter/TablesPage";
import { AlertsPage } from "./pages/warehouse/AlertsPage";
import { IngredientDetailPage } from "./pages/warehouse/IngredientDetailPage";
import { IngredientsPage } from "./pages/warehouse/IngredientsPage";

/**
 * The app's route tree. Declarative mode (createBrowserRouter/RouterProvider),
 * not framework mode, this project has no @react-router/dev Vite plugin.
 *
 * One route per IA surface (AC1), sourced from the mockups' own address
 * bars (see the story's Dev Notes route table), all but Login gated behind
 * RequireAuth. The catch-all sends any other authenticated URL back through
 * RequireAuth's own root-path redirect rather than rendering a blank page.
 *
 * Exported separately from the router instance itself, so tests can build
 * their own createMemoryRouter from the exact same route config instead of
 * fighting createBrowserRouter's dependency on the real browser history.
 */
export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: <RequireAuth />,
    children: [
      { path: "waiter/tables", element: <TablesPage /> },
      { path: "waiter/tables/:tableId", element: <TableOrderDetailPage /> },
      { path: "cook/kitchen-display", element: <KitchenDisplayPage /> },
      { path: "cook/dishes", element: <DishesPage /> },
      { path: "cook/smart-chef", element: <SmartChefPage /> },
      { path: "warehouse/ingredients", element: <IngredientsPage /> },
      { path: "warehouse/ingredients/:ingredientId", element: <IngredientDetailPage /> },
      { path: "warehouse/alerts", element: <AlertsPage /> },
      { path: "admin/menu", element: <MenuManagementPage /> },
      { path: "admin/recipe-suggestions", element: <RecipeSuggestionsPage /> },
      { path: "admin/users", element: <UsersPage /> },
      { path: "admin/tables", element: <TablesSetupPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
