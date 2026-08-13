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
 * A Role's nav lists only surfaces that Role is authorized for, which is
 * Story 1.4 AC2's intent (a Waiter must never see Admin tools) and is how that
 * AC is now worded in epics.md. Admin's Ingredients entry is the first entry
 * that crosses a URL prefix: `POST /api/inventory/ingredients` permits `admin`
 * and `warehouse_manager` alike (`InventoryWriteDep`, Story 2.1), and Story
 * 2.6's AC4 states the creation flow is reachable by "a Warehouse Manager or
 * Admin". Without this entry the backend's grant would be unreachable from the
 * UI for one of the two Roles it names. AC2's wording was amended in the same
 * story rather than left contradicting the code (Story 2.6 review).
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
 * Each Role's own URL prefix. Not exported: canRoleVisit below is the only
 * consumer, and the one seam callers should go through.
 */
const ROLE_PATH_PREFIX: Record<UserRole, string> = {
  admin: "/admin",
  waiter: "/waiter",
  cook: "/cook",
  warehouse_manager: "/warehouse",
};

/**
 * Whether a Role may visit a path: anything under its own URL prefix, or a
 * surface its own nav links to.
 *
 * Deriving the cross-prefix half from ROLE_NAV_ITEMS rather than a second
 * hand-kept list is what keeps such a grant from drifting: a nav entry a Role
 * cannot actually open is unrepresentable. (The converse does not hold, and
 * deliberately so: the prefix clause makes every path under a Role's own
 * prefix reachable whether or not the nav links to it, which is what lets
 * detail routes like /waiter/tables/:tableId work without their own entry.)
 *
 * Two matching rules, and the difference matters:
 *   - The prefix clause is segment-aware, so "/admin" does not also match
 *     "/administration" should such a route ever exist.
 *   - The nav clause is an *exact* match, so an entry grants exactly the one
 *     surface it names and never its subtree. Admin's Ingredients entry must
 *     not silently also open /warehouse/ingredients/:ingredientId, which is
 *     Story 4.3's surface and nobody's to grant here (Story 2.6 review).
 *
 * Still a navigation affordance, not a security boundary. The backend's
 * require_role remains the only real enforcement.
 *
 * @param role - The acting User's Role.
 * @param pathname - The path being visited.
 * @returns Whether the Role is allowed to land on that path.
 */
export function canRoleVisit(role: UserRole, pathname: string): boolean {
  const ownPrefix = ROLE_PATH_PREFIX[role];
  const isUnderOwnPrefix = pathname === ownPrefix || pathname.startsWith(`${ownPrefix}/`);
  // `?? []` rather than a bare index: UserRole is a compile-time union, but the
  // Role arrives as a string off the wire, so a Role added backend-first would
  // otherwise throw inside the route guard and blank the whole app.
  const navItems = ROLE_NAV_ITEMS[role] ?? [];
  return isUnderOwnPrefix || navItems.some((item) => pathname === item.path);
}
