import type { UserRole } from "../../types/user";

/**
 * Each Role's home surface, the route login (and the root path) lands on.
 *
 * Sourced from the mockups' own address bars, not invented, see the story's
 * Dev Notes route table.
 */
export const ROLE_HOME_PATH: Record<UserRole, string> = {
  admin: "/admin/menu",
  waiter: "/waiter/tables",
  cook: "/cook/kitchen-display",
  warehouse_manager: "/warehouse/ingredients",
};

/**
 * Each Role's own nav entries, in the order they render left to right.
 *
 * A Role's nav never lists another Role's surfaces (AC2), this map is the
 * single source of truth both the AppShell nav and the route guard's
 * role-scoped redirect read from.
 */
export const ROLE_NAV_ITEMS: Record<UserRole, { label: string; path: string }[]> = {
  admin: [
    { label: "Menu Management", path: "/admin/menu" },
    { label: "Recipe Suggestions", path: "/admin/recipe-suggestions" },
    { label: "Users", path: "/admin/users" },
    { label: "Tables setup", path: "/admin/tables" },
  ],
  waiter: [{ label: "Tables", path: "/waiter/tables" }],
  cook: [
    { label: "Kitchen Display", path: "/cook/kitchen-display" },
    { label: "Dishes", path: "/cook/dishes" },
    { label: "Smart Chef", path: "/cook/smart-chef" },
  ],
  warehouse_manager: [
    { label: "Ingredients", path: "/warehouse/ingredients" },
    { label: "Alerts", path: "/warehouse/alerts" },
  ],
};

/**
 * Each Role's own URL prefix, used by the route guard to detect a
 * cross-role URL visit.
 */
export const ROLE_PATH_PREFIX: Record<UserRole, string> = {
  admin: "/admin",
  waiter: "/waiter",
  cook: "/cook",
  warehouse_manager: "/warehouse",
};
