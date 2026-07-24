# Edge Case Hunter — PRD Review

**Reviewed:** `prd.md` + `addendum.md` (full file, launch-tier)
**Method:** `bmad-review-edge-case-hunter` — exhaustive path enumeration, unhandled/ambiguous paths only, no severity ranking, no editorializing.
**Finding count:** 21

---

## Findings (JSON)

```json
[
  {
    "location": "prd.md:165-171 vs prd.md:130-131",
    "trigger_condition": "FR-6 implies per-waiter table assignment; FR-2 explicitly excludes per-resource filtering",
    "guard_snippet": "Define what \"tables/orders they're responsible for\" means given FR-2's Role-only-permissions scope, or drop the phrase from FR-6",
    "potential_consequence": "Unclear if every Waiter sees every table or only an unspecified subset"
  },
  {
    "location": "prd.md:149-156",
    "trigger_condition": "Waiter attempts FR-4 open-table action on a Table whose status is reserved",
    "guard_snippet": "if table.status == 'reserved': define allow/reject behavior (currently only 'occupied' is guarded)",
    "potential_consequence": "Undefined system behavior when a reserved table is opened"
  },
  {
    "location": "prd.md:157-164",
    "trigger_condition": "Waiter needs to edit quantity/note or remove an Order Item already added, before or after pickup",
    "guard_snippet": "Add FR: edit/remove an Order Item while status is pending (and note-amend while in_preparation)",
    "potential_consequence": "Wrong or changed-mind orders cannot be corrected once submitted"
  },
  {
    "location": "prd.md:172-179",
    "trigger_condition": "Waiter attempts FR-7 close on an Order with zero Order Items, or on an Order containing an item that can never reach ready (e.g. dish 86'd mid-service, no cancel path exists)",
    "guard_snippet": "Define closability for zero-item orders; add an Order Item cancel/void path so a hard-blocked FR-7 cannot deadlock a table",
    "potential_consequence": "A table could become permanently unclosable, or an empty table's closability is undefined"
  },
  {
    "location": "prd.md:193-201",
    "trigger_condition": "Cook mis-clicks and needs to revert in_preparation to pending, or ready to in_preparation",
    "guard_snippet": "Add explicit reverse-transition rule or state it is intentionally disallowed",
    "potential_consequence": "A mis-pick or mis-mark-ready cannot be corrected once triggered, and stock is already deducted"
  },
  {
    "location": "prd.md:202-208",
    "trigger_condition": "All Order Items reach ready; Order Item has no served status, so nothing in FR-10 defines the ready to served transition",
    "guard_snippet": "Add FR: define the actor/action/condition that moves an Order from ready to served",
    "potential_consequence": "Order can get stuck at ready with no defined path to served before FR-7 close"
  },
  {
    "location": "prd.md:133-141",
    "trigger_condition": "Admin needs to change an existing User's Role or full name after creation",
    "guard_snippet": "Add FR: edit an existing User's Role/name (FR-3 currently only covers create + deactivate)",
    "potential_consequence": "A mis-assigned role can only be fixed by deactivating and recreating the account, losing continuity"
  },
  {
    "location": "prd.md:133-141",
    "trigger_condition": "Admin creates a User with a username that already exists",
    "guard_snippet": "Add consequence: duplicate username on creation is rejected (mirrors FR-21's table-number uniqueness rule)",
    "potential_consequence": "Two accounts could collide on username, or behavior on collision is undefined"
  },
  {
    "location": "prd.md:133-141",
    "trigger_condition": "Admin deactivates the only remaining active admin account (including themselves)",
    "guard_snippet": "Add guard: reject deactivation that would leave zero active Admin accounts",
    "potential_consequence": "System could be left with no admin able to log in and manage users/menu"
  },
  {
    "location": "prd.md:133-141",
    "trigger_condition": "A Cook with an Order Item currently in_preparation is deactivated by Admin mid-shift",
    "guard_snippet": "Add FR: reassign/hand off an in-progress Order Item to another Cook (or Admin) when its assigned Cook is deactivated",
    "potential_consequence": "That Order Item can never be marked ready since the only Role permitted to transition it (FR-9, Cook) can no longer log in as that user, and no other actor is authorized to take over"
  },
  {
    "location": "prd.md:223-225",
    "trigger_condition": "A waste or negative-adjustment Stock Movement (FR-13) pushes an Ingredient below its minimum threshold",
    "guard_snippet": "Broaden FR-12's trigger from \"After any consumption Stock Movement\" to \"after any Stock Movement that can decrease stock\"",
    "potential_consequence": "A shortage caused by waste/adjustment instead of consumption may never surface a Low-Stock Alert"
  },
  {
    "location": "prd.md:227-228",
    "trigger_condition": "Two consumption Stock Movements on the same Ingredient cross the threshold at nearly the same instant (the exact UJ-3 edge-case scenario)",
    "guard_snippet": "Make alert check-and-create atomic/unique-constrained per Ingredient-in-shortage; NFR-3 only covers deduction atomicity, not alert dedup",
    "potential_consequence": "Two active alerts could be created for the same shortage, contradicting the stated one-active-alert-per-ingredient rule"
  },
  {
    "location": "prd.md:231-237",
    "trigger_condition": "Warehouse Manager logs a waste or negative adjustment movement with a quantity exceeding current stock",
    "guard_snippet": "State whether manual movements may drive stock negative, matching or diverging from the consumption path's explicit allowance",
    "potential_consequence": "Unclear whether manual entry can produce negative stock or should be capped at zero"
  },
  {
    "location": "prd.md:209-244",
    "trigger_condition": "A new raw-material Ingredient needs to exist before it can appear in a Stock Movement (FR-13) or a Recipe (FR-20)",
    "guard_snippet": "Add FR: create a new Ingredient (name, unit of measure, minimum threshold)",
    "potential_consequence": "No defined path creates the Ingredient master record that FR-13/FR-14/FR-20 all assume already exists"
  },
  {
    "location": "prd.md:295-301",
    "trigger_condition": "Admin changes a Dish's price while an Order containing that Dish is already open (not yet closed)",
    "guard_snippet": "State whether Order total (FR-7) uses the Order-Item's price-at-add-time or the Dish's current price at close time (FR-20 resolves the equivalent question for Recipe staleness; FR-19 does not for price)",
    "potential_consequence": "total_amount could reflect a price the customer never saw, or be computed inconsistently across orders"
  },
  {
    "location": "prd.md:295-301",
    "trigger_condition": "Admin marks a Dish unavailable (FR-19) while it has existing pending or in_preparation Order Items already in the kitchen queue",
    "guard_snippet": "State whether in-flight Order Items for a newly-unavailable Dish must still be prepared or are blocked/voided",
    "potential_consequence": "Kitchen behavior for already-placed items of a just-86'd dish is undefined"
  },
  {
    "location": "prd.md:295-308",
    "trigger_condition": "A Dish is marked available (FR-19) before its Recipe (FR-20) has any Recipe Ingredient lines defined",
    "guard_snippet": "Require a non-empty Recipe as a precondition for marking a Dish available, or explicitly allow zero-ingredient dishes",
    "potential_consequence": "FR-5 lets the dish be ordered and FR-11's stock deduction silently becomes a no-op with no recorded Stock Movement"
  },
  {
    "location": "prd.md:309-314",
    "trigger_condition": "Admin needs to remove or renumber a Restaurant Table after creation",
    "guard_snippet": "Add FR for table deletion/deactivation and restate FR-21's uniqueness rule to account for it (tracks PRD's own Open Question 5, left without a default)",
    "potential_consequence": "No path to correct a mis-entered table number or retire a table; uniqueness behavior on renumbering is undefined"
  },
  {
    "location": "prd.md:269-277",
    "trigger_condition": "A Cook opens or scrolls back through a Chat Session or Recipe Suggestion originally created by a different Cook",
    "guard_snippet": "State Chat Session/Recipe Suggestion visibility scope explicitly, since FR-2's Out-of-Scope note excludes exactly this kind of per-resource restriction",
    "potential_consequence": "Unclear whether all Cooks share every colleague's in-progress recipe drafts and chat history, or each Cook's are private"
  },
  {
    "location": "prd.md:251-258",
    "trigger_condition": "A Cook submits two Recipe Suggestion generation requests in quick succession (e.g. double-click) before the first completes",
    "guard_snippet": "Add guard: disable/ignore a second FR-15 request while one is already in flight for that Cook",
    "potential_consequence": "Duplicate simultaneous OpenAI calls and duplicate persisted Recipe Suggestion rows for one intended request"
  },
  {
    "location": "prd.md:363",
    "trigger_condition": "Two Waiters, or a Waiter and a Cook, edit the same Table/Order at the same time (PRD's own Open Question 4)",
    "guard_snippet": "Resolve OQ4 with a default (last-write-wins, optimistic locking + conflict message, or explicitly out of scope) — currently no default is assumed, unlike OQ1-OQ3",
    "potential_consequence": "Concurrent edits to the same Table/Order have no defined resolution, unlike every other concurrency case in the PRD (NFR-3 covers stock/status atomicity only)"
  }
]
```

---

## Plain-language restatement (for PM action)

1. **Waiter table visibility contradicts itself.** FR-6 talks about "tables a waiter is responsible for," but FR-2 explicitly says the system won't do per-waiter filtering in v1. As written, it's not clear if every waiter sees every table, or if there's some unstated assignment concept. Pick one and reword.

2. **Opening a "reserved" table is undefined.** FR-4 only says what happens if a table is already `occupied`. Nothing says what happens if a waiter tries to open a table that's `reserved`.

3. **No way to fix or cancel an order item after it's submitted.** A waiter can add items (FR-5) but there's no FR to edit a quantity, add/change a note, or remove an item — before or after the kitchen starts on it.

4. **Closing a table can deadlock.** If an order item can never become "ready" (e.g., the dish had to be pulled mid-shift) and there's no cancel path, FR-7's hard-block means that table may never close. Also unclear whether an order with zero items can be closed at all.

5. **No "undo" for a cook's status mis-click.** Once an item is marked in-preparation or ready, there's no way back, even for a mistake — and stock is already deducted at pickup, so this isn't cosmetic.

6. **The order lifecycle has a missing link.** The glossary lists `ready → served → closed` for orders, but order *items* only ever reach `ready` — nothing says what actually moves the order from `ready` to `served`.

7-9. **User management is create/deactivate only.** There's no way to fix a wrongly-assigned role, no stated rule against two accounts sharing a username, and nothing stops an admin from deactivating the last remaining admin account (locking everyone out of administration).

10. **A cook being deactivated mid-shift can strand an order.** If a cook has an item in progress and gets deactivated, nobody else is authorized to pick it up and finish it, per the strict role rules elsewhere in the PRD.

11. **Low-stock alerts only check consumption, not waste/adjustment.** If a warehouse manager logs waste or a negative adjustment that drops stock below threshold, the PRD's alert trigger (worded as "after any consumption movement") doesn't clearly cover it.

12. **Possible duplicate low-stock alerts under real concurrency.** The PRD explicitly worries about two simultaneous consumption events (UJ-3's own edge case) but the "one alert per shortage" rule isn't described as atomic, so a race could still produce two alerts.

13. **No rule on manual entries driving stock negative.** It's spelled out that automatic consumption can push stock negative (intentionally). It's not said whether a warehouse manager's manual waste/adjustment entry is allowed to do the same.

14. **There's no FR for creating an ingredient in the first place.** Recording stock movements and building recipes both assume the ingredient already exists as a record — nothing creates that record.

15. **Price changes mid-order are unresolved.** If a dish's price changes while a table's order is still open, it's not stated whether the final bill uses the old or new price (the PRD solved this exact problem for recipes but not for prices).

16. **86'ing a dish mid-service doesn't say what happens to items already in the kitchen queue for it.**

17. **A dish can go live with no recipe attached**, which means the automatic stock-deduction feature silently does nothing for that dish.

18. **No way to delete or renumber a table** — this is actually already flagged as the PRD's own Open Question 5, but no default answer is given, so it remains a true gap.

19. **Unclear whether cooks can see each other's Smart Chef drafts and chats** — the "no per-resource permissions" rule elsewhere implies yes, but that's never said outright for chat/suggestions specifically.

20. **Double-clicking "generate a suggestion" isn't guarded against** — could fire two AI calls and create two draft rows for one request.

21. **Concurrent edits to the same table/order (PRD's own Open Question 4) are explicitly acknowledged as unresolved** — unlike the PRD's other open questions, no working default is assumed here, so this genuinely has no defined behavior today.
