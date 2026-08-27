import { describe, expect, it } from "vitest";

import { canRoleVisit } from "./navigationConfig";

// Focused unit coverage of canRoleVisit's includeSubroutes clause (this batch's #2), on top of
// router.test.tsx's own integration-level coverage of the same behavior through the real route
// tree. Exercised directly here since router.test.tsx cannot isolate the nav clause from the
// prefix clause for every case (most nav entries live under their own owner's prefix, so only
// Admin's cross-prefix Ingredients entry can prove the nav clause's own behavior in isolation).

describe("canRoleVisit", () => {
  it("still grants a nav entry's exact surface with no includeSubroutes change in behavior", () => {
    expect(canRoleVisit("admin", "/warehouse/ingredients")).toBe(true);
  });

  it("grants an includeSubroutes entry's subtree", () => {
    expect(canRoleVisit("admin", "/warehouse/ingredients/5")).toBe(true);
  });

  it("does not treat a same-prefix sibling path as a subroute (segment-aware, not a raw prefix match)", () => {
    // "/warehouse/ingredients-other" starts with "/warehouse/ingredients" as a raw string, but is
    // not a subroute of it (no "/" boundary) — must not be granted.
    expect(canRoleVisit("admin", "/warehouse/ingredients-other")).toBe(false);
  });

  it("does not extend the includeSubroutes grant to a different nav entry entirely", () => {
    // /warehouse/alerts is a completely different path, not under the Ingredients entry's
    // subtree, and Admin's nav does not list it.
    expect(canRoleVisit("admin", "/warehouse/alerts")).toBe(false);
  });

  it("does not grant a warehouse_manager (no includeSubroutes anywhere in its own nav) any cross-prefix subtree", () => {
    expect(canRoleVisit("warehouse_manager", "/admin/menu")).toBe(false);
  });
});
