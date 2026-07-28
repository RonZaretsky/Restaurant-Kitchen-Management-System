# Application Flow — Restaurant Kitchen Management System

This describes the end-to-end flow the system is being built toward (target behavior),
tying the domain modules from [database-schema.md](database-schema.md) together into one
runtime story. See [CLAUDE.md](../CLAUDE.md) for architecture, stack, and design-pattern
guidance.

## 1. Authentication & role routing

A user (`waiter` / `cook` / `warehouse_manager` / `admin`) logs in. Their `User.role`
determines which screens and actions are available. This is modeled as an explicit role
hierarchy/strategy rather than scattered role checks — see the Design Patterns section in
CLAUDE.md.

## 2. Order intake (waiter)

- Waiter opens a `RestaurantTable` (`available → occupied`).
- Waiter browses the menu to decide what to offer the table (see **Dish availability**
  below — this is a live, computed check, not just `Dish.is_available`).
- Waiter creates an `Order` against the table and adds `OrderItem` lines (dish, quantity,
  notes). Each submission is guarded by the same availability check.
- `Order` and its `OrderItem`s start at `pending`.

### Dish availability (stock-aware, not just the manual flag)

`Dish.is_available` is a manual admin toggle, but *actual* sellability also depends on
whether there's enough raw stock to make the dish right now. Real availability is:

```
is_available AND enough Ingredient.current_stock for every RecipeIngredient of the dish
```

The system should expose a computed **max servable portions** per dish:

```
max_servable(dish) = min over each RecipeIngredient ri of dish:
    floor(Ingredient(ri.ingredient_id).current_stock / ri.quantity)
```

This check runs in two places, and must be a single shared implementation (not
duplicated) — a natural `MenuAvailabilityService` in `services/`:

1. **Menu-browsing time** — waiter's menu view shows live availability (e.g. "only 2
   left") instead of a flat yes/no.
2. **Order-submission time** — re-checked as a guard when the waiter actually adds N
   portions to the order, since stock may have moved since the menu was loaded (race with
   other waiters/cooks/kitchen consumption). On failure, the rejection must say *which*
   ingredient is short, not just "unavailable."

## 3. Kitchen execution (cook)

- Cooks see incoming `OrderItem`s in real time (implies a push mechanism — websockets or
  polling; Observer-shaped).
- A cook picks up an item → `OrderItem.status = in_preparation`, `cook_id` set.
- **Stock deduction trigger**: for the dish's `RecipeIngredient` rows, deduct
  `ri.quantity × OrderItem.quantity` from each `Ingredient.current_stock`, and append a
  `StockMovement(type=consumption, reference_id=Order.id)`.
- Immediately after deduction, check `Ingredient.current_stock < min_stock_threshold` per
  affected ingredient; if breached, alert the warehouse manager.
- Cook marks the item `ready` ("pass") when done.
- `Order.status` is **derived**, not set directly: once any item is `in_preparation` the
  order follows; once all items are `ready`, the order becomes `ready`. Waiter then marks
  it `served`, then `closed` when the bill is paid (`Order.total_amount` populated on close).

## 4. Inventory & logistics (warehouse manager)

- Views current stock and receives low-stock alerts from step 3.
- Logs `purchase` (stock delivered), `waste` (disposal), or `adjustment` (manual
  correction) — each just another `StockMovement` row, same audit trail as automatic
  `consumption`.

## 5. AI smart chef (cook/admin)

- **Recipe generator**: reads current `Ingredient` stock, sends a prompt to OpenAI, stores
  the result as an `AIRecipeSuggestion` (prompt + generated recipe + stock snapshot, so
  it's reproducible/auditable later). Purpose: suggest dishes/specials that use up
  near-threshold or surplus stock before it's wasted — closing the loop back to the menu.
- **Smart assistant**: persistent chat (`AIChatSession` → many `AIChatMessage`) where the
  chef iterates on recipes, asks for substitutions, versions dishes, etc. — ongoing
  conversational context, unlike the one-shot recipe generator.

## 6. Administration (admin)

- Menu management: create/update `Category` and `Dish` (price, availability, prep time).
- User management: create users, assign roles, deactivate accounts (`is_active`).

## The central loop

```
Menu (admin)
   -> Order (waiter, gated by live dish availability)
   -> Preparation (cook)
   -> automatic stock deduction + threshold alert (inventory)
   -> AI suggests new dishes from leftover/near-threshold stock
   -> back to Menu
```

The stock-deduction trigger at `in_preparation`, and the availability check at order time,
are the connective tissue between four of the five modules — likely the most important
flows to get right architecturally:

- **State** — `Order` / `OrderItem` status lifecycles.
- **Observer** — low-stock alerts, real-time order/kitchen updates.
- **Strategy** — per-`MovementType` stock handling, role-based permissions.
- **Repository** — DB access per aggregate (Order, Inventory, Menu), kept out of routes.
