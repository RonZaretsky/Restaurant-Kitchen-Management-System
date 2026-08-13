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
 * This map is the single source of truth both the AppShell nav and the route
 * guard's role-scoped redirect read from: a Role may visit its own URL prefix
 * plus anything listed here, and nothing else (see canRoleVisit).
 *
 * A Role's nav lists only its own prefix's surfaces, with one deliberate
 * exception: Admin also gets Ingredients. `POST /api/inventory/ingredients`
 * permits `admin` and `warehouse_manager` alike (`InventoryWriteDep`, Story
 * 2.1), and Story 2.6's AC4 states the Ingredients creation flow is reachable
 * by "a Warehouse Manager or Admin". Without this entry the backend's grant
 * would be unreachable from the UI for one of the two Roles it names.
 */
export const ROLE_NAV_ITEMS: Record<UserRole, { label: string; path: string }[]> = {
  admin: [
    { label: "Menu Management", path: "/admin/menu" },
    { label: "Recipe Suggestions", path: "/admin/recipe-suggestions" },
    { label: "Users", path: "/admin/users" },
    { label: "Tables setup", path: "/admin/tables" },
    { label: "Ingredients", path: "/warehouse/ingredients" },
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

/**
 * Whether a Role may visit a path: its own prefix, or any surface its own nav
 * links to.
 *
 * Deriving the second half from ROLE_NAV_ITEMS rather than a second hand-kept
 * list is what keeps a cross-prefix grant from drifting: a nav entry a Role
 * cannot actually open, or a reachable surface with no way to navigate to it,
 * are both unrepresentable here.
 *
 * Still a navigation affordance, not a security boundary. The backend's
 * require_role remains the only real enforcement.
 *
 * @param role - The acting User's Role.
 * @param pathname - The path being visited.
 * @returns Whether the Role is allowed to land on that path.
 */
export function canRoleVisit(role: UserRole, pathname: string): boolean {
  return (
    pathname.startsWith(ROLE_PATH_PREFIX[role]) ||
    ROLE_NAV_ITEMS[role].some((item) => pathname.startsWith(item.path))
  );
}
